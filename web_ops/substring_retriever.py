"""Exact substring retriever — complements BM25 with literal text matching.

What this module provides
- ``SubstringRetriever``: a ``BaseRetriever`` that scores chunks by exact,
  case‑insensitive substring matching, using word‑level, bigram, and full‑query
  sub‑queries to capture both scattered keyword hits and ordered phrase hits.

Why this exists
- BM25 is a term‑based retriever — it matches `loading` when you search
  `load`, but it misses compound matches like `autoload` and `reload`.
- Substring matching catches **sub‑word matches** that BM25 cannot, as well as
  exact multi‑word phrases that BM25 treats as independent terms.
- By plugging this into ``HybridRetriever`` alongside BM25, we get a fused
  ranking where the two retrievers complement each other: BM25 covers
  stemmed/synonym matches, substring covers literal sub‑string and phrase hits.

How it works
1. Stopword removal: English function words (the, a, is, …) are stripped
   from the query before matching — they have near‑zero discriminative power
   and waste sub‑query slots.
2. Sub‑query generation: the cleaned query is expanded into individual words,
   bigrams (adjacent 2‑word phrases), and the full cleaned query.  No
   stemming, no lemmatisation — the matcher works on raw, literal text.
3. Scoring: for each chunk, every sub‑query that appears as a case‑insensitive
   substring contributes ``len(sub_query) * occurrence_count`` to the raw
   score.  Longer phrases get proportionally higher weight, and repeated
   matches accumulate.
4. Normalisation: the ``HybridRetriever`` applies min‑max normalisation and
   weight multiplication — this retriever returns raw, un‑normalised scores.

How to use
::

    from web_ops.substring_retriever import SubstringRetriever

    retriever = SubstringRetriever.from_defaults(nodes, similarity_top_k=50)
    results = retriever.retrieve("load auth")
    for r in results:
        print(f"[{r.score:.1f}] {r.node.text[:80]}")
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode


# ── Stopword list ──────────────────────────────────────────────────────────────
# Hardcoded English stopwords from the NLTK `stopwords` corpus — avoids a
# network-dependent ``nltk.download('stopwords')`` call at import time.
# The list has not changed meaningfully in 20 years and won't.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am",
    "an", "and", "any", "are", "aren", "as", "at",
    "be", "because", "been", "before", "being", "below", "between",
    "both", "but", "by",
    "can", "cannot", "could", "couldn",
    "did", "didn", "do", "does", "doesn", "doing", "don", "down", "during",
    "each",
    "few", "for", "from", "further",
    "had", "hadn", "has", "hasn", "have", "haven", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how",
    "i", "if", "in", "into", "is", "isn", "it", "its", "itself",
    "just",
    "ll",
    "m", "ma", "me", "might", "mightn", "more", "most", "must", "mustn",
    "my", "myself",
    "need", "needn", "no", "nor", "not", "now",
    "o", "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "ourselves", "out", "over", "own",
    "re",
    "s", "same", "shan", "she", "should", "shouldn", "so", "some",
    "such",
    "t", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too",
    "under", "until", "up",
    "ve", "very",
    "was", "wasn", "we", "were", "weren", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "won",
    "would", "wouldn",
    "y", "you", "your", "yours", "yourself", "yourselves",
})


# ── Public helper (used by HybridSearcher) ─────────────────────────────────────


def remove_stopwords(query: str) -> Tuple[str, List[str]]:
    """Strip English stopwords from *query*, returning ``(cleaned, removed)``.

    Words are matched case‑insensitively against ``_STOPWORDS``.
    The order of remaining words is preserved.

    Args:
        query: Raw user query (e.g. ``"how to configure the load auth module"``).

    Returns:
        ``(cleaned_query, removed_words)`` — *cleaned_query* may be empty if
        every word was a stopword; *removed_words* is the list of words that
        were dropped (preserving original case).
    """
    words = query.split()
    removed: List[str] = [w for w in words if w.lower() in _STOPWORDS]
    kept: List[str] = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(kept), removed


# ── Sub‑query generation ───────────────────────────────────────────────────────


def generate_sub_queries(cleaned_query: str) -> List[str]:
    """Expand a cleaned query into individual words, bigrams, and the full phrase.

    Strategy: words + bigrams + full query.  Always.  No config knobs.
    For an *n*‑word query this produces at most *2n* sub‑queries (exact
    count: *n* words + *n−1* bigrams + 1 full phrase when *n* > 1).

    Args:
        cleaned_query: Stopword‑stripped, whitespace‑normalised query string.

    Returns:
        Ordered list of sub‑query strings — words first, then bigrams,
        then the full query (if it differs from the single word).
    """
    words = cleaned_query.split()
    if not words:
        return []

    sub_queries: List[str] = list(words)  # individual words

    # Bigrams — sliding window of width 2.
    for i in range(len(words) - 1):
        sub_queries.append(" ".join(words[i : i + 2]))

    # Full query (only when it differs from a single‑word query and adds
    # information beyond the words + bigrams already emitted).
    if len(words) > 2:
        sub_queries.append(cleaned_query)

    return sub_queries


# ── Chunk scoring ──────────────────────────────────────────────────────────────


def score_chunk(
    sub_queries: List[str],
    chunk_text: str,
    heading_path: Optional[List[str]] = None,
    heading_boost_factor: float = 2.0,
) -> float:
    """Score one chunk against a set of sub-queries with optional heading boost.

    Each sub-query that appears as a case-insensitive substring contributes
    ``len(sub_query_in_chars) * occurrence_count`` to the raw score.

    When *heading_path* is provided, sub-queries that also appear in the
    heading hierarchy receive an additional boost of
    ``len(sub_query) * heading_occurrences * heading_boost_factor``.
    This rewards chunks whose section headings contain the search terms,
    since heading matches indicate higher topical importance.

    Occurrences are counted as non-overlapping matches (``str.find`` with
    advancing start index).

    Args:
        sub_queries: Output of ``generate_sub_queries``.
        chunk_text: The chunk's text content.
        heading_path: List of ancestor heading strings (e.g. ``["API", "Auth"]``).
            When provided, matches in headings get extra weight.
        heading_boost_factor: Multiplier for heading matches (default 2.0).
            A value of 2.0 means heading matches count double.

    Returns:
        Raw score (not normalised).  ``HybridRetriever`` applies min-max
        normalisation during fusion.
    """
    text_lower = chunk_text.lower()
    # Join headings with space to allow phrase matching across heading levels
    heading_text = " ".join(heading_path).lower() if heading_path else ""
    total: float = 0.0

    for sub in sub_queries:
        sub_lower = sub.lower()
        # Count non-overlapping matches in chunk text.
        text_count = 0
        start = 0
        while True:
            idx = text_lower.find(sub_lower, start)
            if idx == -1:
                break
            text_count += 1
            start = idx + len(sub_lower)

        # Count non-overlapping matches in heading path.
        heading_count = 0
        if heading_text:
            start = 0
            while True:
                idx = heading_text.find(sub_lower, start)
                if idx == -1:
                    break
                heading_count += 1
                start = idx + len(sub_lower)

        # Add base score from text matches
        if text_count > 0:
            total += len(sub) * text_count

        # Add boost from heading matches (independent of text matches)
        if heading_count > 0:
            boost = len(sub) * heading_count * heading_boost_factor
            total += boost

    return total


# ── Retriever ──────────────────────────────────────────────────────────────────


class SubstringRetriever(BaseRetriever):
    """Exact substring retriever — scores chunks by literal (case‑insensitive)
    sub‑string matches and returns ``NodeWithScore`` lists compatible with
    ``HybridRetriever``.

    Construction mirrors ``BM25Retriever`` — use the ``from_defaults``
    class method to create an instance pre‑loaded with nodes.
    """

    def __init__(
        self,
        nodes: List[TextNode],
        similarity_top_k: int = 100,
        heading_boost_factor: float = 2.0,
    ) -> None:
        """Initialise with a node list and a retrieval cap.

        Args:
            nodes: TextNodes to search (typically flattened from a chunked tree).
            similarity_top_k: Max number of results to return per query.
            heading_boost_factor: Multiplier for heading matches (default 2.0).
                A value of 2.0 means heading matches count double in scoring.
        """
        self._nodes_stored: List[TextNode] = nodes
        self._similarity_top_k: int = similarity_top_k
        self._heading_boost_factor: float = heading_boost_factor
        # Expose the cleaned query + removed words from the most recent
        # _retrieve() call so HybridSearcher can read them.
        self._last_cleaned_query: str = ""
        self._last_removed_words: List[str] = []
        super().__init__()

    @classmethod
    def from_defaults(
        cls,
        nodes: List[TextNode],
        similarity_top_k: int = 100,
        heading_boost_factor: float = 2.0,
    ) -> "SubstringRetriever":
        """Factory matching the ``BM25Retriever`` API.

        Args:
            nodes: TextNodes to index.
            similarity_top_k: Max results per query.
            heading_boost_factor: Multiplier for heading matches (default 2.0).

        Returns:
            A ready-to-use ``SubstringRetriever`` instance.
        """
        return cls(
            nodes,
            similarity_top_k=similarity_top_k,
            heading_boost_factor=heading_boost_factor,
        )

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Run the full substring-match pipeline.

        1. Strip stopwords.
        2. Generate sub-queries (words, bigrams, full phrase).
        3. Score every chunk (with heading boost if heading_path is present).
        4. Return top-*k* results sorted by raw score descending.

        Scores are **not** normalised here — ``HybridRetriever`` applies
        min-max normalisation during fusion.

        Returns:
            List of ``NodeWithScore``, sorted by ``score`` descending.
        """
        query = query_bundle.query_str
        cleaned, removed = remove_stopwords(query)
        self._last_cleaned_query = cleaned
        self._last_removed_words = removed

        sub_queries = generate_sub_queries(cleaned)
        results: List[NodeWithScore] = []

        for node in self._nodes_stored:
            # Extract heading_path from metadata for heading boost
            heading_path = node.metadata.get("heading_path", [])
            score = score_chunk(
                sub_queries,
                node.text,
                heading_path=heading_path,
                heading_boost_factor=self._heading_boost_factor,
            )
            if score > 0.0:
                results.append(NodeWithScore(node=node, score=score))

        results.sort(key=lambda r: r.score or 0.0, reverse=True)
        return results[: self._similarity_top_k]
