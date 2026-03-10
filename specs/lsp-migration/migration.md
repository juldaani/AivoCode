# LSP Migration Checklist

## Overview

Step-by-step migration from `lsp_server/` to new `lsp/` abstraction layer.

---

## Phase 1: Create New Structure

### 1.1 Create Directory Structure

```bash
mkdir -p lsp/backends/lsp_client/providers
mkdir -p lsp/backends/multilspy/providers
mkdir -p lsp/config
```

### 1.2 Create Core Files

| File | Status | Notes |
|------|--------|-------|
| `lsp/__init__.py` | [ ] | Public exports |
| `lsp/protocol.py` | [ ] | LspClient, LspProvider protocols |
| `lsp/types.py` | [ ] | FileEvent, FileChangeType, JsonDict |
| `lsp/exceptions.py` | [ ] | LspError, LspMethodNotFound |
| `lsp/manager.py` | [ ] | LspManager class |

### 1.3 Create Backend Files

| File | Status | Notes |
|------|--------|-------|
| `lsp/backends/__init__.py` | [ ] | Empty or exports |
| `lsp/backends/lsp_client/__init__.py` | [ ] | Exports |
| `lsp/backends/lsp_client/client.py` | [ ] | LspClientImpl |
| `lsp/backends/lsp_client/providers/__init__.py` | [ ] | Exports |
| `lsp/backends/lsp_client/providers/basedpyright.py` | [ ] | BasedpyrightProvider |
| `lsp/backends/multilspy/__init__.py` | [ ] | Exports |
| `lsp/backends/multilspy/client.py` | [ ] | MultilspyClientImpl (stub) |
| `lsp/backends/multilspy/providers/__init__.py` | [ ] | Exports |
| `lsp/backends/multilspy/providers/java.py` | [ ] | JavaProvider (stub) |
| `lsp/backends/multilspy/providers/csharp.py` | [ ] | CSharpProvider (stub) |

### 1.4 Create Config Files

| File | Status | Notes |
|------|--------|-------|
| `lsp/config/__init__.py` | [ ] | Exports |
| `lsp/config/pyproject.py` | [ ] | Move from basedpyright/config.py |

---

## Phase 2: Implement Core

### 2.1 Types (`lsp/types.py`)

- [ ] Copy `FileChangeType` from `lsp_server/types.py`
- [ ] Copy `FileEvent` from `lsp_server/types.py`
- [ ] Define `JsonValue` and `JsonDict` type aliases

### 2.2 Exceptions (`lsp/exceptions.py`)

- [ ] Define `LspError` base exception
- [ ] Define `LspMethodNotFound` exception
- [ ] Define `LspResponseError` exception

### 2.3 Protocols (`lsp/protocol.py`)

- [ ] Define `LspClient` protocol with all methods
- [ ] Define `LspProvider` protocol with `get_instance_id()` and `create_client()`
- [ ] Add `ConfigT` type variable

### 2.4 Manager (`lsp/manager.py`)

- [ ] Implement `LspManager` class
- [ ] Implement `get_or_start()` with cache check
- [ ] Implement `shutdown_all()`

---

## Phase 3: Implement lsp-client Backend

### 3.1 Client Implementation (`lsp/backends/lsp_client/client.py`)

- [ ] Create `LspClientImpl` class
- [ ] Implement all `LspClient` protocol methods
- [ ] Implement `notify_did_change_watched_files()` via low-level `notify()`
- [ ] [TBD: verify lsp-client `is_running` property name]

### 3.2 Basedpyright Provider (`lsp/backends/lsp_client/providers/basedpyright.py`)

- [ ] Create `BasedpyrightConfig` dataclass
- [ ] Create `BasedpyrightProvider` class
- [ ] Implement `get_instance_id()` - format: `{workspace}::{config_file}` or `{workspace}`
- [ ] Implement `create_client()` using lsp-client's `BasedpyrightClient`
- [ ] Implement `get_workspace_ignores()` - copy logic from current provider

### 3.3 Config Utilities (`lsp/config/pyproject.py`)

- [ ] Move `resolve_and_validate_config_file()` from `lsp_server/basedpyright/config.py`
- [ ] Keep TOML/JSON parsing logic

---

## Phase 4: Implement multilspy Skeleton

### 4.1 Client Skeleton (`lsp/backends/multilspy/client.py`)

