# Tasks: lsp-migration

## Status
- Total: 24
- Completed: 0
- Remaining: 24

---

## Tasks

### Group 1: Core Types & Exceptions
Produce importable `lsp.types` and `lsp.exceptions` modules.

[ ] 1.1 Create directory structure
 - `lsp/` (add)
 - `lsp/backends/` (add)
 - `lsp/backends/lsp_client/` (add)
 - `lsp/backends/lsp_client/providers/` (add)
 - `lsp/backends/multilspy/` (add)
 - `lsp/backends/multilspy/providers/` (add)
 - `lsp/config/` (add)

[ ] 1.2 Implement types module
 - `lsp/types.py` (add) - FileChangeType, FileEvent, JsonDict, JsonValue

[ ] 1.3 Implement exceptions module
 - `lsp/exceptions.py` (add) - LspError, LspMethodNotFound, LspResponseError

---

### Group 2: Protocols & Manager
Produce usable abstraction layer with `LspClient`, `LspProvider`, and `LspManager`.

[ ] 2.1 Implement LspClient protocol
 - `lsp/protocol.py` (add) - LspClient protocol with all methods

[ ] 2.2 Implement LspProvider protocol
 - `lsp/protocol.py` (edit: add LspProvider with get_instance_id, create_client, get_workspace_ignores)

[ ] 2.3 Implement LspManager
 - `lsp/manager.py` (add) - LspManager with get_or_start, shutdown_all

[ ] 2.4 Create public exports
 - `lsp/__init__.py` (add) - Export all public symbols
 - `lsp/backends/__init__.py` (add) - Empty or minimal exports

---

### Group 3: lsp-client Backend
Produce working backend that wraps lsp-client library.

[ ] 3.1 Implement LspClientImpl
 - `lsp/backends/lsp_client/__init__.py` (add)
 - `lsp/backends/lsp_client/client.py` (add) - LspClientImpl wrapping lsp-client's Client

[ ] 3.2 Implement config utilities
 - `lsp/config/__init__.py` (add)
 - `lsp/config/pyproject.py` (add) - resolve_and_validate_config_file from lsp_server

[ ] 3.3 Implement BasedpyrightProvider
 - `lsp/backends/lsp_client/providers/__init__.py` (add)
 - `lsp/backends/lsp_client/providers/basedpyright.py` (add) - BasedpyrightConfig, BasedpyrightProvider

[ ] 3.4 Update backend exports
 - `lsp/backends/lsp_client/__init__.py` (edit: export LspClientImpl, BasedpyrightProvider, BasedpyrightConfig)

---

### Group 4: multilspy Skeleton
Produce stub backend that raises NotImplementedError.

[ ] 4.1 Implement MultilspyClientImpl stub
 - `lsp/backends/multilspy/__init__.py` (add)
 - `lsp/backends/multilspy/client.py` (add) - All methods raise NotImplementedError

[ ] 4.2 Implement provider stubs
 - `lsp/backends/multilspy/providers/__init__.py` (add)
 - `lsp/backends/multilspy/providers/java.py` (add) - JavaProvider stub
 - `lsp/backends/multilspy/providers/csharp.py` (add) - CSharpProvider stub

---

### Group 5: Consumer Migration
Produce working integration with engine and tests.

[ ] 5.1 Update engine imports
 - `engine/core.py` (edit: change imports from lsp_server to lsp)

[ ] 5.2 Update test helpers
 - `tests/lsp_server/helpers.py` (edit: update imports)

[ ] 5.3 Update test fixtures
 - `tests/lsp_server/conftest.py` (edit: update imports, use LspManager)

[ ] 5.4 Update test files
 - `tests/lsp_server/test_basedpyright.py` (edit: update imports)
 - `tests/lsp_server/test_did_change_watched_files.py` (edit: update imports)

---

### Group 6: Tests
Produce passing test suite.

[ ] 6.1 Run and fix tests
 - `tests/lsp_server/` (edit: fix any test failures)

[ ] 6.2 Verify integration
 - Manual verification: engine starts, file watcher works, shutdown works

---

### Group 7: Cleanup
Remove old implementation.

[ ] 7.1 Delete old lsp_server module
 - `lsp_server/async_process.py` (delete)
 - `lsp_server/client.py` (delete)
 - `lsp_server/spec.py` (delete)
 - `lsp_server/provider.py` (delete)
 - `lsp_server/manager.py` (delete)
 - `lsp_server/types.py` (delete)
 - `lsp_server/__init__.py` (delete)
 - `lsp_server/how_to_use.py` (delete)
 - `lsp_server/basedpyright/__init__.py` (delete)
 - `lsp_server/basedpyright/config.py` (delete)
 - `lsp_server/basedpyright/provider.py` (delete)
 - `lsp_server/basedpyright/` (delete)
 - `lsp_server/` (delete)

[ ] 7.2 Final verification
 - Run full test suite
 - Verify no broken imports
