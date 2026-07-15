"""Hybrid search over text chunks — BM25 + exact substring matching.

What this module provides
- ``HybridRetriever``: Combines multiple ``BaseRetriever`` instances with
  weighted min-max score fusion (mirrors ``QueryFusionRetriever`` in
  ``_relative_score_fusion`` mode with ``num_queries=1``).
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

from typing import Dict, List, Optional, Tuple

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
_MAX_TEXT_CHARS = 1200

# Number of characters on each side of a substring match used to build
# the ``highlights`` snippet.
_HIGHLIGHT_WINDOW = 50

# Reciprocal Rank Fusion constant — controls how tightly top ranks are
# compressed.  k=60 is the standard from the RRF paper (Cormack et al.).
# Smaller k gives more spread between top results.
_RRF_K = 60


# ---------------------------------------------------------------------------
# HybridRetriever — mirrors QueryFusionRetriever._relative_score_fusion
# ---------------------------------------------------------------------------


class HybridRetriever(BaseRetriever):
    """Combine sub-retrievers with weighted min-max score fusion.

    Algorithm mirrors the built-in ``QueryFusionRetriever`` in
    ``_relative_score_fusion`` mode with ``num_queries=1``.

    When *labels* are provided (one per retriever), raw per‑retriever
    scores are stored in a ``_per_retriever_scores`` dict keyed by
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
        # Hash-keyed store for per-retriever scores, populated during
        # _retrieve() and read by HybridSearcher.search().
        # Dict[node_hash, Dict[label_key, raw_score]]
        self._per_retriever_scores: Dict[str, Dict[str, float]] = {}
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Run all retrievers, fuse scores, return top-k.

        Steps:
        1. Collect results from every sub-retriever.
        2. Reciprocal Rank Fusion (RRF) + min‑max normalise each retriever's
           scores to [0, 1], then multiply by weight.  RRF suppresses
           outlier dominance — a single 200‑match chunk no longer compresses
           every other result toward zero.
        3. Store normalised‑weighted per‑retriever scores in
           ``self._per_retriever_scores`` (same scale as fused score).
        4. Merge duplicates (keyed by ``node.hash``) — scores are summed.
        5. Sort by score descending, return top ``_top_k``.
        """
        # ── Step 1: Collect results ────────────────────────────────────────
        per_retriever: List[List[NodeWithScore]] = []
        for retriever in self._retrievers:
            per_retriever.append(retriever.retrieve(query_bundle))

        # ── Step 2: RRF normalise, multiply by weight ─────────────────────
        for nodes, weight in zip(per_retriever, self._weights):
            if not nodes:
                continue
            n = len(nodes)
            # RRF score for each rank position (1‑based).
            rrf_scores = [1.0 / (_RRF_K + rank) for rank in range(1, n + 1)]
            rrf_min, rrf_max = rrf_scores[-1], rrf_scores[0]

            if rrf_max == rrf_min:
                # Single node — normalised to 1.0.
                norm_scores = [1.0] * n if rrf_max > 0 else [0.0] * n
            else:
                norm_scores = [
                    (s - rrf_min) / (rrf_max - rrf_min) for s in rrf_scores
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
            ``text``, ``heading_path``, ``line_range``, and optionally
            ``highlights`` (when *text* was truncated to the ``_MAX_TEXT_CHARS``
            cap).  *total_matches* is the total number of results across all
            pages.
        """
        if self._retriever is None:
            raise RuntimeError(
                "HybridSearcher.build() must be called before search()"
            )

        # Preprocess once — store the cleaned query for the caller (e.g. API
        # layer) to include in the response.
        self.query_cleaned, _discard_removed = remove_stopwords(query)

        raw_results = self._retriever.retrieve(query)
        total = len(raw_results)
        page_slice = raw_results[page * top_k : (page + 1) * top_k]

        # Generate sub‑queries once for highlight extraction.
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

            # Truncate long text; add highlights when truncation occurs.
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

            if truncated and sub_queries:
                highlight = _extract_highlight(sub_queries, full_text)
                if highlight is not None:
                    result["highlights"] = highlight

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


def _extract_highlight(
    sub_queries: List[str],
    text: str,
    window: int = _HIGHLIGHT_WINDOW,
) -> Optional[str]:
    """Find the best substring match and return ``±window`` context.

    Sub‑queries are tried in **reverse order** (full phrase first =
    most specific) so the longest match controls the snippet position.

    Args:
        sub_queries: Output of ``generate_sub_queries``.
        text: Full (untruncated) chunk text.
        window: Characters of context on each side of the match.

    Returns:
        A snippet like ``"…context before match context after…"`` with
        ellipsis added when the snippet doesn't start/end at the text
        boundary.  Returns ``None`` when no sub‑query matches at all.
    """
    text_lower = text.lower()
    for sub in reversed(sub_queries):
        idx = text_lower.find(sub.lower())
        if idx == -1:
            continue
        start = max(0, idx - window)
        end = min(len(text), idx + len(sub) + window)
        snippet = text[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        return snippet
    return None
