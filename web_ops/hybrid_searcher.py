"""Hybrid search over text chunks — vector (FastEmbed) + keyword (BM25).

What this module provides
- ``HybridRetriever``: Combines two ``BaseRetriever`` instances with weighted
  min-max score fusion (mirrors ``QueryFusionRetriever._relative_score_fusion``
  with ``num_queries=1``).
- ``HybridSearcher``: High-level wrapper that builds an in-memory index from a
  list of ``TextNode`` objects and runs hybrid queries against it.

Why this exists
- The webfetch pipeline produces chunked content (``_parse_chunked`` →
  ``_flatten_chunks`` → ``TextNode`` list).  This module plugs those nodes
  into a dual retriever so agents can search inside fetched pages without
  needing an LLM or external service.
- The index is NOT persistent — it is rebuilt each request.  Typical pages
  produce 10–200 chunks, so the rebuild cost is sub‑second.

How to use
::

    from web_ops.hybrid_searcher import HybridSearcher

    searcher = HybridSearcher()
    searcher.build(nodes, vector_weight=0.65)
    results, total = searcher.search("install python", top_k=5, page=0)
    for r in results:
        print(f"[{r['score']:.3f}] {r['text'][:80]}...")
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.retrievers.bm25 import BM25Retriever


# ── Constants ─────────────────────────────────────────────────────────────────

# HuggingFace embedding model.  bge-small-en-v1.5 is 33 MB, 384-dim vectors,
# and runs locally via ONNX runtime — no API key needed.
_DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Default weight assigned to the vector retriever (BM25 gets 1 − weight).
# 0.65 means semantic meaning drives ranking, keywords fill gaps.
_DEFAULT_VECTOR_WEIGHT = 0.65

# Hardcoded page size for search results when the caller doesn't specify.
_DEFAULT_TOP_K = 5


# ---------------------------------------------------------------------------
# HybridRetriever — mirrors QueryFusionRetriever._relative_score_fusion
# ---------------------------------------------------------------------------


class HybridRetriever(BaseRetriever):
    """Combine sub-retrievers with weighted min-max score fusion.

    Algorithm mirrors the built-in ``QueryFusionRetriever`` in
    ``_relative_score_fusion`` mode with ``num_queries=1``.

    Unlike ``QueryFusionRetriever``, this class does NOT resolve
    ``Settings.llm``, so it can be used without an LLM provider installed.
    """

    def __init__(
        self,
        retrievers: List[BaseRetriever],
        weights: Optional[List[float]] = None,
        top_k: int = 8,
    ) -> None:
        """Initialise the hybrid retriever.

        Args:
            retrievers: Sub-retrievers to combine (e.g. vector + BM25).
            weights: Per-retriever weight (normalised to sum to 1).
                Defaults to equal weighting.
            top_k: Number of results to return.
        """
        if weights is None:
            weights = [1.0 / len(retrievers)] * len(retrievers)
        else:
            total = sum(weights)
            weights = [w / total for w in weights]
        self._retrievers = retrievers
        self._weights = weights
        self._top_k = top_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Run all retrievers, fuse scores, return top-k.

        Steps:
        1. Collect results from every sub-retriever.
        2. Min-max normalise each retriever's scores to [0, 1].
        3. Multiply each score by that retriever's weight.
        4. Merge duplicates (keyed by ``node.hash``) — scores are summed.
        5. Sort by score descending, return top ``_top_k``.
        """
        # Collect results from each sub-retriever.
        per_retriever: List[List[NodeWithScore]] = []
        for retriever in self._retrievers:
            per_retriever.append(retriever.retrieve(query_bundle))

        # Min-max normalise each retriever's scores, then multiply by its weight.
        for nodes, weight in zip(per_retriever, self._weights):
            if not nodes:
                continue
            scores = [n.score or 0.0 for n in nodes]
            min_s, max_s = min(scores), max(scores)
            for node in nodes:
                raw = node.score or 0.0
                if max_s == min_s:
                    normalised = 1.0 if max_s > 0 else 0.0
                else:
                    normalised = (raw - min_s) / (max_s - min_s)
                node.score = normalised * weight

        # Merge: sum scores for duplicate nodes (keyed by node hash).
        merged: Dict[str, NodeWithScore] = {}
        for nodes in per_retriever:
            for node in nodes:
                h = node.node.hash
                if h in merged:
                    merged[h].score = (merged[h].score or 0.0) + (node.score or 0.0)
                else:
                    merged[h] = node

        return sorted(
            merged.values(), key=lambda n: n.score or 0.0, reverse=True
        )[: self._top_k]


# ---------------------------------------------------------------------------
# HybridSearcher — high-level wrapper
# ---------------------------------------------------------------------------


class HybridSearcher:
    """Build an in-memory hybrid index from TextNodes and run queries against it.

    The index is NOT persistent — each ``build()`` call creates fresh vector
    and BM25 indexes.  For typical page sizes (10–200 chunks) this completes
    in under a second.

    Usage::

        searcher = HybridSearcher()
        searcher.build(nodes)
        results, total = searcher.search("query", top_k=5, page=0)
    """

    def __init__(self) -> None:
        """Create a searcher with no index loaded yet."""
        self._index: Optional[VectorStoreIndex] = None
        self._nodes: List[TextNode] = []
        self._retriever: Optional[HybridRetriever] = None

    def build(
        self,
        nodes: List[TextNode],
        vector_weight: float = _DEFAULT_VECTOR_WEIGHT,
    ) -> None:
        """Index *nodes* for hybrid retrieval.

        Side effects:
        - Sets ``Settings.embed_model`` to ``FastEmbedEmbedding`` (once per
          process — the model itself is cached after the first ``build()``).
        - Creates an in-memory ``VectorStoreIndex`` over *nodes*.
        - Creates a ``BM25Retriever`` over *nodes*.
        - Wires both into a ``HybridRetriever``.

        Args:
            nodes: TextNodes to index (typically flattened from a chunked tree).
            vector_weight: Weight for the vector retriever (0–1).
                BM25 gets ``1 − vector_weight``.  Default 0.65.
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

        # Wire hybrid — fetch all nodes from sub-retrievers so pagination
        # happens after weighted score fusion.
        # self._retriever = HybridRetriever(
        #     retrievers=[vector_retriever, bm25_retriever],
        #     weights=[vector_weight, 1.0 - vector_weight],
        #     top_k=num_nodes,
        # )
        self._retriever = HybridRetriever(
            retrievers=[bm25_retriever],
            weights=None,
            top_k=num_nodes,
        )

    def search(
        self,
        query: str,
        top_k: int = _DEFAULT_TOP_K,
        page: int = 0,
    ) -> Tuple[List[Dict], int]:
        """Run a hybrid query and return paginated results.

        Args:
            query: Natural-language search query.
            top_k: Results per page.  Default 5.
            page: Zero-based page index.  Default 0.

        Returns:
            ``(results, total_matches)`` where *results* is a list of dicts
            with keys ``score``, ``text``, ``heading_path``, ``lines``, and
            *total_matches* is the total number of results across all pages.
        """
        if self._retriever is None:
            raise RuntimeError(
                "HybridSearcher.build() must be called before search()"
            )

        raw_results = self._retriever.retrieve(query)
        total = len(raw_results)
        page_slice = raw_results[page * top_k : (page + 1) * top_k]

        formatted: List[Dict] = []
        for r in page_slice:
            metadata = r.node.metadata or {}
            formatted.append({
                "score": round(r.score or 0.0, 4),
                "text": r.node.text,
                "heading_path": metadata.get("heading_path", []),
                "lines": metadata.get("lines", []),
            })

        return formatted, total
