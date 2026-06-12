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
  the `lsp` and `web_ops` libraries.  Swagger docs at `http://localhost:8000/docs`.
- **CLI** — standalone package in `cli/`.  Sends HTTP requests to the REST API
  (`$AIVOCODE_URL`, defaults to `http://localhost:8000`).  No daemon logic,
  no web_ops imports — pure HTTP client with only `httpx` as a dependency.
  Install once via `bash cli/install.sh` and run `aivocode lsp symbols ...`
  from anywhere.
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

### 2. Install the CLI (one-time)

```bash
bash cli/install.sh
```

Creates an isolated venv at `~/.aivocode-cli/` (zero impact on the conda env),
installs the CLI with a single dependency (`httpx`), and links `aivocode` to
`~/.local/bin/`.

### 3. Run CLI commands

```bash
# Query document symbols (auto-starts the LSP daemon if needed)
aivocode lsp symbols tests/data/mock_repos/python/mock_pkg/utils.py

# Fetch a URL
aivocode webfetch https://example.com

# Search the web
aivocode websearch "python asyncio" --num-results 5

# Manage the daemon
aivocode lsp start
aivocode lsp status
aivocode lsp stop

# Explore a codebase (high-level agent tools)
aivocode codebase tree --suffix .py
aivocode codebase overview src/main.py
aivocode codebase read src/main.py --symbol MyClass
aivocode codebase explain src/main.py --symbol my_func
aivocode codebase search "ClassName" --kind Class
aivocode codebase incoming-calls src/main.py --symbol my_func
aivocode codebase outgoing-calls src/main.py --symbol my_func
aivocode codebase references src/main.py --symbol MyClass
aivocode codebase impact src/main.py --symbol my_func

# Import-graph tools (zero LSP — file-level dependency analysis)
aivocode codebase import-dependents src/main.py --depth 2
aivocode codebase import-dependencies src/main.py
aivocode codebase affected-tests src/main.py --depth 4

# Pretty-printed output (available on every subcommand)
aivocode lsp status --pretty-format
```

The CLI connects to the REST API at `$AIVOCODE_URL` (defaults to
`http://localhost:8000`).

**Development mode** (from the repo root, picks up uncommitted changes):

```bash
python -m cli lsp symbols tests/data/mock_repos/python/mock_pkg/utils.py
```

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
AIVOCODE_URL=http://localhost:8000 aivocode lsp symbols utils.py

cd /workspaces/aivocode
AIVOCODE_URL=http://localhost:8001 aivocode lsp symbols some_file.py
```

Always set `AIVOCODE_URL` to point to the server for the worktree you're
targeting.  The default `http://localhost:8000` is only correct when there
is a single worktree or your primary worktree uses the default port.

To query a different worktree, use absolute file paths and point to its
server:

```bash
cd /workspaces/lsp-cli-endpoint
AIVOCODE_URL=http://localhost:8001 aivocode lsp symbols /workspaces/aivocode/src/main.py
```

The CLI can be installed once via `bash cli/install.sh` and works from any
worktree — it's an HTTP client with zero local processing.  For development,
use `python -m cli` from the repo root to pick up uncommitted changes.

## REST API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/lsp/symbols` | Query document symbols `{"file": "...", "workspace?": "..."}` |
| `POST` | `/lsp/start` | Ensure daemon is running `{"workspace": "..."}` |
| `POST` | `/lsp/stop` | Graceful shutdown `{"workspace": "..."}` |
| `GET` | `/lsp/status` | Daemon health `?workspace=...` |
| `POST` | `/codebase/tree` | Recursive file tree `{"suffix?": ".py", "workspace?": "..."}` |
| `POST` | `/codebase/overview` | File ToC `{"file": "...", "depth?": 0, "workspace?": "..."}` |
| `POST` | `/codebase/read` | Read symbol body `{"file": "...", "symbol_name": "...", "line?": N}` |
| `POST` | `/codebase/explain` | Full symbol report `{"file": "...", "symbol_name": "..."}` |
| `POST` | `/codebase/search` | Workspace-wide search `{"query": "...", "kind?": "...", "limit?": 50}` |
| `POST` | `/codebase/incoming-calls` | Who calls this `{"file": "...", "symbol_name": "..."}` |
| `POST` | `/codebase/outgoing-calls` | What this calls `{"file": "...", "symbol_name": "...", "workspace_only?": true}` |
| `POST` | `/codebase/references` | Usage sites `{"file": "...", "symbol_name": "..."}` |
| `POST` | `/codebase/impact` | Change impact `{"file": "...", "symbol_name": "..."}` |
| `POST` | `/codebase/import-dependents` | Who imports this file `{"file": "...", "depth?": 1}` |
| `POST` | `/codebase/import-dependencies` | What this file imports `{"file": "..."}` |
| `POST` | `/codebase/affected-tests` | Test files importing this file `{"file": "...", "depth?": 4}` |
| `POST` | `/web_ops/webfetch` | Fetch a URL `{"url": "...", "wait_until?": "load", ...}` |
| `POST` | `/web_ops/websearch` | Search web/code `{"query": "...", "num_results?": 10, ...}` |