- [ ] Create `MultilspyClientImpl` class
- [ ] All methods raise `NotImplementedError`

### 4.2 Provider Skeletons

- [ ] Create `JavaProvider` stub
- [ ] Create `CSharpProvider` stub
- [ ] All methods raise `NotImplementedError`

---

## Phase 5: Update Public Exports

### 5.1 `lsp/__init__.py`

```python
from .exceptions import LspError, LspMethodNotFound, LspResponseError
from .manager import LspManager
from .protocol import LspClient, LspProvider
from .types import FileChangeType, FileEvent, JsonDict, JsonValue

__all__ = [
    "FileChangeType",
    "FileEvent",
    "JsonDict",
    "JsonValue",
    "LspClient",
    "LspError",
    "LspManager",
    "LspMethodNotFound",
    "LspProvider",
    "LspResponseError",
]
```

### 5.2 `lsp/backends/lsp_client/__init__.py`

```python
from .client import LspClientImpl
from .providers import BasedpyrightConfig, BasedpyrightProvider

__all__ = [
    "BasedpyrightConfig",
    "BasedpyrightProvider",
    "LspClientImpl",
]
```

---

## Phase 6: Update Consumers

### 6.1 `engine/core.py`

| Change | Status |
|--------|--------|
| Update imports from `lsp_server` to `lsp` | [ ] |
| Update provider imports to use `lsp.backends.lsp_client.providers` | [ ] |
| Verify `LspManager` usage unchanged | [ ] |
| Verify `client.request()`, `client.notify_did_change_watched_files()` unchanged | [ ] |

**Old imports:**
```python
from lsp_server import WorkspaceLspManager, AsyncLspClient, FileEvent, FileChangeType
```

**New imports:**
```python
from lsp import LspManager, LspClient, FileEvent, FileChangeType
from lsp.backends.lsp_client.providers import BasedpyrightProvider, BasedpyrightConfig
```

### 6.2 Test Files

| File | Status | Changes |
|------|--------|---------|
| `tests/lsp_server/conftest.py` | [ ] | Update imports |
| `tests/lsp_server/helpers.py` | [ ] | Update imports |
| `tests/lsp_server/test_basedpyright.py` | [ ] | Update imports |
| `tests/lsp_server/test_did_change_watched_files.py` | [ ] | Update imports |

---

## Phase 7: Testing

### 7.1 Run Tests

```bash
conda run -n env-aivocode pytest tests/lsp_server/
```

- [ ] All tests pass
- [ ] Fix any failures

### 7.2 Manual Verification

- [ ] Start engine with basedpyright
- [ ] Verify file watcher triggers `didChangeWatchedFiles`
- [ ] Verify `documentSymbol` requests work
- [ ] Verify graceful shutdown

---

## Phase 8: Cleanup

### 8.1 Delete Old Implementation

| File/Directory | Status |
|----------------|--------|
| `lsp_server/async_process.py` | [ ] DELETE |
| `lsp_server/client.py` | [ ] DELETE |
| `lsp_server/spec.py` | [ ] DELETE |
| `lsp_server/provider.py` | [ ] DELETE |
| `lsp_server/manager.py` | [ ] DELETE |
| `lsp_server/types.py` | [ ] DELETE |
| `lsp_server/__init__.py` | [ ] DELETE |
| `lsp_server/how_to_use.py` | [ ] DELETE |
| `lsp_server/basedpyright/` | [ ] DELETE |
| `lsp_server/` directory | [ ] DELETE |

### 8.2 Update Documentation

- [ ] Update any references to `lsp_server` in comments/docs
- [ ] Verify no broken imports remain

---

## Verification Checklist

- [ ] `lsp/` module structure complete
- [ ] `LspClientImpl` wraps lsp-client correctly
- [ ] `BasedpyrightProvider` creates working clients
- [ ] `LspManager` caches by `(provider_id, instance_id)`
- [ ] `notify_did_change_watched_files()` works
- [ ] `engine/core.py` uses new module
- [ ] All tests pass
- [ ] `lsp_server/` deleted
- [ ] multilspy skeleton in place

---

## Rollback Plan

If migration fails:

1. Revert `engine/core.py` changes
2. Revert test file changes
3. Delete `lsp/` directory
4. `lsp_server/` remains functional

Git commands:
```bash
git checkout -- engine/core.py tests/lsp_server/
rm -rf lsp/
```
