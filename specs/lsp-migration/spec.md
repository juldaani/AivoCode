# LSP Migration

## Summary

Replace the custom `lsp_server/` implementation with the `lsp-client` library while introducing a clean abstraction layer. This enables future multi-library support (e.g., multilspy) without coupling AivoCode to any single LSP client implementation.

## Scope

### In scope
- New `lsp/` module with protocol-based abstraction
- `lsp-client` backend (full implementation)
- `multilspy` backend (skeleton only)
- Python language support via basedpyright
- Migration of `engine/core.py` and test files
- Deletion of `lsp_server/` directory

### Out of scope
- Additional language servers (rust-analyzer, gopls, etc.)
- Full multilspy implementation
- Configuration file format changes
- Engine behavior changes

## Requirements

### Functional Requirements
1. **Protocol Abstraction**: Define `LspClient` and `LspProvider` protocols that hide library-specific details
2. **Client Lifecycle**: Support `start()`, `is_running()`, `shutdown()` lifecycle
3. **LSP Operations**: Support `request()`, `notify()`, and `notify_did_change_watched_files()`
4. **Provider Pattern**: Each language server has a provider that creates clients and extracts workspace ignores
5. **Client Caching**: `LspManager` caches clients by `(provider_id, instance_id)` to avoid duplicate servers
6. **Instance ID**: Providers expose `get_instance_id()` for cache key computation before client creation

### Non-Functional Requirements
1. **Type Safety**: Full type annotations on public API
2. **Async-First**: All LSP operations are async
3. **Extensibility**: New backends can be added without changing consumer code
4. **Backward Compatible API**: Consumer code (`engine/core.py`) requires minimal changes

### Constraints
- Python 3.12+
- lsp-client version: 0.3.9
- basedpyright version: 1.38.1

## Proposed Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     lsp/ (New Abstraction)                      │
│  Stable API for AivoCode - hides library implementation details │
├─────────────────────────────────────────────────────────────────┤
│  Public Exports:                                                │
│  - LspClient (protocol)                                         │
│  - LspManager (client cache, lifecycle)                         │
│  - LspProvider (protocol)                                       │
│  - FileEvent, FileChangeType, JsonDict, JsonValue (types)       │
│  - LspError, LspMethodNotFound (exceptions)                     │
├─────────────────────────────────────────────────────────────────┤
│                     Backend Implementations                     │
├──────────────────────────┬──────────────────────────────────────┤
│   backends/lsp_client/    │   backends/multilspy/ (skeleton)    │
│   - LspClientImpl         │   - MultilspyClientImpl (stub)      │
│   - BasedpyrightProvider  │   - JavaProvider (stub)             │
├──────────────────────────┴──────────────────────────────────────┤
│  Dependencies: lsp-client==0.3.9 | multilspy (future)          │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Own `LspClient` protocol | Decouples from lsp-client, enables future backends |
| `get_instance_id()` on provider | Allows cache check before expensive client creation |
| Low-level `notify()` for didChangeWatchedFiles | lsp-client lacks mixin for this; use direct call |
| `is_running()` with manual flag tracking | lsp-client has no public `is_running` property; simple flag is reliable |
| Use lsp-client built-in server request handlers | lsp-client has `WithRespondConfigurationRequest` and `WithRespondWorkspaceFoldersRequest` mixins |
| No backward compatibility | Clean break; update all downstream imports explicitly |
| multilspy skeleton only | Unblocks future work without current overhead |

### Module Structure

```
lsp/
├── __init__.py                 # Public exports
├── protocol.py                 # LspClient, LspProvider protocols
├── types.py                    # FileEvent, FileChangeType, JsonDict
├── exceptions.py               # LspError, LspMethodNotFound
├── manager.py                  # LspManager (client cache)
│
├── backends/
│   ├── __init__.py
│   │
│   ├── lsp_client/             # lsp-client backend (FULL IMPL)
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
└── config/                     # Config utilities
    ├── __init__.py
    └── pyproject.py            # TOML parsing, config validation
```

### Integration Points

**Consumer: `engine/core.py`**
- Imports `LspManager`, `LspClient`, `FileEvent`, `FileChangeType` from `lsp/`
- Uses `LspManager.get_or_start(provider, workspace, config)`
- Calls `client.request()`, `client.notify_did_change_watched_files()`, `client.is_running()`

**Tests: `tests/lsp/`**
- Directory renamed from `tests/lsp_server/`
- Update imports to use `lsp/` module
- Provider tests use `BasedpyrightProvider` from `lsp.backends.lsp_client.providers`
- Update `config.toml` provider module paths

## Acceptance Criteria

- [ ] `lsp/` module created with protocol definitions
- [ ] `LspClientImpl` wraps lsp-client's `Client` correctly
- [ ] `BasedpyrightProvider` creates working basedpyright clients
- [ ] `LspManager` caches and reuses clients by `(provider_id, instance_id)`
- [ ] `notify_did_change_watched_files()` works via low-level `notify()`
- [ ] `engine/core.py` updated to use new `lsp/` module
- [ ] All tests pass after migration
- [ ] `lsp_server/` directory deleted
- [ ] multilspy skeleton in place (raises `NotImplementedError`)

## References

- `api.md` - Protocol definitions and contracts
- `migration.md` - Step-by-step migration checklist
