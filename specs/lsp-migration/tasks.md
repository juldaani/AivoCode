# Tasks: lsp-migration

## Status
- Total: 9
- Completed: 0
- Remaining: 9

---

## Tasks

[ ] 1. Add lsp-client dependency
 - pyproject.toml (add lsp-client to dependencies)

[ ] 2. Create lsp/ module core (protocols, types, exceptions)
 - lsp/__init__.py (add - public exports)
 - lsp/protocol.py (add - LspClient, LspProvider protocols)
 - lsp/types.py (add - FileEvent, FileChangeType, JsonDict, JsonValue)
 - lsp/exceptions.py (add - LspError, LspMethodNotFound)

[ ] 3. Create LspManager
 - lsp/manager.py (add - client caching with get_or_start, shutdown_all)

[ ] 4. Create lsp-client backend
 - lsp/backends/__init__.py (add)
 - lsp/backends/lsp_client/__init__.py (add - exports)
 - lsp/backends/lsp_client/client.py (add - LspClientImpl wrapping lsp-client)
 - lsp/backends/lsp_client/providers/__init__.py (add)
 - lsp/backends/lsp_client/providers/basedpyright.py (add - BasedpyrightProvider, BasedpyrightConfig)

[ ] 5. Create config utilities
 - lsp/config/__init__.py (add)
 - lsp/config/pyproject.py (add - TOML parsing, config validation, moved from basedpyright)

[ ] 6. Create multilspy backend skeleton
 - lsp/backends/multilspy/__init__.py (add)
 - lsp/backends/multilspy/client.py (add - MultilspyClientImpl stub)
 - lsp/backends/multilspy/providers/__init__.py (add)
 - lsp/backends/multilspy/providers/java.py (add - JavaProvider stub)
 - lsp/backends/multilspy/providers/csharp.py (add - CSharpProvider stub)

[ ] 7. Update engine to use new lsp/ module
 - engine/core.py (edit: update imports from lsp_server to lsp)

[ ] 8. Update tests
 - tests/lsp_server/conftest.py (edit: update imports)
 - tests/lsp_server/helpers.py (edit: update imports)
 - tests/lsp_server/test_basedpyright.py (edit: update imports)
 - tests/lsp_server/test_did_change_watched_files.py (edit: update imports)

[ ] 9. Delete old lsp_server/ module
 - lsp_server/ (delete entire directory)
