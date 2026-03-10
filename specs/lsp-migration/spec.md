# LSP Migration

## Summary

Replace the custom `lsp_server/` implementation with the `lsp-client` library while introducing a clean abstraction layer (`lsp/`) that supports future multi-backend integration (e.g., multilspy for broader language coverage).

**Why:**
- `lsp-client` is battle-tested and production-ready
- Avoid maintaining custom JSON-RPC transport and LSP lifecycle code
- Enable future support for multiple LSP client libraries through a unified interface

## Scope

### In scope
- Create `lsp/` module with protocol-based abstraction
- Implement `lsp/backends/lsp_client/` backend (full)
- Create `lsp/backends/multilspy/` backend (skeleton only)
- Migrate Python language support (basedpyright)
- Update `engine/core.py` to use new `lsp/` module
- Update test files to use new imports
- Delete `lsp_server/` directory after migration

### Out of scope
- Full multilspy implementation
- Additional language servers beyond basedpyright
- New LSP features (hover, completion, etc.)

## Requirements

### Functional Requirements
1. **LspClient Protocol**: Stable interface for LSP operations (request, notify, shutdown, is_running)
2. **LspProvider Protocol**: Factory pattern for creating language-specific clients
3. **LspManager**: Client caching by (provider_id, instance_id) to avoid duplicate servers
4. **File watching support**: `notify_did_change_watched_files()` must work
5. **Python support**: Basedpyright provider with config file resolution

### Non-Functional Requirements
1. **Backward compatibility**: `engine/core.py` usage pattern preserved
2. **Extensibility**: Easy to add new providers and backends
3. **Type safety**: Full type annotations on public API
4. **No auto-download**: Explicit server installation required (matches lsp-client philosophy)

## Proposed Design

### Architecture

```
lsp/
├── __init__.py                 # Public exports
├── protocol.py                 # LspClient, LspProvider protocols
├── types.py                    # FileEvent, FileChangeType, JsonDict, etc.
├── exceptions.py               # LspError, LspMethodNotFound
├── manager.py                  # LspManager (client cache)
│
├── backends/
│   ├── __init__.py
│   │
│   ├── lsp_client/             # lsp-client backend (FULL)
│   │   ├── __init__.py
│   │   ├── client.py           # LspClientImpl
│   │   └── providers/
│   │       ├── __init__.py
│   │       └── basedpyright.py # BasedpyrightProvider
│   │
│   └── multilspy/              # multilspy backend (SKELETON)
│       ├── __init__.py
│       ├── client.py           # MultilspyClientImpl (stub)
│       └── providers/
│           ├── __init__.py
│           ├── java.py         # JavaProvider (stub)
│           └── csharp.py       # CSharpProvider (stub)
│
└── config/
    ├── __init__.py
    └── pyproject.py            # TOML parsing, config validation
```

### Protocol Definitions

#### `LspClient` Protocol

```python
@runtime_checkable
class LspClient(Protocol):
    """Stable interface for LSP clients."""
    
    @property
    def provider_id(self) -> str: ...
    
    @property
    def instance_id(self) -> str: ...
    
    async def request(self, method: str, params: JsonDict | None = None) -> JsonValue: ...
    
    async def notify(self, method: str, params: JsonDict | None = None) -> None: ...
    
    async def notify_did_change_watched_files(self, changes: Sequence[FileEvent]) -> None: ...
    
    def is_running(self) -> bool: ...
    
    async def shutdown(self) -> None: ...
```

#### `LspProvider` Protocol

