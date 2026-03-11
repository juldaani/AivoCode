# Tasks: lsp-migration

## Status
- Total: 24
- Completed: 0
- Remaining: 24

---

## Tasks

### Group 1: Core Abstraction Module
Checkpoint: `lsp/` exposes stable protocols, types, exceptions, and manager cache.
Smoke-testable: no

Smoke test:
- N/A
- Reason: This group is foundational API/plumbing without a runnable backend.
- Deferred to: Group 2 (backend integration smoke test)

[ ] 1.1 Create `lsp/` package structure and module entrypoints
 - lsp/__init__.py (add: public exports surface)
 - lsp/protocol.py (add)
 - lsp/types.py (add)
 - lsp/exceptions.py (add)
 - lsp/manager.py (add)
 - lsp/backends/__init__.py (add)
 - lsp/config/__init__.py (add)

[ ] 1.2 Implement core shared types
 - lsp/types.py (edit: `JsonValue`, `JsonDict`, `FileChangeType`, `FileEvent`)

[ ] 1.3 Implement protocol and exception contracts
 - lsp/protocol.py (edit: `LspClient`, generic `LspProvider[ConfigT]`)
 - lsp/exceptions.py (edit: `LspError`, `LspMethodNotFound`, `LspResponseError`)

[ ] 1.4 Implement client cache/lifecycle manager
 - lsp/manager.py (edit: `LspManager.get_or_start()` keyed by `(provider_id, instance_id)`, `shutdown_all()`)

[ ] 1.5 Add multilspy backend skeleton modules
 - lsp/backends/multilspy/__init__.py (add: backend exports)
 - lsp/backends/multilspy/client.py (add: `MultilspyClientImpl` methods raise `NotImplementedError`)
 - lsp/backends/multilspy/providers/__init__.py (add: provider exports)
 - lsp/backends/multilspy/providers/java.py (add: `JavaProvider` stub)
 - lsp/backends/multilspy/providers/csharp.py (add: `CSharpProvider` stub)

### Group 2: lsp-client Backend + Basedpyright Provider
Checkpoint: A working `lsp-client` backend can start basedpyright, serve requests, and process watched-file notifications.
Smoke-testable: yes

Smoke test:
- Goal: Prove end-to-end LSP behavior through new abstraction using basedpyright.
- How: `conda run -n env-aivocode python tmp/validate_lsp_migration_g2.py`
- Input: Temporary workspace with a small Python file, valid basedpyright config, and one synthetic file-change event.
- Expect: Successful `textDocument/documentSymbol` response, successful `workspace/didChangeWatchedFiles` notify call, and clean shutdown.

[ ] 2.1 Implement `LspClientImpl` over lsp-client
 - lsp/backends/lsp_client/client.py (add: request/notify wrappers, `notify_did_change_watched_files()`)
 - lsp/backends/lsp_client/client.py (add: `is_running()` via manual `_running` flag)

[ ] 2.2 Add server-request handling through lsp-client capabilities
 - lsp/backends/lsp_client/client.py (edit: include `WithRespondConfigurationRequest` and `WithRespondWorkspaceFoldersRequest` mixins)

[ ] 2.3 Implement basedpyright provider and config
 - lsp/backends/lsp_client/providers/basedpyright.py (add: `BasedpyrightConfig`, `BasedpyrightProvider`, `get_instance_id()`, `create_client()`, `get_workspace_ignores()`)

[ ] 2.4 Move and integrate config resolution utilities
 - lsp/config/pyproject.py (add: `resolve_and_validate_config_file()` and TOML/JSON parsing helpers)
 - lsp/backends/lsp_client/providers/__init__.py (add: provider/config exports)
 - lsp/backends/lsp_client/__init__.py (add: backend exports)

[ ] 2.5 Run smoke test for Group 2
 - tmp/validate_lsp_migration_g2.py (add: temporary validation script)

### Group 3: Engine + Downstream Configuration Migration
Checkpoint: Engine uses only the new `lsp/` abstraction and downstream dynamic import settings point to new provider paths.
Smoke-testable: yes

Smoke test:
- Goal: Verify engine path from repo config → provider load → symbol query works without `lsp_server`.
- How: Run engine symbol query flow against one configured repository (existing entrypoint or a temporary script).
- Input: Repo configuration updated to `lsp.backends.lsp_client.providers.*` class paths.
- Expect: Engine initializes client through `LspManager`, returns symbols, and no `lsp_server` import is required.