Workspace detection is **server-side** — the CLI sends absolute paths
(cwd or file path), and the server calls `detect_workspace()` via git.

## Package Structure

```
api_server/          REST API server (FastAPI)
├── app.py           FastAPI app + CORS + routers
└── routes/lsp.py    LSP route handlers

cli/                 CLI (thin HTTP client)
├── pyproject.toml    Standalone package: aivocode-cli (dep: httpx only)
├── install.sh        Isolated venv install script
├── main.py           Entry point: python -m cli / aivocode
├── _utils.py         Shared: HTTP transport, --pretty-format
└── commands/         One module per subcommand
    ├── lsp.py
    ├── codebase.py
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

codebase/            Agent‑facing exploration tools
├── __init__.py      Public API: read_symbol, file_overview, explain_symbol, etc.
├── _analyze.py      Call hierarchy, references, overview, search, impact
├── _read.py         Symbol body reader + tree‑sitter import extraction
├── _resolve.py      Name → position resolution + symbol tree builders
├── _snippet.py      File snippet reader (snippet/preview/range)
├── _tree.py         Recursive file/directory tree builder
├── _treesitter.py   Tree-sitter parser registry (lazy grammar loading)
├── _import_graph.py Workspace-wide reverse import graph + dependency queries
└── _lang_handlers/  Language-specific import extraction (Python, TS, ...)
    ├── _base.py     LanguageHandler protocol + RawImport dataclass
    └── _python.py   PythonHandler — tree-sitter import parsing + resolution

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

# Import graph (unit + integration + schema)
pytest tests/unit/codebase/test_import_graph.py tests/integration/test_import_graph.py tests/e2e/test_import_graph_schema.py -v

# Import graph daemon integration (requires running daemon)
pytest tests/integration/test_import_graph.py::TestGraphReindex -v
```

## Key Design Decisions

| Decision | Why |
|---|---|
| Daemon per workspace, auto‑started | Keeps LSP server alive across CLI invocations — no re‑indexing on every query |
| `force_polling=True` | Docker‑mounted volumes don't get inotify events |
| Crash‑fast | Watcher or LSP crash → daemon exits → next query auto‑restarts fresh. Stale state is worse than a clean start. |
| Thin layers everywhere | CLI, REST routes, public API — all ~10‑line wrappers. Library owns the logic. |
| REST API, not direct import | Universal endpoint for CLI, MCP, browser consumers. Same API regardless of transport. |
| Server‑side workspace detection | CLI sends absolute paths (cwd / file); server calls `detect_workspace()` via git. Zero git knowledge in CLI. |
| Standalone CLI with isolated venv | `cli/install.sh` creates `~/.aivocode-cli/` — only `httpx` + stdlib. Zero impact on the devcontainer's conda env.
| `python -m cli` for development | Picks up uncommitted changes immediately without reinstall.

## Gotchas

- **`from __future__ import annotations`** must be the very first statement
  in any file that uses it (PEP 236).
- **Unix socket path limit** is 108 bytes — the socket hash is truncated to
  24 hex chars to stay under the limit.
- **Workspace detection** is server‑side. The CLI sends absolute paths
  and the server calls `detect_workspace()` via git. No `lsp` imports in
  the CLI at all.
- **`detect_workspace()`** accepts both files and directories.  Passing
  `Path.cwd()` works for `start`/`stop`/`status`.
- **File existence** is checked before calling the LSP server — missing
  files return a clean JSON error instead of crashing the daemon with an
  ExceptionGroup.
- **Daemon `start_new_session=True`** means the daemon survives parent
  exit.  Tests clean up with `POST /lsp/stop` before killing the server.
- **Standalone CLI isolation** — `cli/install.sh` creates a dedicated venv
  at `~/.aivocode-cli/`. The `aivocode` console script automatically uses
  that venv's Python via its shebang line. `httpx` lives only there.
