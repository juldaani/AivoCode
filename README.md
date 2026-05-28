# AivoCode — Codebase Intelligence Engine for AI Agents

AivoCode provides LSP-powered code analysis and web intelligence (fetching,
searching) as a REST API, with a CLI client that agents run in their
devcontainer.  The LSP daemon keeps language servers alive across queries
for fast, indexed responses.

## Architecture

```
Devcontainer / any consumer              Aivocode container (or localhost)
════════════════════════════              ═══════════════════════════════════
                                         fastapi dev api_server/app.py :8000
CLI: python -m cli lsp symbols file.py       │
      │  HTTP POST /lsp/symbols              ├─ lsp library (daemon per
      └─────────────────────────────────────►│   workspace, Unix socket
                                             │   transport, file watcher
      ◄───────────────────────────────────── │   with force_polling=True)
         {"symbols": [...], ...}             │
                                             ├─ web_ops library (future)
                                             └─ GET /health
```

- **REST API server** — FastAPI app in `api_server/`.  Thin routes wrapping
  the `lsp` library.  Swagger docs at `http://localhost:8000/docs`.
- **CLI** — `cli/commands/lsp.py`.  Sends HTTP requests to the REST API
  (`$AIVOCODE_URL`, defaults to `http://localhost:8000`).  No daemon logic.
- **Library** — `lsp/`.  Persistent daemon, workspace detection, symbol
  serialization.  Unchanged regardless of CLI / REST / MCP front‑end.

## Quick Start

### 1. Start the REST API server

```bash
fastapi dev api_server/app.py
# Server listening on http://127.0.0.1:8000
# Swagger docs at http://127.0.0.1:8000/docs
```

For production: `fastapi run api_server/app.py`

### 2. Run CLI commands (from the repo root)

```bash
# Query document symbols (auto-starts the LSP daemon if needed)
python -m cli lsp symbols tests/data/mock_repos/python/mock_pkg/utils.py

# Manage the daemon
python -m cli lsp start
python -m cli lsp status
python -m cli lsp stop
```

The CLI connects to the REST API at `$AIVOCODE_URL` (defaults to
`http://localhost:8000`).

## Development with Multiple Worktrees

Each worktree is self‑contained — its own REST API server, its own daemon
subprocess, its own code.  Start one server per worktree on different ports:

```bash
# Terminal 1 — lsp-cli-endpoint
cd /workspaces/lsp-cli-endpoint && fastapi dev api_server/app.py
# → :8000

# Terminal 2 — aivocode (main)
cd /workspaces/aivocode && fastapi dev api_server/app.py --port 8001
# → :8001
```

Run CLI from the worktree you're working in:

```bash
cd /workspaces/lsp-cli-endpoint
AIVOCODE_URL=http://localhost:8000 python -m cli lsp symbols utils.py

cd /workspaces/aivocode
AIVOCODE_URL=http://localhost:8001 python -m cli lsp symbols some_file.py
```

Always set `AIVOCODE_URL` to point to the server for the worktree you're
targeting.  The default `http://localhost:8000` is only correct when there
is a single worktree or your primary worktree uses the default port.

To query a different worktree, use absolute file paths and point to its
server:

```bash
cd /workspaces/lsp-cli-endpoint
AIVOCODE_URL=http://localhost:8001 python -m cli lsp symbols /workspaces/aivocode/src/main.py
```

There is **no global `aivocode` install** — `python -m cli` resolves
imports from the current worktree's packages.

## REST API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/lsp/symbols` | Query document symbols `{"file": "...", "workspace?": "..."}` |
| `POST` | `/lsp/start` | Ensure daemon is running `{"workspace": "..."}` |
| `POST` | `/lsp/stop` | Graceful shutdown `{"workspace": "..."}` |
| `GET` | `/lsp/status` | Daemon health `?workspace=...` |

## Package Structure

```
api_server/          REST API server (FastAPI)
├── app.py           FastAPI app + CORS + routers
└── routes/lsp.py    LSP route handlers

cli/                 CLI (thin HTTP client)
├── main.py          Entry point: python -m cli
└── commands/        One module per subcommand
    ├── lsp.py
    ├── webfetch.py
    └── websearch.py

lsp/                 LSP library (core logic)
├── __init__.py      Public API: query_document_symbols, daemon_*
├── client.py        LspClient (async context manager)
├── _daemon.py       Daemon lifecycle: spawn, query, stop
├── _protocol.py     LD‑JSON over Unix sockets
├── _serialize.py    DocumentSymbol → JSON
├── _workspace.py    Git workspace detection
├── _translate.py    File watcher → LSP events
└── config.py        LanguageEntry, load_config (lsp_config.toml)

web_ops/             Web intelligence (future REST endpoints)
file_watcher/        File system watcher (awatch_repos)
tests/
├── e2e/             End-to-end tests (CLI + server)
└── integration/lsp/ LSP client integration tests
```

## Tests

```bash
# All tests
pytest

# LSP integration (LspClient, symbols, diagnostics)
pytest tests/integration/lsp/ -v

# E2E: LSP bridge (file watcher → LSP)
pytest tests/e2e/test_lsp_bridge.py -v

# E2E: CLI + REST API (starts server, tests all lsp subcommands)
pytest tests/e2e/test_lsp_cli.py -v
```

## Key Design Decisions

| Decision | Why |
|---|---|
| Daemon per workspace, auto‑started | Keeps LSP server alive across CLI invocations — no re‑indexing on every query |
| `force_polling=True` | Docker‑mounted volumes don't get inotify events |
| Crash‑fast | Watcher or LSP crash → daemon exits → next query auto‑restarts fresh. Stale state is worse than a clean start. |
| Thin layers everywhere | CLI, REST routes, public API — all ~10‑line wrappers. Library owns the logic. |
| REST API, not direct import | Universal endpoint for CLI, MCP, browser consumers. Same API regardless of transport. |
| `python -m cli`, no global install | Each worktree runs its own code. No cross‑contamination. |

## Gotchas

- **`from __future__ import annotations`** must be the very first statement
  in any file that uses it (PEP 236).
- **Unix socket path limit** is 108 bytes — the socket hash is truncated to
  24 hex chars to stay under the limit.
- **`detect_workspace()`** accepts both files and directories.  Passing
  `Path.cwd()` works for `start`/`stop`/`status`.
- **File existence** is checked before calling the LSP server — missing
  files return a clean JSON error instead of crashing the daemon with an
  ExceptionGroup.
- **Daemon `start_new_session=True`** means the daemon survives parent
  exit.  Tests clean up with `POST /lsp/stop` before killing the server.
