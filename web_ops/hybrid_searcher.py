"""Hybrid search over text chunks — BM25 + exact substring matching.

What this module provides
- ``HybridRetriever``: Combines multiple ``BaseRetriever`` instances with
  weighted score fusion.  Each retriever's raw scores are normalised to
  [0, 1] — via RRF (for high‑variance scorers like substring) or via raw‑
  score min‑max (for well‑calibrated scorers like BM25) — then multiplied
  by per‑retriever weight and summed.
- ``HybridSearcher``: High-level wrapper that builds an in-memory index from a
  list of ``TextNode`` objects and runs hybrid queries against it.

Why this exists
- The webfetch pipeline produces chunked content (``_parse_chunked`` →
  ``_flatten_chunks`` → ``TextNode`` list).  This module plugs those nodes
  into a fused retriever so agents can search inside fetched pages without
  needing an LLM or external service.
- BM25 covers stemmed/term‑based matching; substring matching catches
  sub‑word hits (``reload``, ``autoload``) and exact multi‑word phrases
  that BM25 treats as independent terms.
- The index is NOT persistent — it is rebuilt each request.  Typical pages
  produce 10–200 chunks, so the rebuild cost is sub‑second.

How to use
::

    from web_ops.hybrid_searcher import HybridSearcher

    searcher = HybridSearcher()
    searcher.build(nodes, substring_weight=0.4)
    results, total = searcher.search("install python", top_k=5, page=0)
    for r in results:
        print(f"[{r['score_fused']:.3f} | bm25={r['score_bm25']:.3f} "
              f"sub={r['score_substring']:.3f}] {r['highlights'] or r['text'][:80]}")
    # Read pre‑processed query info after search():
    print(searcher.query_cleaned)        # "install python"
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.retrievers.bm25 import BM25Retriever

from web_ops.substring_retriever import (
    SubstringRetriever,
    generate_sub_queries,
    remove_stopwords,
)


# ── Constants ─────────────────────────────────────────────────────────────────

# HuggingFace embedding model.  bge-small-en-v1.5 is 33 MB, 384-dim vectors,
# and runs locally via ONNX runtime — no API key needed.
_DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Default weight assigned to the vector retriever (BM25 gets 1 − weight).
# 0.65 means semantic meaning drives ranking, keywords fill gaps.
# (Currently unused — vector embeddings are commented out.)
_DEFAULT_VECTOR_WEIGHT = 0.65

# Default weight for the substring retriever in BM25 + substring fusion.
# BM25 gets ``1 − substring_weight`` (default 0.6).
_DEFAULT_SUBSTRING_WEIGHT = 0.4

# Hardcoded page size for search results when the caller doesn't specify.
_DEFAULT_TOP_K = 5

# Max characters in the "text" field of each result.  Longer chunks are
# truncated with a "..." suffix and a ``highlights`` field is emitted.
_MAX_TEXT_CHARS = 500

# Number of characters on each side of a substring match used to build
# a highlight snippet for the full‑query match.
_HIGHLIGHT_WINDOW = 40

# Sliding‑window width for the greedy highlight‑placement algorithm.
# Equal to 2 × _HIGHLIGHT_WINDOW so the scoring window matches the
# eventual snippet width — a match centered in the snippet is always
# visible at the density peak.
_GREEDY_WINDOW = 2 * _HIGHLIGHT_WINDOW  # 80

# Reciprocal Rank Fusion constant — controls how tightly top ranks are
# compressed.  k=60 is the standard from the RRF paper (Cormack et al.).
# Smaller k gives more spread between top results.
_RRF_K = 60


# ---------------------------------------------------------------------------
# HybridRetriever — weighted score fusion with per‑retriever normalisation
# ---------------------------------------------------------------------------


class HybridRetriever(BaseRetriever):
    """Combine sub-retrievers with weighted min-max score fusion.

    Each retriever is normalised to [0, 1] then multiplied by its weight.
    Retriever‑specific normalisation is controlled via ``rrf_indices``:

    * **RRF normalisation** (default for all, or opt‑in per retriever):
      replaces raw scores with Reciprocal Rank Fusion scores computed
      from rank positions.  This suppresses outlier dominance from
      high‑variance scorers (e.g. substring matching where one chunk
      can have 200× the matches of the next).
    * **Raw‑score min‑max normalisation** (for retrievers NOT in
      ``rrf_indices``): scales raw scores directly to [0, 1],
      preserving the relative signal strength of the retriever's
      native scoring (e.g. BM25 tf‑idf weights).

    When *labels* are provided (one per retriever), per‑retriever
    scores are stored in ``_per_retriever_scores`` keyed by
    ``node.hash`` — readable by callers after ``_retrieve()`` completes.

    Unlike ``QueryFusionRetriever``, this class does NOT resolve
    ``Settings.llm``, so it can be used without an LLM provider installed.
    """

    def __init__(
        self,
        retrievers: List[BaseRetriever],
        weights: Optional[List[float]] = None,
        labels: Optional[List[str]] = None,
        top_k: int = 8,
        rrf_indices: Optional[Set[int]] = None,
    ) -> None:
        """Initialise the hybrid retriever.

        Args:
            retrievers: Sub-retrievers to combine (e.g. BM25 + substring).
            weights: Per-retriever weight (normalised to sum to 1).
                Defaults to equal weighting.
            labels: Short names for each retriever (e.g. ``["bm25","substring"]``).
                When set, raw per‑retriever scores are stored in
                ``self._per_retriever_scores`` keyed by ``node.hash``.
            top_k: Number of results to return.
            rrf_indices: Indices of retrievers that should use Reciprocal
                Rank Fusion (RRF) normalisation.  Retrievers NOT in this
                set use raw-score min‑max normalisation instead.  When
                ``None`` (default), all retrievers use RRF (backward
                compatible).  Pass an empty set to use raw‑score
                normalisation for every retriever.
        """
        if weights is None:
            weights = [1.0 / len(retrievers)] * len(retrievers)
        else:
            total = sum(weights)
            weights = [w / total for w in weights]
        self._retrievers = retrievers
        self._weights = weights
        self._labels = labels or []
        self._top_k = top_k
        self._rrf_indices: Optional[Set[int]] = rrf_indices
        # Hash-keyed store for per-retriever scores, populated during
        # _retrieve() and read by HybridSearcher.search().
        # Dict[node_hash, Dict[label_key, raw_score]]
        self._per_retriever_scores: Dict[str, Dict[str, float]] = {}
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Run all retrievers, fuse scores, return top-k.

        Steps:
        1. Collect results from every sub-retriever.
        2. Normalise each retriever's scores to [0, 1], then multiply by
           weight.  Retrievers listed in ``rrf_indices`` use Reciprocal Rank
           Fusion (RRF) normalisation — this suppresses outlier dominance
           from high‑variance scorers like substring matching.  Other
           retrievers (e.g. BM25) use raw‑score min‑max normalisation,
           preserving the relative signal strength of actual relevance scores.
        3. Store normalised‑weighted per‑retriever scores in
           ``self._per_retriever_scores`` (same scale as fused score).
        4. Merge duplicates (keyed by ``node.hash``) — scores are summed.
        5. Sort by score descending, return top ``_top_k``.
        """
        # ── Step 1: Collect results ────────────────────────────────────────
        per_retriever: List[List[NodeWithScore]] = []
        for retriever in self._retrievers:
            per_retriever.append(retriever.retrieve(query_bundle))

        # ── Step 2: Normalise each retriever's scores to [0, 1], × weight ──
        for retriever_idx, (nodes, weight) in enumerate(
            zip(per_retriever, self._weights)
        ):
            if not nodes:
                continue
            n = len(nodes)

            # Decide normalisation strategy — RRF or raw‑score min‑max.
            # None (default) = RRF for every retriever (backward compatible).
            use_rrf = (
                self._rrf_indices is None
                or retriever_idx in (self._rrf_indices or set())
            )

            if use_rrf:
                # RRF score for each rank position (1‑based).  Rank scores
                # ignore raw magnitudes — a chunk with 200 substring matches
                # and one with 199 get nearly identical RRF scores, preventing
                # outliers from compressing everything toward zero.
                rrf_scores = [1.0 / (_RRF_K + rank) for rank in range(1, n + 1)]
                rrf_min, rrf_max = rrf_scores[-1], rrf_scores[0]

                if rrf_max == rrf_min:
                    norm_scores = [1.0] * n if rrf_max > 0 else [0.0] * n
                else:
                    norm_scores = [
                        (s - rrf_min) / (rrf_max - rrf_min) for s in rrf_scores
                    ]
            else:
                # Raw‑score min‑max normalisation — preserves the relative
                # signal strength from the retriever's native scoring
                # (e.g. BM25 tf‑idf weights).  When all raw scores are equal
                # (including all‑zero for empty queries), contribution is
                # uniform.
                raw_scores = [node.score or 0.0 for node in nodes]
                raw_min, raw_max = min(raw_scores), max(raw_scores)

                if raw_max == raw_min:
                    norm_scores = [1.0] * n if raw_max > 0 else [0.0] * n
                else:
                    norm_scores = [
                        (s - raw_min) / (raw_max - raw_min) for s in raw_scores
                    ]

            for node, norm in zip(nodes, norm_scores):
                node.score = round(norm * weight, 4)

        # ── Step 3: Store normalised×weight per‑retriever scores ───────────
        # Stored AFTER normalisation so scores are on the same [0, weight]
        # scale as the fused result — directly comparable and algebraically
        # summable: score_fused ≈ score_bm25 + score_substring.
        self._per_retriever_scores = {}
        if self._labels:
            for retriever_idx, nodes in enumerate(per_retriever):
                if retriever_idx >= len(self._labels):
                    continue
                label_key = f"score_{self._labels[retriever_idx]}"
                for node in nodes:
                    h = node.node.hash
                    if h not in self._per_retriever_scores:
                        self._per_retriever_scores[h] = {}
                    self._per_retriever_scores[h][label_key] = round(
                        node.score or 0.0, 4
                    )

        # ── Step 4: Merge duplicates (by node hash) ────────────────────────
        merged: Dict[str, NodeWithScore] = {}
        for nodes in per_retriever:
            for node in nodes:
                h = node.node.hash
                if h in merged:
                    merged[h].score = (
                        (merged[h].score or 0.0) + (node.score or 0.0)
                    )
                else:
                    merged[h] = node

        # ── Step 6: Sort, return top‑k ─────────────────────────────────────
        return sorted(
            merged.values(), key=lambda n: n.score or 0.0, reverse=True
        )[: self._top_k]


