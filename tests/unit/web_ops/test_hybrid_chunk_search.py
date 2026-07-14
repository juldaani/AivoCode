"""Unit tests for hybrid chunk search: markdown → chunks → search.

Tests cover:
- _flatten_chunks: chunked tree → TextNode list with metadata
- HybridSearcher: build index, search, pagination, scoring
- End-to-end: saved markdown → parse → flatten → search

Uses a real-world markdown file cached at ``tests/data/github_pi_subagents.md``
to avoid network dependencies.  The markdown was fetched once from
https://github.com/nicobailon/pi-subagents and checked in.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from web_ops.fetcher import _flatten_chunks, _parse_chunked
from web_ops.hybrid_searcher import HybridSearcher

# Path to saved test data (115 845 chars, 1 697 lines of markdown).
_TEST_MD = Path(__file__).resolve().parent.parent.parent.parent / "data" / "webfetch" / "github_pi_subagents.md"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def chunked_tree() -> dict:
    """Parse the saved markdown into a chunked tree — done once per module."""
    markdown = _TEST_MD.read_text(encoding="utf-8")
    return _parse_chunked(markdown)


@pytest.fixture(scope="module")
def flat_nodes(chunked_tree: dict) -> list:
    """Flatten the chunked tree into TextNode list — done once per module."""
    return _flatten_chunks(chunked_tree, include_headers=True)


@pytest.fixture(scope="module")
def searcher(flat_nodes: list) -> HybridSearcher:
    """Build and return a pre-indexed searcher — done once per module."""
    s = HybridSearcher()
    s.build(flat_nodes, vector_weight=0.65)
    return s


# ── _flatten_chunks ───────────────────────────────────────────────────────────


class TestFlattenChunks:
    """Flattening the chunked tree into TextNode objects with metadata."""

    def test_returns_non_empty_list(self, flat_nodes: list):
        """A real page should produce many chunks."""
        assert len(flat_nodes) > 10, (
            f"Expected >10 chunks from a real page, got {len(flat_nodes)}"
        )

    def test_every_node_has_text(self, flat_nodes: list):
        """Every TextNode must have non-empty text."""
        for node in flat_nodes:
            assert node.text, f"Node has empty text"
            assert isinstance(node.text, str)

    def test_every_node_has_metadata(self, flat_nodes: list):
        """Every TextNode must have heading_path and lines metadata."""
        for node in flat_nodes:
            meta = node.metadata or {}
            assert "heading_path" in meta, f"Missing heading_path in metadata: {meta}"
            assert isinstance(meta["heading_path"], list)
            assert "lines" in meta, f"Missing lines in metadata: {meta}"
            assert isinstance(meta["lines"], list)
            assert len(meta["lines"]) == 2

    def test_some_nodes_have_heading_path(self, flat_nodes: list):
        """At least some nodes should have a non-empty heading_path
        (the page has sections)."""
        with_path = [n for n in flat_nodes
                     if (n.metadata or {}).get("heading_path")]
        assert len(with_path) > 0, "No nodes have a heading_path"

    def test_header_prepended_to_text(self, flat_nodes: list):
        """When include_headers=True, text should contain breadcrumb for
        chunks under a heading."""
        breadcrumb_nodes = [
            n for n in flat_nodes
            if n.text.startswith("[") and "] " in n.text[:80]
        ]
        assert len(breadcrumb_nodes) > 0, (
            "No nodes have breadcrumb prefix in text"
        )

    def test_without_headers(self, chunked_tree: dict):
        """With include_headers=False, no breadcrumb prefix in text.

        A breadcrumb looks like ``[H1 > H2] actual text`` — ``[``, some text,
        `` > ``, some text, ``]``, then a space.  Plain markdown link syntax
        ``[text](url)`` must not trigger a false positive."""
        nodes_no_header = _flatten_chunks(chunked_tree, include_headers=False)
        for node in nodes_no_header:
            text = node.text
            if not text.startswith("["):
                continue
            # Find the first ']' — a breadcrumb has ' > ' before it.
            close = text.find("]")
            if close == -1:
                continue
            prefix = text[:close]
            assert " > " not in prefix, (
                f"Node has breadcrumb prefix despite include_headers=False: "
                f"{text[:80]}..."
            )

    def test_nodes_have_unique_ids(self, flat_nodes: list):
        """Every TextNode should have a unique node_id."""
        ids = [n.node_id for n in flat_nodes]
        assert len(ids) == len(set(ids)), "Duplicate node_id found"


# ── HybridSearcher ────────────────────────────────────────────────────────────


class TestHybridSearcherBuild:
    """Index building from TextNodes."""

    def test_build_does_not_raise(self, flat_nodes: list):
        """build() should succeed for a realistic node list."""
        s = HybridSearcher()
        s.build(flat_nodes, vector_weight=0.65)

    def test_build_custom_weight(self, flat_nodes: list):
        """build() should accept different vector weights."""
        s = HybridSearcher()
        s.build(flat_nodes, vector_weight=0.0)  # pure BM25
        s.build(flat_nodes, vector_weight=1.0)  # pure vector

    def test_search_before_build_raises(self):
        """search() before build() should raise RuntimeError."""
        s = HybridSearcher()
        with pytest.raises(RuntimeError, match="build.*before search"):
            s.search("test")


class TestHybridSearcherSearch:
    """Query execution and result formatting."""

    def test_search_returns_list_and_total(self, searcher: HybridSearcher):
        """search() returns (list_of_dicts, int)."""
        results, total = searcher.search("pi-subagents", top_k=5, page=0)
        assert isinstance(results, list)
        assert isinstance(total, int)
        assert total >= 0

    def test_result_dict_keys(self, searcher: HybridSearcher):
        """Each result dict must have score, text, heading_path, lines."""
        results, _ = searcher.search("readme", top_k=3, page=0)
        assert len(results) > 0, "Expected at least 1 result"
        for r in results:
            for key in ("score", "text", "heading_path", "lines"):
                assert key in r, f"Missing key '{key}' in result: {r}"
            assert isinstance(r["score"], float)
            assert isinstance(r["text"], str)
            assert isinstance(r["heading_path"], list)
            assert isinstance(r["lines"], list)

    def test_scores_are_non_increasing(self, searcher: HybridSearcher):
        """Results should be returned in descending score order."""
        results, _ = searcher.search("subagent", top_k=10, page=0)
        scores = [r["score"] for r in results]
        for i in range(1, len(scores)):
            assert scores[i] <= scores[i - 1], (
                f"Score increased at index {i}: {scores[i - 1]} → {scores[i]}"
            )

    def test_different_queries_different_rankings(self, searcher: HybridSearcher):
        """Different queries should produce different top results."""
        r1, _ = searcher.search("installation instructions", top_k=3, page=0)
        r2, _ = searcher.search("license copyright", top_k=3, page=0)
        texts1 = [r["text"][:80] for r in r1]
        texts2 = [r["text"][:80] for r in r2]
        assert texts1 != texts2, (
            f"Different queries returned same top results:\n  {texts1}"
        )

    def test_pagination_different_pages(self, searcher: HybridSearcher):
        """Page 0 and page 1 should return different results."""
        r0, total = searcher.search("subagent", top_k=3, page=0)
        r1, _ = searcher.search("subagent", top_k=3, page=1)
        expected_pages = max(1, math.ceil(total / 3))
        if expected_pages > 1:
            texts0 = [r["text"][:60] for r in r0]
            texts1 = [r["text"][:60] for r in r1]
            assert texts0 != texts1, (
                f"Page 0 and page 1 returned identical results"
            )

    def test_pagination_no_overlap(self, searcher: HybridSearcher):
        """Page 0 and page 1 should have no overlapping results."""
        r0, total = searcher.search("subagent", top_k=3, page=0)
        r1, _ = searcher.search("subagent", top_k=3, page=1)
        expected_pages = max(1, math.ceil(total / 3))
        if expected_pages > 1:
            scores0 = {r["text"][:60] for r in r0}
            scores1 = {r["text"][:60] for r in r1}
            assert scores0.isdisjoint(scores1), (
                f"Pages overlap: {scores0 & scores1}"
            )

    def test_page_beyond_range(self, searcher: HybridSearcher):
        """A page beyond the total should return empty results."""
        results, total = searcher.search("subagent", top_k=5, page=999)
        assert results == [], f"Expected empty results, got {len(results)}"

    def test_vector_weight_zero(self, flat_nodes: list):
        """Pure BM25 (vector_weight=0) should still return results."""
        s = HybridSearcher()
        s.build(flat_nodes, vector_weight=0.0)
        results, total = s.search("agent", top_k=3, page=0)
        assert len(results) > 0
        assert all(isinstance(r["score"], float) for r in results)

    def test_vector_weight_one(self, flat_nodes: list):
        """Pure vector (vector_weight=1) should still return results."""
        s = HybridSearcher()
        s.build(flat_nodes, vector_weight=1.0)
        results, total = s.search("agent", top_k=3, page=0)
        assert len(results) > 0
        assert all(isinstance(r["score"], float) for r in results)


# ── Smoke: end-to-end with simple queries ─────────────────────────────────────


class TestEndToEnd:
    """Full pipeline: markdown → parse → flatten → search."""

    def test_total_chunks_reasonable(self, flat_nodes: list):
        """A 115k-char GitHub page should produce a reasonable number of chunks.
        Navigation-heavy pages can produce many small chunks — allow 10–500."""
        assert 10 <= len(flat_nodes) <= 500, (
            f"Expected 10–500 chunks, got {len(flat_nodes)}"
        )

    def test_search_query_returns_top_hit(self, searcher: HybridSearcher):
        """The top hit should be a coherent chunk of text."""
        results, _ = searcher.search("pi-subagents", top_k=1, page=0)
        assert len(results) == 1
        r = results[0]
        assert r["score"] > 0.0, f"Top hit score is zero: {r}"
        assert len(r["text"]) > 20, f"Top hit text too short: {r['text'][:60]}"