```python
class LspProvider(Protocol[ConfigT]):
    """Factory for creating LSP clients."""
    
    @property
    def id(self) -> str: ...
    
    @property
    def config_class(self) -> type[ConfigT]: ...
    
    def get_instance_id(self, workspace_root: Path, config: ConfigT) -> str:
        """Compute unique instance ID without starting server."""
        ...
    
    async def create_client(self, workspace_root: Path, config: ConfigT) -> LspClient:
        """Create and start an LSP client."""
        ...
    
    def get_workspace_ignores(self, workspace_root: Path, config: ConfigT) -> list[str]:
        """Extract paths/patterns to ignore from workspace config."""
        ...
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Own Protocol** | Decouples from any specific library; enables multi-backend |
| **`get_instance_id()` method** | Allows `LspManager` to check cache before creating client |
| **Low-level `notify()` for didChangeWatchedFiles** | lsp-client lacks this mixin; use direct call |
| **Provider pattern preserved** | Matches current usage; language-specific config isolated |
| **multilspy skeleton** | Future-proofing; easy to implement when needed |

### Backend: lsp-client Implementation

`LspClientImpl` wraps `lsp_client.client.Client`:

```python
class LspClientImpl(LspClient):
    def __init__(self, client: Client, provider_id: str, instance_id: str):
        self._client = client
        self._provider_id = provider_id
        self._instance_id = instance_id
    
    async def notify_did_change_watched_files(self, changes: Sequence[FileEvent]) -> None:
        # Use low-level notify (lsp-client lacks mixin for this)
        await self._client.notify(
            "workspace/didChangeWatchedFiles",
            params={"changes": [{"uri": ev.uri, "type": int(ev.type)} for ev in changes]}
        )
```

`BasedpyrightProvider` uses `lsp_client.clients.BasedpyrightClient`:

```python
class BasedpyrightProvider(LspProvider[BasedpyrightConfig]):
    id = "basedpyright"
    config_class = BasedpyrightConfig
    
    def get_instance_id(self, workspace_root: Path, config: BasedpyrightConfig) -> str:
        cfg_file = resolve_config_file(workspace_root, config.config_file)
        return f"{workspace_root}::{cfg_file}" if cfg_file else str(workspace_root)
    
    async def create_client(self, workspace_root: Path, config: BasedpyrightConfig) -> LspClient:
        # Create lsp-client's BasedpyrightClient
        # Wrap in LspClientImpl
        ...
```

### Import Migration Map

| Old | New |
|-----|-----|
| `from lsp_server import AsyncLspClient` | `from lsp import LspClient` (Protocol) |
| `from lsp_server import WorkspaceLspManager` | `from lsp import LspManager` |
| `from lsp_server import LspServerProvider` | `from lsp import LspProvider` |
| `from lsp_server import LspServerSpec` | **REMOVED** (internal) |
| `from lsp_server import FileEvent, FileChangeType` | `from lsp import FileEvent, FileChangeType` |
| `from lsp_server import BasedPyrightProvider` | `from lsp.backends.lsp_client.providers import BasedpyrightProvider` |
| `from lsp_server import BasedPyrightConfig` | `from lsp.backends.lsp_client.providers import BasedpyrightConfig` |

### Consumer Update: `engine/core.py`

```python
# OLD
from lsp_server import WorkspaceLspManager, AsyncLspClient, FileEvent, FileChangeType

# NEW
from lsp import LspManager, LspClient, FileEvent, FileChangeType
from lsp.backends.lsp_client.providers import BasedpyrightProvider, BasedpyrightConfig

# Usage pattern unchanged:
self.lsp_manager = LspManager()
client = await self.lsp_manager.get_or_start(provider, workspace, config)
await client.notify_did_change_watched_files(events)
```

## Acceptance Criteria

- [ ] `lsp/` module created with protocol definitions
- [ ] `lsp/backends/lsp_client/client.py` implements `LspClient` protocol
- [ ] `lsp/backends/lsp_client/providers/basedpyright.py` implements `LspProvider`
- [ ] `lsp/manager.py` implements client caching with `get_or_start()`
- [ ] `lsp/backends/multilspy/` skeleton created (stubs raise `NotImplementedError`)
- [ ] `lsp-client` added to `pyproject.toml` dependencies
- [ ] `engine/core.py` updated to use new `lsp/` module
- [ ] All tests in `tests/lsp_server/` updated and passing
- [ ] `lsp_server/` directory deleted
- [ ] `FileEvent`, `FileChangeType` types preserved in `lsp/types.py`

## Dependencies

```toml
[project.dependencies]
lsp-client = ">=0.1.0"  # [TBD: verify actual PyPI version]
```

## Notes

- `[ASSUMPTION]` `lsp-client.BasedpyrightClient` API matches documented pattern
- `[ASSUMPTION]` Error handling wraps lsp-client exceptions in our `LspError` hierarchy
- `[TBD]` Verify `lsp-client` version on PyPI before implementation
