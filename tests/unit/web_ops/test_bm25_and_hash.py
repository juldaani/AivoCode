"""Tests for BM25 keyword extraction.

These tests verify the BM25 CSR matrix traversal functionality.
These tests serve as snapshot tests to detect regressions after fixes.

Note: Node hash None handling is difficult to test directly because
TextNode.hash is a read-only computed property. The fix is defensive
programming that adds a fallback to node_id if hash is ever None.
"""

from __future__ import annotations

import pytest

from web_ops.fetcher import _get_top_bm25_keywords


class TestBM25KeywordExtraction:
    """Test _get_top_bm25_keywords function with various corpus sizes."""

    def test_small_corpus_basic(self) -> None:
        """Test BM25 keyword extraction with a small 3-document corpus."""
        import bm25s
        import Stemmer

        # Small test corpus
        corpus = [
            "python programming language",
            "java programming language",
            "python java comparison",
        ]

        stemmer = Stemmer.Stemmer("english")
        token_ids, vocab = bm25s.tokenize(
            corpus, stopwords="en", stemmer=stemmer, return_ids=True,
        )
        id_to_token = {v: k for k, v in vocab.items()}

        bm25 = bm25s.BM25()
        bm25.index(token_ids)

        # Extract top-3 keywords per document
        results = _get_top_bm25_keywords(bm25, token_ids, id_to_token, top_n=3)

        # Verify structure
        assert len(results) == 3, f"Expected 3 documents, got {len(results)}"
        for i, keywords in enumerate(results):
            assert isinstance(keywords, list), f"Doc {i}: keywords should be a list"
            assert len(keywords) <= 3, f"Doc {i}: should have at most 3 keywords"
            for kw in keywords:
                assert isinstance(kw, str), f"Doc {i}: keyword should be string"
                assert len(kw) > 0, f"Doc {i}: keyword should not be empty"

        # Verify that keywords are actually from the vocabulary
        all_keywords = {kw for doc_kws in results for kw in doc_kws}
        assert all_keywords.issubset(set(id_to_token.values())), (
            f"Keywords {all_keywords} not in vocabulary {set(id_to_token.values())}"
        )

    def test_medium_corpus_performance(self) -> None:
        """Test BM25 keyword extraction with a medium 50-document corpus."""
        import bm25s
        import Stemmer
        import time

        # Medium corpus: 50 documents
        corpus = [
            f"document {i} about topic {i % 10} with some additional text"
            for i in range(50)
        ]

        stemmer = Stemmer.Stemmer("english")
        token_ids, vocab = bm25s.tokenize(
            corpus, stopwords="en", stemmer=stemmer, return_ids=True,
        )
        id_to_token = {v: k for k, v in vocab.items()}

        bm25 = bm25s.BM25()
        bm25.index(token_ids)

        # Time the extraction
        start = time.time()
        results = _get_top_bm25_keywords(bm25, token_ids, id_to_token, top_n=3)
        elapsed = time.time() - start

        # Verify structure
        assert len(results) == 50
        for keywords in results:
            assert isinstance(keywords, list)
            assert len(keywords) <= 3

        # Performance check: should complete in reasonable time
        # (This is a baseline; after optimization it should be much faster)
        print(f"\nBM25 keyword extraction for 50 docs took {elapsed:.3f}s")
        assert elapsed < 10.0, f"Extraction took too long: {elapsed:.3f}s"

    def test_single_document(self) -> None:
        """Test BM25 keyword extraction with a single document."""
        import bm25s
        import Stemmer

        corpus = ["python programming language tutorial"]

        stemmer = Stemmer.Stemmer("english")
        token_ids, vocab = bm25s.tokenize(
            corpus, stopwords="en", stemmer=stemmer, return_ids=True,
        )
        id_to_token = {v: k for k, v in vocab.items()}

        bm25 = bm25s.BM25()
        bm25.index(token_ids)

        results = _get_top_bm25_keywords(bm25, token_ids, id_to_token, top_n=3)

        assert len(results) == 1
        assert isinstance(results[0], list)
        assert len(results[0]) <= 3

    def test_empty_document(self) -> None:
        """Test BM25 keyword extraction with an empty document."""
        import bm25s
        import Stemmer

        corpus = ["", "python programming", ""]

        stemmer = Stemmer.Stemmer("english")
        token_ids, vocab = bm25s.tokenize(
            corpus, stopwords="en", stemmer=stemmer, return_ids=True,
        )
        id_to_token = {v: k for k, v in vocab.items()}

        bm25 = bm25s.BM25()
        bm25.index(token_ids)

        results = _get_top_bm25_keywords(bm25, token_ids, id_to_token, top_n=3)

        assert len(results) == 3
        # Empty documents should have empty keyword lists
        assert results[0] == [] or len(results[0]) == 0
        assert results[2] == [] or len(results[2]) == 0
        # Non-empty document should have keywords
        assert len(results[1]) > 0

    def test_top_n_parameter(self) -> None:
        """Test that top_n parameter correctly limits keywords."""
        import bm25s
        import Stemmer

        corpus = [
            "python programming language tutorial guide",
            "java programming language tutorial",
        ]

        stemmer = Stemmer.Stemmer("english")
        token_ids, vocab = bm25s.tokenize(
            corpus, stopwords="en", stemmer=stemmer, return_ids=True,
        )
        id_to_token = {v: k for k, v in vocab.items()}

        bm25 = bm25s.BM25()
        bm25.index(token_ids)

        # Test different top_n values
        for top_n in [1, 2, 5, 10]:
            results = _get_top_bm25_keywords(bm25, token_ids, id_to_token, top_n=top_n)
            assert len(results) == 2
            for keywords in results:
                assert len(keywords) <= top_n


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
