# Tasks: query-substring-search

## Status
- Total: 10
- Completed: 10
- Remaining: 0

---

## Tasks

### Group 1: SubstringRetriever core
Checkpoint: `SubstringRetriever` class scores chunks by substring match and returns `NodeWithScore[]` compatible with `HybridRetriever`.

- [x] 1.1 Create `SubstringRetriever` class implementing `BaseRetriever`
  - `web_ops/substring_retriever.py` (add)
  - Hardcoded `_STOPWORDS` frozenset (~179 English stopwords from NLTK)
  - `_remove_stopwords(query: str) -> str`: strip stopwords, whitespace-normalize
  - `_generate_sub_queries(cleaned_query: str) -> list[str]`: words + bigrams + full query
  - `_score_chunk(sub_queries: list[str], chunk_text: str) -> float`: weighted phrase-length scoring, case-insensitive
  - `_retrieve(query_bundle) -> list[NodeWithScore]`: full pipeline — preprocess → sub-queries → score all chunks → min-max normalize → return

- [x] 1.2 Implement weighted scoring with phrase-length priority
  - `web_ops/substring_retriever.py` (edit)
  - Longer sub-query matches contribute higher score: weight = `len(sub_query_in_chars) * occurrence_count`
  - Score = sum over all matching sub-queries, per chunk
  - Min-max normalize final scores to [0, 1] for HybridRetriever fusion

- [x] 1.3 Export `SubstringRetriever` from `web_ops/__init__.py`
  - `web_ops/__init__.py` (edit)
  - Add to existing exports alongside `HybridSearcher`

### Group 2: Wire into HybridSearcher
Checkpoint: `HybridSearcher.build()` creates both BM25 and Substring retrievers, fusing with default 0.6/0.4 weights.

- [x] 2.1 Wire `SubstringRetriever` into `HybridSearcher.build()`
  - `web_ops/hybrid_searcher.py` (edit: `build()` method)
  - Add `substring_weight` parameter (default `_DEFAULT_SUBSTRING_WEIGHT = 0.4`)
  - BM25 weight becomes `1.0 - substring_weight` (default 0.6)
  - Build `SubstringRetriever` over the same nodes, pass to `HybridRetriever` as second retriever
  - Update module docstring and `build()` docstring to reflect three-retriever design

- [x] 2.2 Update `HybridSearcher.search()` response metadata
  - `web_ops/hybrid_searcher.py` (edit: `search()` method)
  - Include `query_cleaned` (after stopword removal) and `removed_stopwords` in result dicts
  - Expose these through `HybridSearcher` so the API layer can include them in response `info`

### Group 3: API and CLI
Checkpoint: Users can pass `--query-substring-weight` via CLI, and responses surface the cleaned query.

- [x] 3.1 Add `substring_weight` field to API request model
  - `api_server/routes/web_ops.py` (edit: request body model)
  - Add `query_substring_weight: float = 0.4` alongside existing `query_vector_weight`
  - Pass to `searcher.build()` as `substring_weight`
  - Include `query_cleaned` and `removed_stopwords` in search-mode response

- [x] 3.2 Add `--query-substring-weight` CLI argument
  - `cli/commands/webfetch.py` (edit)
  - New `--query-substring-weight` float arg, default 0.4
  - Sent as `query_substring_weight` in request body

### Group 4: Tests
Checkpoint: All existing tests pass; new tests cover substring matching, stopword removal, bigram generation, fusion scoring, and CLI wiring.

- [x] 4.1 Unit tests for `SubstringRetriever` internals
  - `tests/unit/web_ops/test_hybrid_chunk_search.py` (edit: add test class)
  - `test_stopword_removal`: "how to configure the load auth module" → "configure load auth module"
  - `test_sub_query_generation_words_bigrams_full`: verify output for 3-word and 5-word queries
  - `test_scoring_weighted_by_phrase_length`: full phrase scores higher than individual words
  - `test_case_insensitive`: "Load" matches "reload" and "autoload"
  - `test_no_match_returns_zero`: irrelevant query scores 0
  - `test_empty_query_handling`: empty after stopword removal → no sub-queries → zero scores
  - `test_min_max_normalization`: scores fall in [0, 1] range

- [x] 4.2 Integration tests for fused search results
  - `tests/unit/web_ops/test_hybrid_chunk_search.py` (edit: add test class)
  - `test_bm25_plus_substring_fusion`: fused search finds exact substrings that BM25 alone misses
  - `test_substring_weight_zero`: weight=0 → pure BM25, same as before
  - `test_substring_weight_one`: weight=1.0 → pure substring, no BM25 contribution
  - `test_result_metadata_includes_cleaned_query`: `query_cleaned` and `removed_stopwords` present

- [x] 4.3 CLI e2e test
  - `tests/e2e/test_web_ops_cli.py` (edit: add test)
  - `--query "load auth" --query-substring-weight 0.3` produces valid search-mode response