[ ] 3.1 Migrate engine imports and typing to new API
 - engine/core.py (edit: replace `lsp_server` imports with `lsp` imports and type hints)

[ ] 3.2 Update dynamic provider/config class paths
 - Files defining `repo.lsp.provider_class` / `repo.lsp.config_class` (edit: replace `lsp_server.basedpyright.*` with `lsp.backends.lsp_client.providers.*`)

[ ] 3.3 Remove backward-compat assumptions
 - engine/core.py (edit: do not add alias/fallback import logic)
 - Any related runtime config defaults (edit: point directly to new paths)

[ ] 3.4 Verify file-watcher integration still maps events to LSP file events
 - engine/core.py (edit: preserve `FileEvent` and `FileChangeType` flow into `notify_did_change_watched_files()`)

[ ] 3.5 Run smoke test for Group 3
 - tmp/validate_lsp_migration_g3.py (add: temporary engine integration validation script, if needed)

### Group 4: Test Suite Migration and Rename
Checkpoint: Test suite is renamed to `tests/lsp/` and passes against the new module paths.
Smoke-testable: yes

Smoke test:
- Goal: Confirm migrated tests execute from new location with updated imports/config paths.
- How: `conda run -n env-aivocode pytest tests/lsp/test_generic.py tests/lsp/test_did_change_watched_files.py`
- Input: Updated test directory, imports, and `config.toml` provider module paths.
- Expect: Tests collect from `tests/lsp/` and pass without `lsp_server` imports.

[ ] 4.1 Rename test directory
 - tests/lsp_server/ (delete: move contents)
 - tests/lsp/ (add: renamed test directory)

[ ] 4.2 Update test fixtures/util imports
 - tests/lsp/conftest.py (edit: `LspClient`/`LspManager` imports and startup helper typing)
 - tests/lsp/helpers.py (edit: import types from `lsp`)

[ ] 4.3 Update provider-specific test imports
 - tests/lsp/test_basedpyright.py (edit: provider/config/manager imports)
 - tests/lsp/test_did_change_watched_files.py (edit: `FileChangeType` import)
 - tests/lsp/test_generic.py (edit: any direct/indirect path assumptions)

[ ] 4.4 Update test config dynamic module paths
 - tests/lsp/config.toml (edit: `provider_module = "lsp.backends.lsp_client.providers"`)
 - tests/lsp/config.py (edit: ensure dynamic import resolution aligns with new module layout)

[ ] 4.5 Run smoke test for Group 4
 - tests/lsp/ (run: targeted pytest commands above)

### Group 5: Cleanup, Docs Sweep, and Final Verification
Checkpoint: Legacy implementation is removed and migration is fully verified.
Smoke-testable: yes

Smoke test:
- Goal: Validate final migrated state with legacy code removed.
- How: `conda run -n env-aivocode pytest tests/lsp/` plus a repository search for `lsp_server` references.
- Input: Cleaned codebase with `lsp_server/` removed and docs/imports updated.
- Expect: Tests pass and no functional code paths still depend on `lsp_server`.

[ ] 5.1 Delete legacy LSP implementation
 - lsp_server/async_process.py (delete)
 - lsp_server/client.py (delete)
 - lsp_server/spec.py (delete)
 - lsp_server/provider.py (delete)
 - lsp_server/manager.py (delete)
 - lsp_server/types.py (delete)
 - lsp_server/__init__.py (delete)
 - lsp_server/how_to_use.py (delete)
 - lsp_server/basedpyright/ (delete)
 - lsp_server/ (delete: directory)

[ ] 5.2 Update remaining docs/comments/import references
 - Repository files referencing `lsp_server` (edit: replace with `lsp` where applicable)

[ ] 5.3 Verify acceptance criteria coverage explicitly
 - specs/lsp-migration/spec.md (check: each acceptance criterion satisfied by implemented changes)
 - specs/lsp-migration/api.md (check: protocol/contract parity)
 - specs/lsp-migration/migration.md (check: checklist closure)

[ ] 5.4 Run smoke test for Group 5
 - tests/lsp/ (run: full LSP test suite)
 - Repository-wide search (run: ensure no unintended `lsp_server` dependencies remain)
