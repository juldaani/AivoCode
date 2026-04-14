# LSP Migration

## Summary

Migrate from the hand-rolled `lsp_server/` client implementation to the `lsp-client` library, behind a clean public interface (`LspClient` protocol, `LspServerProvider` protocol) that decouples consumers from any specific LSP client library. Adding a new language/LSP combo in the future requires only a new provider implementation — no plumbing changes.

## Scope

### In scope
- New `lsp/` package with public interface: `LspClient`, `LspServerProvider`, `WorkspaceLspManager`, `FileEvent`, `FileChangeType`
- `LspClientAdapter` — implements `LspClient` by wrapping `lsp-client` library's `Client`
- `BasedPyrightProvider` — implements `LspServerProvider`, creates `BasedpyrightClient` via `LspClientAdapter`
- `BasedPyrightConfig` + `resolve_and_validate_config_file()` + `get_workspace_ignores()` migrated from `lsp_server/basedpyright/`
- `WorkspaceLspManager` updated: uses `provider.create_client()` instead of `provider.spec()`
- `engine/` updated to import from `lsp` instead of `lsp_server`
- Config schema change: `provider_class` values point to `lsp.basedpyright.BasedPyrightProvider` etc.

### Out of scope
- Deleting or modifying `lsp_server/` — leave it untouched
- Adding typed LSP methods (hover, definition, etc.) to `LspClient` — those are future MCP server concerns
- Adding support for languages other than Python/basedpyright (but the interface must make it straightforward)
- Container-based server support (available in `lsp-client` but not needed now)
- Test migration (existing `lsp_server` tests remain; new tests for `lsp/` written as needed)

## Requirements

- `LspClient` protocol must be library-agnostic — no `lsp-client` types in its interface
- `LspServerProvider.create_client()` returns a `LspClient` — the provider owns construction details
- `notify_file_changes()` on `LspClient` must work via `lsp-client`'s public `notify()` API with `lsprotocol` types (no raw dict hacks)
- `WorkspaceLspManager` caches clients by `(provider.id, workspace_root)` — no `LspServerSpec` dependency
- `engine/core.py` changes are minimal: import path swap + `notify_did_change_watched_files` → `notify_file_changes`
- `BasedPyrightProvider.get_workspace_ignores()` keeps working identically (parses pyproject.toml / pyrightconfig.json)
- Dynamic class loading via `provider_class` / `config_class` strings continues to work

## Proposed Design

### Package structure

```
lsp/
├── __init__.py              # public exports
├── protocol.py              # LspClient + LspServerProvider protocols
├── types.py                 # FileEvent, FileChangeType
├── manager.py               # WorkspaceLspManager
├── adapter.py               # LspClientAdapter (wraps lsp-client Client)
├── basedpyright/
│   ├── __init__.py
│   ├── provider.py          # BasedPyrightProvider
│   └── config.py            # BasedPyrightConfig, resolve_and_validate_config_file
└── lsp_client_tst.py        # existing test script, keep as-is
```

### Key design decisions

1. **`LspClient` is a Protocol** — consumers depend on the interface, not the adapter. The `lsp-client` library is only imported inside `adapter.py` and `basedpyright/provider.py`.

2. **`LspClientAdapter` holds the lsp-client context manager open** — `start()` calls `__aenter__()`, `shutdown()` calls `__aexit__()`. This matches the current engine pattern of long-lived clients.

3. **`notify_file_changes()` implementation** — uses `client.notify(DidChangeWatchedFilesNotification(...))` with `lsprotocol` types. This is `lsp-client`'s public API, not an internal hack.

4. **`LspServerSpec` and `AsyncStdioLspProcess` are not in the public interface** — they remain in `lsp_server/` untouched. If a future provider needs something similar, it's an implementation detail inside that provider.

5. **Manager key** — `(provider.id, str(workspace_root.resolve()))`. Simple, stable, no spec dependency.

### Engine changes

```python
# BEFORE
from lsp_server import WorkspaceLspManager, AsyncLspClient, FileEvent, FileChangeType
self._path_to_client: dict[Path, AsyncLspClient] = {}
await client.notify_did_change_watched_files(lsp_events)

# AFTER
from lsp import WorkspaceLspManager, LspClient, FileEvent, FileChangeType
self._path_to_client: dict[Path, LspClient] = {}
await client.notify_file_changes(lsp_events)
```

Three lines change in `engine/core.py`.

### Config change

```toml
# BEFORE
provider_class = "lsp_server.basedpyright.BasedPyrightProvider"
config_class = "lsp_server.basedpyright.BasedPyrightConfig"

# AFTER
provider_class = "lsp.basedpyright.BasedPyrightProvider"
config_class = "lsp.basedpyright.BasedPyrightConfig"
```

### Adding a new language (future example)

Two files + config entry. No changes to engine, manager, or protocols.

```python
# lsp/gopls/provider.py
class GoplsProvider:
    id = "gopls"

    def create_client(self, workspace_root: Path, config: GoplsConfig) -> LspClient:
        from lsp_client import GoplsClient, LocalServer
        client = GoplsClient(
            server=LocalServer(program="gopls", args=["serve"]),
            workspace=workspace_root,
        )
        return LspClientAdapter(client)

    def get_workspace_ignores(self, workspace_root, config) -> list[str]:
        return []
```

## Acceptance Criteria

- [ ] `lsp/` package exists with all files listed above
- [ ] `LspClient` protocol defined with: `start()`, `shutdown()`, `is_running()`, `request()`, `notify()`, `notify_file_changes()`
- [ ] `LspServerProvider` protocol defined with: `id`, `create_client()`, `get_workspace_ignores()`
- [ ] `LspClientAdapter` implements `LspClient` wrapping `lsp-client`'s `Client`
- [ ] `BasedPyrightProvider.create_client()` returns a `LspClientAdapter` wrapping `BasedpyrightClient`
- [ ] `WorkspaceLspManager.get_or_start()` calls `provider.create_client()` → `client.start()`
- [ ] `engine/core.py` imports from `lsp` instead of `lsp_server`
- [ ] `engine/core.py` calls `notify_file_changes()` instead of `notify_did_change_watched_files()`
- [ ] `run_AivoCode.py` works end-to-end: engine starts, file watcher notifies LSP, `query_symbols()` returns results
- [ ] `lsp_server/` is unchanged (no files modified)
- [ ] `lsp/lsp_client_tst.py` still works (untouched)
- [ ] Config uses `lsp.basedpyright.*` class paths
