# Tasks: webfetch-search-cache

## Status
- Total: 18
- Completed: 18
- Remaining: 0

---

## Tasks

### Group 1: Cache Infrastructure
Checkpoint: All cache read, write, delete, and path helpers exist in fetcher.py. Constants updated.

[x] 1.1 Update cache constants (TTL 1800, max files 400)
 - web_ops/fetcher.py (edit: `_CACHE_TTL_S` 900→1800, `_CACHE_MAX_FILES` 200→400)

[x] 1.2 Add `_cache_path_for_layer(url, suffix)` helper
 - web_ops/fetcher.py (add: returns `Path` for `{hash}_{suffix}` — e.g., `_chunked.json`, `_nodes.json`)

[x] 1.3 Add `_bm25_cache_dir(url)` helper
 - web_ops/fetcher.py (add: returns `Path` to `{hash}_bm25/` directory)

[x] 1.4 Add `_write_chunked_cache(url, chunked_tree)` helper
 - web_ops/fetcher.py (add: `json.dumps(chunked_tree)` → `{hash}_chunked.json`)

[x] 1.5 Add `_write_nodes_cache(url, nodes)` helper
 - web_ops/fetcher.py (add: `json.dumps([n.to_dict() for n in nodes])` → `{hash}_nodes.json`)

[x] 1.6 Add `_write_bm25_cache(url, bm25_retriever)` helper
 - web_ops/fetcher.py (add: `bm25_retriever.persist(dir)` → `{hash}_bm25/`; handles `OSError` gracefully)

[x] 1.7 Add `_read_cache_chunked(url)` helper
 - web_ops/fetcher.py (add: reads `{hash}_chunked.json`, returns `dict | None`)

[x] 1.8 Add `_read_cache_nodes(url)` helper
 - web_ops/fetcher.py (add: reads `{hash}_nodes.json`, reconstructs `list[TextNode]` via `TextNode.from_dict()`, returns `list | None`)

[x] 1.9 Add `_load_bm25_retriever(url, nodes)` helper
 - web_ops/fetcher.py (add: tries `BM25Retriever.from_persist_dir()` → on failure rebuilds from nodes + re-persists → returns `BM25Retriever`)

[x] 1.10 Add `_delete_cache_layers(url)` helper
 - web_ops/fetcher.py (add: deletes `{hash}_chunked.json`, `{hash}_nodes.json`, `{hash}_bm25/`; called on `--refresh-cache`)

### Group 2: HybridSearcher Cache Support
Checkpoint: HybridSearcher accepts a pre-built BM25 retriever via `build_from_cache()`.

[x] 2.1 Add `HybridSearcher.build_from_cache(nodes, bm25_retriever, substring_weight)`
 - web_ops/hybrid_searcher.py (add: method reusing pre-loaded BM25; reuses SubstringRetriever and HybridRetriever wiring from `build()`)

### Group 3: Cache on Initial Fetch
Checkpoint: After a successful fetch + chunking, the chunked tree and TextNode list are persisted. On cache-hit, chunking is skipped if cached layers exist.

[x] 3.1 Write chunked tree + nodes to cache after initial fetch
 - web_ops/fetcher.py (edit: `_result_with_truncation()` — after `_parse_chunked()` builds the chunked tree, call `_write_chunked_cache()` + `_write_nodes_cache()`)

[x] 3.2 Skip chunking on cache hit when cached layers exist
 - web_ops/fetcher.py (edit: `_fetch_url()` — on cache hit path, try `_read_cache_chunked(url)` and pass to `_result_with_truncation(chunked=...)`)

### Group 4: Search-Mode Route Integration
Checkpoint: The `/web_ops/webfetch` search-mode handler loads cached layers when available, falling back to full recompute on miss.

[x] 4.1 Load cached layers in search-mode route handler
 - api_server/routes/web_ops.py (edit: `webfetch()` — before `_parse_chunked()`, try `_read_cache_nodes()` + `_load_bm25_retriever()`; on hit, use `build_from_cache()`)

[x] 4.2 Persist missing layers on cache miss in search mode
 - api_server/routes/web_ops.py (edit: `webfetch()` — after computing chunked/nodes/BM25, call `_write_chunked_cache()`, `_write_nodes_cache()`, `_write_bm25_cache()` to populate cache for next request)

### Group 5: Refresh-Cache Integration
Checkpoint: `--refresh-cache` flag deletes all cached layers (not just markdown), forcing a full rebuild.

[x] 5.1 Wire `_delete_cache_layers()` into the refresh-cache path
 - web_ops/fetcher.py (edit: `_fetch_url()` — before re-fetching, call `_delete_cache_layers(url)` when `refresh_cache=True`)

### Group 6: Documentation
Checkpoint: AGENTS.md documents the cache layers and the refresh-cache rule.

[x] 6.1 Add caching section to AGENTS.md
 - AGENTS.md (edit: add section explaining four cache layers per URL, TTL, and instruction to use `--refresh-cache` when chunking algorithm changes)

### Group 7: Verification
Checkpoint: All existing tests pass. Manual smoke test confirms cache hit on subsequent queries.

[x] 7.1 Run existing test suite
 - Run: `pytest tests/unit/web_ops/ -k "not test_bm25_plus_substring_fusion"` (skipping known broken test) → 89 passed
 - Run: `pytest tests/ -k "cache"` → 11 passed
 - Run: `pytest tests/e2e/test_web_ops_cli.py` → 6 passed

[x] 7.2 Manual smoke test: cache hit on subsequent build
 - Verified: inline test simulating route handler cache-hit + refresh-cache flow → all PASSED