# ---------------------------------------------------------------------------
# HybridSearcher — high-level wrapper
# ---------------------------------------------------------------------------


class HybridSearcher:
    """Build an in-memory hybrid index from TextNodes and run queries against it.

    The index is NOT persistent — each ``build()`` call creates fresh BM25
    and substring indexes.  For typical page sizes (10–200 chunks) this
    completes in under a second.

    Usage::

        searcher = HybridSearcher()
        searcher.build(nodes, substring_weight=0.4)
        results, total, cleaned, removed = searcher.search(
            "query", top_k=5, page=0,
        )
    """

    def __init__(self) -> None:
        """Create a searcher with no index loaded yet."""
        self._index: Optional[VectorStoreIndex] = None
        self._nodes: List[TextNode] = []
        self._retriever: Optional[HybridRetriever] = None
        self._substring_retriever: Optional[SubstringRetriever] = None

    def build(
        self,
        nodes: List[TextNode],
        vector_weight: float = _DEFAULT_VECTOR_WEIGHT,
        substring_weight: float = _DEFAULT_SUBSTRING_WEIGHT,
    ) -> None:
        """Index *nodes* for hybrid retrieval.

        Side effects:
        - Creates an in-memory ``BM25Retriever`` over *nodes*.
        - Creates a ``SubstringRetriever`` over *nodes*.
        - Wires both into a ``HybridRetriever`` with weighted score fusion
          (default: BM25 0.6, substring 0.4).

        Args:
            nodes: TextNodes to index (typically flattened from a chunked tree).
            vector_weight: (Reserved) Weight for the vector retriever
                when re‑enabled.  Currently unused.
            substring_weight: Weight for the substring retriever (0–1).
                BM25 gets ``1 − substring_weight``.  Default 0.4.
        """
        # The FastEmbed model is heavy to load (~33 MB download on first use),
        # but the Settings singleton caches it after the first assignment.
        # Settings.embed_model = FastEmbedEmbedding(model_name=_DEFAULT_EMBED_MODEL)

        self._nodes = nodes
        num_nodes = len(nodes)

        # Build vector index — in-memory (no external store needed).
        # self._index = VectorStoreIndex(nodes)
        # vector_retriever = self._index.as_retriever(similarity_top_k=num_nodes)

        # Build BM25 retriever.
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=nodes, similarity_top_k=num_nodes
        )

        # Build substring retriever.
        self._substring_retriever = SubstringRetriever.from_defaults(
            nodes=nodes, similarity_top_k=num_nodes
        )

        # Wire hybrid — fetch all nodes from sub-retrievers so pagination
        # happens after weighted score fusion.
        # self._retriever = HybridRetriever(
        #     retrievers=[vector_retriever, bm25_retriever, self._substring_retriever],
        #     weights=[vector_weight, 1.0 - vector_weight - substring_weight,
        #              substring_weight],
        #     top_k=num_nodes,
        # )
        self._retriever = HybridRetriever(
            retrievers=[bm25_retriever, self._substring_retriever],
            weights=[1.0 - substring_weight, substring_weight],
            labels=["bm25", "substring"],
            top_k=num_nodes,
            rrf_indices={1},  # Only substring retriever uses RRF; BM25 keeps
            # raw‑score min‑max to preserve tf‑idf signal.
        )

    def search(
        self,
        query: str,
        top_k: int = _DEFAULT_TOP_K,
        page: int = 0,
    ) -> Tuple[List[Dict], int]:
        """Run a hybrid query and return paginated results.

        After calling ``search()``, read ``searcher.query_cleaned`` for the
        stopword‑stripped query string.

        Args:
            query: Natural-language search query.
            top_k: Results per page.  Default 5.
            page: Zero-based page index.  Default 0.

        Returns:
            ``(results, total_matches)`` where *results* is a list of dicts
            with keys ``score_fused``, ``score_bm25``, ``score_substring``,
            ``n_substring_matches``, ``text``, ``heading_path``,
            ``line_range``, and optionally ``highlights`` (a ``List[str]`` of
            snippets with matched terms uppercased, drawn from the hidden
            region past the ``_MAX_TEXT_CHARS`` cap; absent entirely when
            no matches exist in the hidden region).  *total_matches* is the
            results across all pages.
        """
        if self._retriever is None:
            raise RuntimeError(
                "HybridSearcher.build() must be called before search()"
            )

        # Preprocess once — store the cleaned query for the caller (e.g. API
        # layer) to include in the response.
        self.query_cleaned, _discard_removed = remove_stopwords(query)

        raw_results = self._retriever.retrieve(query)
        # Drop near‑zero results before pagination so they never reach
        # the caller.  0.05 is low enough to include any remotely
        # relevant hit while excluding pure noise.
        _SCORE_FLOOR = 0.05
        raw_results = [
            r for r in raw_results if (r.score or 0.0) >= _SCORE_FLOOR
        ]
        total = len(raw_results)
        page_slice = raw_results[page * top_k : (page + 1) * top_k]

        # Generate sub‑queries once for highlight extraction and match counting.
        sub_queries = generate_sub_queries(self.query_cleaned)

        formatted: List[Dict] = []
        for r in page_slice:
            node_metadata = r.node.metadata or {}
            # Per‑retriever scores live in HybridRetriever's hash‑keyed
            # dict (neither NodeWithScore.metadata nor TextNode.metadata —
            # both are on per‑retriever COPIES of TextNode objects).
            per_retriever_scores: dict = (
                (self._retriever._per_retriever_scores or {}).get(
                    r.node.hash, {}
                )
            )
            full_text: str = r.node.text

            # Truncate long text; extract highlights from the hidden region.
            truncated = len(full_text) > _MAX_TEXT_CHARS
            display_text = (
                f"{full_text[:_MAX_TEXT_CHARS]}… "
                f"[truncated to {_MAX_TEXT_CHARS} chars, "
                f"full chunk has {len(full_text)} chars]"
                if truncated
                else full_text
            )

            # Count substring matches for this chunk (cheap for top-k results).
            n_matches = _count_substring_matches(sub_queries, full_text)

            result: dict = {
                "score_fused": round(r.score or 0.0, 4),
                "score_bm25": per_retriever_scores.get("score_bm25", 0.0),
                "score_substring": per_retriever_scores.get("score_substring", 0.0),
                "n_substring_matches": n_matches,
                "text": display_text,
                "heading_path": node_metadata.get("heading_path", []),
                "line_range": node_metadata.get("lines", []),
            }

            # Highlights are sourced ONLY from the hidden (truncated) region —
            # the visible part is already in the ``"text"`` field.
            if truncated and sub_queries:
                hidden_text = full_text[_MAX_TEXT_CHARS:]
                hidden_chars = len(hidden_text)
                # One highlight per 500 missing chars, capped [1, 5].
                n_highlights = max(1, min(5, (hidden_chars + 499) // 500))
                highlights = _extract_highlights(
                    hidden_text,
                    n_highlights,
                    self.query_cleaned,
                    sub_queries,
                )
                if highlights:
                    result["highlights"] = highlights

            formatted.append(result)

        return formatted, total


# ── Post‑retrieval helpers ────────────────────────────────────────────────────


def _count_substring_matches(sub_queries: List[str], text: str) -> int:
    """Count total non‑overlapping substring match occurrences across all
    sub‑queries in *text* (case‑insensitive).

    Args:
        sub_queries: Output of ``generate_sub_queries``.
        text: Full chunk text.

    Returns:
        Total number of substring matches (may be 0).
    """
    if not sub_queries:
        return 0
    text_lower = text.lower()
    total = 0
    for sub in sub_queries:
        sub_lower = sub.lower()
        start = 0
        while True:
            idx = text_lower.find(sub_lower, start)
            if idx == -1:
                break
            total += 1
            start = idx + len(sub_lower)
    return total


def _add_markers(text: str, sub_queries: List[str]) -> str:
    """Highlight sub‑query matches by uppercasing the span, handling overlaps.

    Finds every occurrence of every sub‑query in *text* (case‑insensitive),
    then greedily selects non‑overlapping matches — longest match wins ties
    at the same start position.  Markers are applied right‑to‑left so
    earlier offsets stay valid.

    Args:
        text: Snippet to annotate.
        sub_queries: All sub‑queries (words, bigrams, full phrase).

    Returns:
        *text* with matched spans uppercased, or *text* unchanged when
        no sub‑query matches.
    """
    if not sub_queries:
        return text

    text_lower = text.lower()

    # ── Find every match span: (start, end, sub_query_text) ──────────────
    spans: List[Tuple[int, int, str]] = []
    for sub in sub_queries:
        sub_lower = sub.lower()
        search_start = 0
        while True:
            idx = text_lower.find(sub_lower, search_start)
            if idx == -1:
                break
            spans.append((idx, idx + len(sub), sub))
            # Step by 1 to catch overlapping matches (e.g. "aaa" in "aaaa"
            # should match at positions 0 and 1); dedup handles overlap.
            search_start = idx + 1

    if not spans:
        return text

    # ── Sort: start ascending, then length descending (longest wins) ─────
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # ── Greedy dedup: keep spans that don't overlap already‑kept ones ────
    kept: List[Tuple[int, int, str]] = []
    for start, end, sub in spans:
        if not kept or start >= kept[-1][1]:
            kept.append((start, end, sub))

    # ── Apply uppercase right‑to‑left (offsets don't shift for earlier ones)
    result = text
    for start, end, sub in reversed(kept):
        result = result[:start] + result[start:end].upper() + result[end:]

    return result


def _find_best_window(
    text: str,
    sub_queries: List[str],
    window_size: int,
    consumed_spans: Set[Tuple[int, int]],
) -> Tuple[int, int]:
    """Find the highest‑scoring density peak in *text*.

    Slides a *window_size*-char window across *text*, scores each by match
    density (1‑word +1, 2‑word +2).  Within the best‑scoring window,
    computes the **cluster midpoint** — the center of the span from the
    leftmost to rightmost match — so the snippet shows the maximum number
    of matches with balanced padding on both sides.

    3+‑word sub‑queries (the full phrase) are excluded from scoring —
    they're handled by Phase‑A highlight placement.

    Args:
        text: Text to scan.
        sub_queries: All sub‑queries (words, bigrams, full phrase).
        window_size: Width of the scoring window.
        consumed_spans: ``(start, end)`` spans already claimed by Phase‑A
            or earlier Phase‑B windows — these are skipped.

    Returns:
        ``(cluster_mid, best_score)`` where *cluster_mid* is the midpoint
        of the match cluster inside the best‑scoring window (character
        offset in *text*), and *best_score* is the sum of match weights
        inside that window.  Returns ``(0, 0)`` when no window scores
        above zero or all candidate positions are consumed.
    """
    if not text or not sub_queries:
        return 0, 0

    text_lower = text.lower()

    # Pre‑filter sub‑queries: only 1‑word and 2‑word matter for scoring.
    scoring_subs: List[Tuple[str, int]] = []  # (sub_lower, weight)
    for sub in sub_queries:
        n_words = len(sub.split())
        if n_words == 1:
            scoring_subs.append((sub.lower(), 1))
        elif n_words == 2:
            scoring_subs.append((sub.lower(), 2))

    if not scoring_subs:
        return 0, 0

    best_window_start = 0
    best_window_score = 0

    # ── Pass 1: slide window, find best‑scoring window ────────────────
    for i in range(len(text)):
        window_end = i + window_size

        # Skip if this window overlaps any already‑consumed span.
        if any(
            i < ce and window_end > cs for cs, ce in consumed_spans
        ):
            continue

        score = 0
        for sub_lower, weight in scoring_subs:
            search_start = i
            while True:
                pos = text_lower.find(sub_lower, search_start)
                if pos == -1 or pos + len(sub_lower) > window_end:
                    break
                score += weight
                search_start = pos + len(sub_lower)

        if score > best_window_score:
            best_window_score = score
            best_window_start = i

    if best_window_score == 0:
        return 0, 0

    # ── Pass 2: find cluster span within the best window ──────────────
    # Compute the midpoint of the match cluster so the snippet shows
    # the maximum number of matches with balanced padding.
    cluster_start: int | None = None
    cluster_end: int | None = None

    for sub_lower, _weight in scoring_subs:
        search_start = best_window_start
        while True:
            pos = text_lower.find(sub_lower, search_start)
            if pos == -1 or pos + len(sub_lower) > best_window_start + window_size:
                break
            if cluster_start is None or pos < cluster_start:
                cluster_start = pos
            match_end = pos + len(sub_lower)
            if cluster_end is None or match_end > cluster_end:
                cluster_end = match_end
            search_start = pos + len(sub_lower)

    if cluster_start is None or cluster_end is None:
        return 0, 0  # safety: no matches despite score > 0

    # Midpoint of the full match cluster — single matches naturally
    # center, clusters get equal padding on both sides.
    cluster_mid = (cluster_start + cluster_end) // 2
    return cluster_mid, best_window_score


def _extract_highlights(
    hidden_text: str,
    n_highlights: int,
    query_cleaned: str,
    sub_queries: List[str],
    snippet_window: int = _HIGHLIGHT_WINDOW,
    greedy_window: int = _GREEDY_WINDOW,
) -> List[str]:
    """Extract up to *n_highlights* snippets from the hidden region of a chunk.

    Two‑phase algorithm:

    **Phase A — full query match (1 slot).**  If ``query_cleaned`` (the
    stopword‑stripped user query) appears anywhere in *hidden_text*, a
    ±*snippet_window*‑char snippet is centered on the first occurrence
    and takes one highlight slot.

    **Phase B — greedy window placement (remaining slots).**  A sliding
    window of *greedy_window* chars is scored by match density
    (1‑word = +1, 2‑word = +2) and the highest‑scoring **non‑overlapping**
    windows are selected greedily until all slots are filled or no window
    scores > 0.

    Every snippet has matched sub‑queries uppercased for visibility.

    Args:
        hidden_text: The part of the chunk beyond ``_MAX_TEXT_CHARS``
            (i.e. the region NOT shown in the ``"text"`` field).
        n_highlights: Maximum number of highlights to generate
            (computed from ``ceil(hidden_chars / 500)``, capped [1, 5]).
        query_cleaned: Stopword‑stripped query used for Phase‑A matching.
        sub_queries: Output of ``generate_sub_queries(query_cleaned)``.
        snippet_window: Chars of context on each side of the Phase‑A match.
        greedy_window: Sliding‑window width for Phase‑B scoring.

    Returns:
        List of marked‑up snippet strings (matches uppercased).  May be shorter than
        *n_highlights* (or even empty) when not enough matches exist
        in *hidden_text*.  An empty list means ``highlights`` should be
        **suppressed** entirely in the result dict (absent key, not
        ``null``).
    """
    highlights: List[str] = []
    # Track consumed spans so Phase‑B windows don't overlap with Phase‑A
    # or with each other.
    consumed: Set[Tuple[int, int]] = set()

    # ── Phase A: full query match (2+ word queries only) ──────────────
    # A single‑word query gets no dedicated full‑query slot — Phase‑B
    # greedy placement already captures every occurrence and can spread
    # multiple highlights across different parts of the hidden text.
    if query_cleaned and len(query_cleaned.split()) >= 2 and n_highlights > 0:
        idx = hidden_text.lower().find(query_cleaned.lower())
        if idx != -1:
            match_end = idx + len(query_cleaned)
            start = max(0, idx - snippet_window)
            end = min(len(hidden_text), match_end + snippet_window)
            snippet = hidden_text[start:end]
            if start > 0:
                snippet = "…" + snippet
            if end < len(hidden_text):
                snippet = snippet + "…"
            snippet = _add_markers(snippet, sub_queries)
            highlights.append(snippet)
            consumed.add((start, end))
            n_highlights -= 1

    # ── Phase B: greedy window placement ───────────────────────────────
    while n_highlights > 0:
        cluster_mid, best_score = _find_best_window(
            hidden_text, sub_queries, greedy_window, consumed,
        )
        if best_score == 0:
            break

        # Center a ±snippet_window snippet on the cluster midpoint so
        # the outermost matches have balanced padding on both sides.
        # Single matches naturally center; clusters get even margins.
        start = max(0, cluster_mid - snippet_window)
        end = min(len(hidden_text), cluster_mid + snippet_window)
        snippet = hidden_text[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(hidden_text):
            snippet = snippet + "…"
        snippet = _add_markers(snippet, sub_queries)
        highlights.append(snippet)
        consumed.add((start, end))
        n_highlights -= 1

    return highlights
