"""Unit tests for hybrid chunk search: markdown → chunks → search.

Tests cover:
- _flatten_chunks: chunked tree → TextNode list with metadata
- HybridSearcher: build index, search, pagination, scoring
- SubstringRetriever: stopword removal, sub-query generation,
  weighted scoring, case insensitivity, normalisation
- End-to-end: saved markdown → parse → flatten → search

Uses a real-world markdown file cached at ``tests/data/webfetch/github_pi_subagents.md``
to avoid network dependencies.  The markdown was fetched once from
https://github.com/nicobailon/pi-subagents and checked in.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from web_ops.fetcher import _flatten_chunks, _parse_chunked
from web_ops.hybrid_searcher import HybridSearcher
from web_ops.substring_retriever import (
    SubstringRetriever,
    generate_sub_queries,
    remove_stopwords,
    score_chunk,
)

# Path to saved test data (115 845 chars, 1 697 lines of markdown).
_TEST_MD = Path(__file__).resolve().parent.parent.parent / "data" / "webfetch" / "github_pi_subagents.md"


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
        """Each result dict must have score_fused, score_bm25, score_substring,
        n_substring_matches, text, line_range."""
        results, _ = searcher.search("readme", top_k=3, page=0)
        assert len(results) > 0, "Expected at least 1 result"
        for r in results:
            for key in ("score_fused", "score_bm25", "score_substring",
                        "n_substring_matches",
                        "text", "line_range"):
                assert key in r, f"Missing key '{key}' in result: {r}"
            assert isinstance(r["score_fused"], float)
            assert isinstance(r["score_bm25"], float)
            assert isinstance(r["n_substring_matches"], int)
            assert isinstance(r["text"], str)
            assert isinstance(r["line_range"], list)

    def test_scores_are_non_increasing(self, searcher: HybridSearcher):
        """Results should be returned in descending score order."""
        results, _ = searcher.search("subagent", top_k=10, page=0)
        scores = [r["score_fused"] for r in results]
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
        assert all(isinstance(r["score_fused"], float) for r in results)

    def test_vector_weight_one(self, flat_nodes: list):
        """Pure vector (vector_weight=1) should still return results."""
        s = HybridSearcher()
        s.build(flat_nodes, vector_weight=1.0)
        results, total = s.search("agent", top_k=3, page=0)
        assert len(results) > 0
        assert all(isinstance(r["score_fused"], float) for r in results)


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
        assert r["score_fused"] > 0.0, f"Top hit score is zero: {r}"
        assert len(r["text"]) > 20, f"Top hit text too short: {r['text'][:60]}"


# ── SubstringRetriever internals ──────────────────────────────────────────────


class TestSubstringRetrieverInternals:
    """Unit tests for stopword removal, sub-query generation, and scoring."""

    # ── stopword removal ─────────────────────────────────────────────────

    def test_stopword_removal(self) -> None:
        """Common stopwords are stripped, meaningful terms kept."""
        cleaned, removed = remove_stopwords(
            "how to configure the load auth module"
        )
        assert cleaned == "configure load auth module"
        assert set(removed) == {"how", "to", "the"}

    def test_stopword_removal_preserves_order(self) -> None:
        """Remaining words keep their original order."""
        cleaned, _ = remove_stopwords("the quick brown fox")
        assert cleaned == "quick brown fox"

    def test_stopword_removal_all_stopwords(self) -> None:
        """When every word is a stopword, the cleaned query is empty."""
        cleaned, removed = remove_stopwords("the a of in")
        assert cleaned == ""
        assert len(removed) == 4

    def test_stopword_removal_no_stopwords(self) -> None:
        """When no stopwords, query is unchanged."""
        cleaned, removed = remove_stopwords("load auth module")
        assert cleaned == "load auth module"
        assert removed == []

    def test_stopword_removal_case_insensitive(self) -> None:
        """Stopword matching is case‑insensitive."""
        cleaned, removed = remove_stopwords("How To Configure THE Load Auth")
        assert cleaned == "Configure Load Auth"
        assert set(removed) == {"How", "To", "THE"}

    def test_stopword_removal_empty_input(self) -> None:
        """Empty input produces empty output."""
        cleaned, removed = remove_stopwords("")
        assert cleaned == ""
        assert removed == []

    # ── sub-query generation ─────────────────────────────────────────────

    def test_sub_query_generation_single_word(self) -> None:
        """A single word produces just that word."""
        subs = generate_sub_queries("load")
        assert subs == ["load"]

    def test_sub_query_generation_two_words(self) -> None:
        """Two words → words + bigram."""
        subs = generate_sub_queries("load auth")
        assert subs == ["load", "auth", "load auth"]

    def test_sub_query_generation_three_words(self) -> None:
        """Three words → words + bigrams + full phrase."""
        subs = generate_sub_queries("load auth module")
        assert subs == [
            "load", "auth", "module",
            "load auth", "auth module",
            "load auth module",
        ]

    def test_sub_query_generation_five_words(self) -> None:
        """Bigram count = n − 1; full phrase included."""
        subs = generate_sub_queries("a b c d e")
        assert subs[:5] == ["a", "b", "c", "d", "e"]          # words
        assert subs[5:9] == ["a b", "b c", "c d", "d e"]      # bigrams
        assert subs[-1] == "a b c d e"                         # full phrase
        assert len(subs) == 10  # 5 words + 4 bigrams + 1 full

    def test_sub_query_generation_empty(self) -> None:
        """Empty input → empty output."""
        subs = generate_sub_queries("")
        assert subs == []

    # ── scoring ──────────────────────────────────────────────────────────

    def test_scoring_weighted_by_phrase_length(self) -> None:
        """A longer match contributes proportionally more to the score."""
        subs = ["load", "auth", "load auth"]
        score_single = score_chunk(["load"], "reload module")
        score_long = score_chunk(["load auth"], "the load auth pattern")
        # "load auth" (9 chars) should score higher than "load" (4 chars)
        # per occurrence, assuming same count.
        assert score_long > score_single

    def test_scoring_multiple_occurrences(self) -> None:
        """Repeated substring matches accumulate."""
        score_once = score_chunk(["load"], "the reload function")
        score_twice = score_chunk(
            ["load"], "reload the autoload module"
        )
        assert score_twice > score_once

    def test_scoring_accumulates_sub_queries(self) -> None:
        """Multiple matching sub-queries sum their contributions."""
        score_one = score_chunk(["auth"], "auth module documentation")
        score_both = score_chunk(
            ["auth", "module"],
            "auth module documentation"
        )
        assert score_both > score_one

    def test_case_insensitive_matching(self) -> None:
        """Substring matching is case‑insensitive."""
        score_lower = score_chunk(["load"], "reLOAD the CLASS")
        score_upper = score_chunk(["LOAD"], "reload the class")
        assert score_lower == score_upper

    def test_no_match_returns_zero(self) -> None:
        """An irrelevant query scores zero."""
        score = score_chunk(["xyzzy"], "this chunk has no match")
        assert score == 0.0

    def test_empty_sub_queries_returns_zero(self) -> None:
        """No sub‑queries means zero score."""
        score = score_chunk([], "some chunk text")
        assert score == 0.0

    # ── SubstringRetriever._retrieve ─────────────────────────────────────

    def test_retrieve_returns_node_with_score(self) -> None:
        """_retrieve returns NodeWithScore objects in descending order."""
        from llama_index.core.schema import QueryBundle, TextNode

        nodes = [
            TextNode(text="the reload function example"),
            TextNode(text="auth module configuration"),
            TextNode(text="unrelated bananas"),
        ]
        retriever = SubstringRetriever.from_defaults(
            nodes, similarity_top_k=10
        )
        results = retriever.retrieve(QueryBundle("load"))
        assert len(results) == 1
        assert results[0].score > 0.0
        assert "reload" in results[0].node.text

    def test_retrieve_top_k_caps_results(self) -> None:
        """Only top_k results are returned."""
        from llama_index.core.schema import QueryBundle, TextNode

        nodes = [
            TextNode(text=f"chunk{i} load") for i in range(10)
        ]
        retriever = SubstringRetriever.from_defaults(
            nodes, similarity_top_k=3
        )
        results = retriever.retrieve(QueryBundle("load"))
        assert len(results) == 3

    def test_retrieve_empty_query_all_stopwords(self) -> None:
        """All‑stopword query returns no results."""
        from llama_index.core.schema import QueryBundle, TextNode

        nodes = [
            TextNode(text="some content"),
        ]
        retriever = SubstringRetriever.from_defaults(
            nodes, similarity_top_k=10
        )
        results = retriever.retrieve(QueryBundle("the a of in"))
        assert results == []

    def test_retrieve_no_match(self) -> None:
        """No matching substring → empty results."""
        from llama_index.core.schema import QueryBundle, TextNode

        nodes = [
            TextNode(text="alpha beta gamma"),
        ]
        retriever = SubstringRetriever.from_defaults(
            nodes, similarity_top_k=10
        )
        results = retriever.retrieve(QueryBundle("xyzzy"))
        assert results == []


# ── Fused search integration tests ────────────────────────────────────────────


class TestFusedSearch:
    """Integration tests for BM25 + substring fusion via HybridSearcher."""

    def test_bm25_plus_substring_fusion(self, flat_nodes: list) -> None:
        """Fused search ranks results from both retrievers."""
        s = HybridSearcher()
        s.build(flat_nodes, substring_weight=0.4)
        results, total = s.search("agent", top_k=10, page=0)
        assert total > 0
        assert len(results) > 0
        assert all(isinstance(r["score_fused"], float) for r in results)
        # Scores should be in descending order.
        scores = [r["score_fused"] for r in results]
        for i in range(1, len(scores)):
            assert scores[i] <= scores[i - 1]

    def test_substring_weight_zero_pure_bm25(self, flat_nodes: list) -> None:
        """weight=0 → pure BM25, substring has zero influence."""
        s = HybridSearcher()
        s.build(flat_nodes, substring_weight=0.0)
        results, total = s.search("subagent", top_k=5, page=0)
        assert len(results) > 0
        assert total > 0

    def test_substring_weight_one_pure_substring(self, flat_nodes: list) -> None:
        """weight=1.0 → pure substring, BM25 has zero influence."""
        s = HybridSearcher()
        s.build(flat_nodes, substring_weight=1.0)
        results, total = s.search("subagent", top_k=5, page=0)
        assert len(results) > 0
        assert total > 0

    def test_search_exposes_cleaned_query(self, flat_nodes: list) -> None:
        """HybridSearcher.query_cleaned is set after search()."""
        s = HybridSearcher()
        s.build(flat_nodes, substring_weight=0.4)
        s.search("how to configure the load auth", top_k=3, page=0)
        assert s.query_cleaned == "configure load auth"

    def test_search_exposes_cleaned_query_no_stopwords(self, flat_nodes: list) -> None:
        """query_cleaned matches original when no stopwords present."""
        s = HybridSearcher()
        s.build(flat_nodes, substring_weight=0.4)
        s.search("subagent", top_k=3, page=0)
        assert s.query_cleaned == "subagent"
