# LSP Server Utilities

What this directory provides
- A small, reusable LSP client stack built around stdio (JSON-RPC over stdin/stdout).
- Provider abstractions to launch language-specific servers (for example, basedpyright).
- A workspace manager that keeps one server process per workspace/server pair.

Why this exists
- To make it easy to start and reuse LSP servers in a deterministic, testable way.
- To keep language-specific logic separate from the generic transport/runtime.
  This lets us plug in different LSP servers (Python, TS, C++, etc.) while
  reusing "the same process management and JSON-RPC plumbing".

How to use it
- Start with `lsp_server/how_to_use.py` for a runnable, minimal example.
- The core flow is: provider -> spec -> AsyncLspClient -> requests/notifications.

Key files
- `lsp_server/async_process.py`: stdio transport + JSON-RPC framing.
- `lsp_server/client.py`: LSP initialize + request routing.
- `lsp_server/manager.py`: cache and reuse clients per workspace.
- `lsp_server/basedpyright.py`: basedpyright-specific provider.
