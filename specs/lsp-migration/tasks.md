# Tasks: lsp-migration

## Status
- Total: 9
- Completed: 9
- Remaining: 0

---

## Tasks

### Group 1: Public Interface
Checkpoint: Protocols and types defined — all other code can reference them

[x] 1.1 Create `lsp/` package with protocols and types
 - lsp/__init__.py (add — public exports)
 - lsp/protocol.py (add — LspClient and LspServerProvider protocols)
 - lsp/file_events.py (add — FileEvent, FileChangeType)

### Group 2: Adapter
Checkpoint: LspClient can be backed by the lsp-client library

[x] 2.1 Implement LspClientAdapter
 - lsp/adapter.py (add — wraps lsp-client Client, implements LspClient)

### Group 3: Basedpyright Provider
Checkpoint: Working basedpyright provider that creates LspClient via lsp-client

[x] 3.1 Create basedpyright provider package
 - lsp/basedpyright/__init__.py (add — exports)

[x] 3.2 Migrate BasedPyrightConfig and resolve_and_validate_config_file
 - lsp/basedpyright/config.py (add — migrated from lsp_server/basedpyright/config.py)

[x] 3.3 Implement BasedPyrightProvider
 - lsp/basedpyright/provider.py (add — create_client() returns LspClientAdapter, get_workspace_ignores() migrated)

### Group 4: Manager
Checkpoint: WorkspaceLspManager works with new provider.create_client() flow

[x] 4.1 Implement WorkspaceLspManager
 - lsp/manager.py (add — uses provider.create_client() → client.start(), caches by (provider.id, workspace_root))

### Group 5: Engine Integration
Checkpoint: Engine runs against new `lsp/` package, end-to-end working

[x] 5.1 Update engine to import from `lsp` instead of `lsp_server`
 - engine/core.py (edit: import path swap, AsyncLspClient → LspClient, notify_did_change_watched_files → notify_file_changes)

[x] 5.2 Update config to reference new provider paths
 - config_aivocode.toml (edit: provider_class and config_class values from lsp_server.basedpyright.* → lsp.basedpyright.*)

### Group 6: Verification
Checkpoint: End-to-end smoke test confirms migration works

[x] 6.1 Run end-to-end verification
 - Verify `lsp/lsp_client_tst.py` still works (untouched)
 - Verify engine starts, file watcher notifies LSP, query_symbols() returns results
 - Verify `lsp_server/` is unchanged
