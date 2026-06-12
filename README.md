# AivoCode — Codebase Intelligence Engine for AI Agents

AivoCode gives AI agents (like Claude, Cursor, or OpenCode) programmatic
access to codebase understanding and web research. It provides LSP-powered
code analysis, tree-sitter import graphs, and web intelligence as a single
REST API — with a zero-dependency CLI that works from any devcontainer.

---

## Why AivoCode?

AI coding agents need to answer questions like:

- *"What functions does this file export?"*
- *"Who calls this function, and where?"*
- *"Which tests will break if I change this module?"*
- *"What does this library's documentation say?"*

Answering these questions reliably requires running language servers,
parsing ASTs, and crawling web pages — all of which take seconds to minutes
to set up. AivoCode runs all of this as a **persistent background service**
so agents get answers in milliseconds.

---

## Core Concepts

**Everything is a REST API.** The server runs language servers, watches
files, builds import graphs, and fetches web pages. Clients (CLI, MCP
servers, browser extensions) send HTTP requests and get JSON back.

**Workspace-scoped.** AivoCode auto-detects your git workspace root. Each
workspace gets its own LSP daemon process — fast, isolated, and crash-safe.

**Three engines under the hood:**

| Engine | How | Used by |
|---|---|---|
| **LSP daemon** | Persistent language server (basedpyright) over Unix sockets | Symbol queries, call hierarchy, references, diagnostics |
| **Tree-sitter import graph** | Parses imports from every source file, builds a reverse dependency graph | `import-dependents`, `affected-tests` |
| **Web intelligence** | Headless browser (Chrome + Crawl4AI) + Exa neural search | `webfetch`, `websearch` |

---

## Tools at a Glance

Every subcommand sends an HTTP request to the REST API server. The CLI
does zero local processing — all logic runs server-side.

### `aivocode lsp` — direct LSP protocol queries

These map directly to LSP protocol features. Also includes daemon lifecycle
management. Every query auto-starts the daemon if needed.

| Subcommand | What it does | How it works |
|---|---|---|
| **symbols** | Lists all symbols (functions, classes, variables) in a file with their ranges | `documentSymbol` request to the LSP server; returns a recursive tree |
| **definition** | Finds where a symbol is defined | `definition` request at a `(line, character)` position |
| **type-definition** | Finds the type declaration of a symbol | `typeDefinition` request |
| **references** | Lists every usage site of a symbol across the workspace | `references` request; includes the definition site |
| **hover** | Shows type info, signature, and docstring at a position | `hover` request; returns markdown |
| **incoming-calls** | Shows who calls a function | `callHierarchy/incomingCalls` |
| **outgoing-calls** | Shows what a function calls | `callHierarchy/outgoingCalls` |
| **diagnostics** | Shows type errors, warnings, style issues | `textDocument/diagnostic` from the language server |
| **workspace-symbol** | Fuzzy search for symbols by name across the whole project | `workspace/symbol` request; substring match (e.g. `"greet"` → `Greeter`) |
| **rename-edits** | Previews a rename without applying it | `rename` with preview mode; returns a `WorkspaceEdit` dict |
| **start** | Ensure the LSP daemon is running (manual trigger) | Spawns the daemon if not alive; does nothing if already running |
| **stop** | Graceful daemon shutdown | Sends shutdown request then removes socket files |
| **status** | Check daemon health | Pings the daemon socket; returns language, server, uptime |

### `aivocode codebase` — agent-facing compositions

These are higher-level tools composing LSP calls, file I/O, and tree-sitter
parsing. Designed for agents that need answers, not raw LSP data.

The first group uses the LSP daemon; the last three use the **tree-sitter
import graph** (no LSP, no daemon wait time).

| Subcommand | What it does | How it works |
|---|---|---|
| **tree** | Recursive directory listing (like `find`) filtered by suffix | `os.scandir` walk; returns `{"dirname/": [files], ...}` |
| **overview** | Table of contents: symbols with signatures, previews, reference counts | Queries document symbols, resolves references per symbol, extracts signatures via tree-sitter |
| **read** | Full body text of a named symbol | Resolves the symbol's range from LSP, reads source from disk |
| **explain** | Full report: body, definition, callers, callees, references | Composes read + incoming-calls + outgoing-calls + references |
| **search** | Search symbols by name with optional kind filter | Wraps workspace-symbol; adds kind and limit filtering |
| **incoming-calls** | Who calls this? — enriched with snippets and file locality | `callHierarchy/incomingCalls` + snippet reader + locality tagging |
| **outgoing-calls** | What does this call? — enriched with snippets, optional workspace-only filter | `callHierarchy/outgoingCalls` + snippet reader + locality filtering |
| **references** | Where is this used? — enriched with snippets and file locality | `references` request + snippet reader + locality tagging |
| **impact** | Change impact: symbol callers + file blast radius + affected tests | Combines LSP call hierarchy + references with import graph transitive dependents and affected tests. `--depth` controls file-level transitivity (default 10) |
| **import-dependents** | Which files (transitively) import this file? | BFS traversal of the reverse import graph; `--depth` controls transitivity |
| **import-dependencies** | What files does this file import directly? | Direct lookup in the forward import graph |
| **affected-tests** | Which test files are affected if this file changes? | Runs import-dependents then filters to test files by naming convention |

The import graph is built from tree-sitter ASTs — a two-pass workspace
walk that indexes every module path and extracts import statements.
Incremental updates from the file watcher mean only changed files are
re-indexed.

### `aivocode webfetch` / `aivocode websearch` — web intelligence

| Subcommand | What it does | How it works |
|---|---|---|
| **webfetch** | Fetches a URL and returns clean markdown | Launches a stealth Chrome browser via CloakBrowser; Crawl4AI captures and converts to markdown. Large pages get a navigable table of contents. Supports section extraction by heading or line range. |
| **websearch** | Neural web/code search | Sends the query to the Exa Search API; returns ranked results with highlights, text summaries, and metadata. Domain filtering and full-text retrieval supported. Requires `EXA_API_KEY`. |

---

## How It Works

### LSP Daemon

The daemon is the heart of the system. Instead of starting a language
server for every CLI invocation (5-30 second penalty for basedpyright to
index a large project), AivoCode keeps one **persistent daemon process**
per workspace:

```
┌─ spawn ───────────────────────────────────────────────────────┐
│  python lsp/_daemon.py <workspace> <socket_path>              │
│                                                               │
│  asyncio event loop:                                          │
│  ├─ LspClient (basedpyright, persistent, auto-indexed)        │
│  ├─ File watcher (watchfiles → didChangeWatchedFiles)         │
│  ├─ Import graph (kept in sync with file changes)              │
│  ├─ Unix socket server (accepts LD-JSON queries)              │
│  └─ Idle watcher (auto-shutdown after 10 min idle)            │
└───────────────────────────────────────────────────────────────┘
```

- **Auto-start**: The first query to a workspace spawns the daemon. No
  manual `start` needed.
- **Crash-fast**: If any component (LSP, watcher, socket server) fails,
  the entire daemon exits. Stale state is worse than a clean restart.
  The next query transparently spawns a fresh daemon.
- **Socket transport**: All queries use Unix domain sockets with
  LD-JSON framing (one JSON line per request/response). Fast,
  local-only, zero network overhead.
- **Idle shutdown**: After 10 minutes of inactivity, the daemon exits
  to free resources. Configurable via `AIVOCODE_DAEMON_IDLE_TIMEOUT`.

### Tree-sitter Import Graph

The import graph provides **file-level** dependency analysis without a
language server. Here's how it works:

1. **Two-pass build**: First, walk the workspace to build a module→file
   index (e.g. `mock_pkg.utils` → `mock_pkg/utils.py`). Second, parse
   every source file with tree-sitter to extract import statements.
2. **Language handlers**: A pluggable protocol (`LanguageHandler`) that
   each language implements. Currently `PythonHandler` (`.py`/`.pyi`)
   parses `import`, `import from`, and `from __future__ import`
   statements, detects lazy/nested imports (inside function/class
   bodies), resolves relative imports, and identifies test files.
3. **Reverse graph**: For every `file A imports file B`, store both
   `_forward[A] = {B}` and `_reverse[B] = {A}`. This makes reverse
   lookups O(1).
4. **BFS traversal**: `import-dependents` and `affected-tests` use a
   breadth-first search from the target file, recording depth at each
   step. Results are sorted by `(depth, file)`.
5. **Incremental updates**: The file watcher triggers `update()` which
   only re-indexes changed files — no full rebuild needed.

### Web Fetch & Search

- **Web fetch**: Uses a headless Chrome browser (CloakBrowser) + Crawl4AI
  to render pages (including JS-heavy SPAs) and convert them to clean
  markdown. Large pages (>10k chars) are chunked into a heading-aware
  tree and returned as a compact table of contents. Full content is
  cached to disk with a 15-minute TTL. Supports per-section extraction
  via heading match or line range.

- **Web search**: Uses the [Exa](https://exa.ai) neural search API for
  semantic web and code search. Supports six search modes (`auto`,
  `fast`, `deep`, `deep-reasoning`, etc.), domain filtering, and full-text
  retrieval. Requires an `EXA_API_KEY` environment variable.

---

## Architecture

AivoCode is designed in thin layers. Each layer is a ~10-line wrapper
around the layer below:

```
┌─ CLI ───────────────────────────────────────────────┐
│  aivocode lsp symbols file.py                       │
│  argparse → HTTP POST /lsp/symbols → print JSON     │
│  (only httpx + stdlib — zero local processing)      │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (localhost:8000)
┌─ REST API ──────────────────────────────────────────┐
│  FastAPI app (api_server/app.py)                    │
│  Thin routes → delegates to lsp / codebase / web_ops│
│  Swagger docs at /docs                              │
└──────┬──────────────┬───────────────┬───────────────┘
       │              │               │
┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼──────────────┐
│  lsp/       │ │ codebase/  │ │ web_ops/            │
│             │ │             │ │                     │
│  Daemon     │ │ Overview    │ │ Fetch (Chrome +     │
│  Symbols    │ │ Read        │ │   Crawl4AI)         │
│  References │ │ Explain     │ │ Search (Exa API)    │
│  CallHier   │ │ Impact      │ │                     │
│  Diagnostics│ │ ImportGraph │ │                     │
│  Rename     │ │ Tree-sitter │ │                     │
│  Hover      │ │ Resolution  │ │                     │
└──────┬──────┘ └─────────────┘ └─────────────────────┘
       │
┌──────▼──────────────────────────────────────────────┐
│  file_watcher/                                      │
│  watchfiles + gitignore → LSP + import graph events │
└─────────────────────────────────────────────────────┘
```

**Key design principles:**

- **Thin layers**: CLI, REST routes, and public API functions are all thin
  wrappers. All logic lives in the libraries.
- **Server-side workspace detection**: CLI sends absolute paths; server
  detects the git root via `git rev-parse --show-toplevel`. Zero git
  knowledge in the CLI.
- **Isolated CLI**: `cli/install.sh` creates a dedicated venv at
  `~/.aivocode-cli/` with only `httpx` as a dependency. Zero impact on
  the devcontainer's conda environment.
- **One daemon per workspace**: Unix sockets under
  `<workspace>/.aivocode/daemons/`. Each daemon runs its own LSP server
  and maintains its own import graph.

---

## Quick Start

### 1. Start the REST API server

```bash
fastapi dev api_server/app.py
# Server listening on http://127.0.0.1:8000
# Interactive docs at http://127.0.0.1:8000/docs
```

For production: `fastapi run api_server/app.py`

### 2. Install the CLI (one-time)

```bash
bash cli/install.sh
```

Creates an isolated venv at `~/.aivocode-cli/`, installs the CLI with
`httpx` as its only dependency, and links `aivocode` to `~/.local/bin/`.

### 3. Run CLI commands

```bash
# Set the server URL for local dev (default is http://localhost:8000)
export AIVOCODE_URL=http://localhost:8000

# aivocode lsp — direct LSP queries (auto-starts the daemon)
aivocode lsp symbols mock_pkg/utils.py
aivocode lsp references mock_pkg/utils.py --line 10 --character 5
aivocode lsp definition mock_pkg/utils.py --line 42 --character 8
aivocode lsp diagnostics mock_pkg/utils.py
aivocode lsp start
aivocode lsp status --pretty-format
aivocode lsp stop

# aivocode codebase — agent-facing exploration
aivocode codebase overview mock_pkg/utils.py
aivocode codebase explain mock_pkg/utils.py --symbol my_func
aivocode codebase import-dependents mock_pkg/utils.py --depth 2
aivocode codebase affected-tests mock_pkg/utils.py --depth 10

# aivocode webfetch / websearch — web intelligence
aivocode webfetch https://example.com
aivocode websearch "python asyncio patterns" --num-results 5
```

**Development mode** (from the repo root, no reinstall needed):

```bash
python -m cli lsp symbols mock_pkg/utils.py
```

---

## Development with Multiple Worktrees

Each worktree is self-contained — its own REST API server, daemon
subprocess, and code. Start servers on different ports:

```bash
# Terminal 1 — worktree A
fastapi dev api_server/app.py                    # → :8000

# Terminal 2 — worktree B
fastapi dev api_server/app.py --port 8001        # → :8001
```

Point the CLI at the correct server with `AIVOCODE_URL`:

```bash
cd /path/to/worktree-a
AIVOCODE_URL=http://localhost:8000 aivocode lsp symbols utils.py

cd /path/to/worktree-b
AIVOCODE_URL=http://localhost:8001 aivocode lsp symbols some_file.py
```

---

## Package Structure

```
api_server/         REST API (FastAPI)
  app.py              App factory, CORS, router registration
  routes/             One module per route group (lsp, codebase, web_ops)

cli/                CLI (thin HTTP client)
  install.sh          Isolated venv installer
  main.py             Argparse dispatch
  commands/           One module per subcommand (lsp, codebase, webfetch, websearch)

lsp/                LSP library (core engine)
  _daemon.py          Daemon lifecycle: spawn, query dispatch, idle/shutdown
  client.py           LspClient — async context manager for language server
  _protocol.py        LD-JSON over Unix sockets
  _serialize.py       LSP results → JSON (position normalization, kind names)
  _workspace.py       Git workspace detection
  config.py           Language config (lsp_config.toml)
  _translate.py       File watcher events → LSP didChangeWatchedFiles

codebase/           Agent-facing exploration tools
  __init__.py         Public API: overview, read, explain, search, impact, import graph
  _analyze.py         Orchestration: composes LSP calls for high-level tools
  _read.py            Symbol body reader + tree-sitter import extraction
  _resolve.py         Name → position resolution via LSP documentSymbols
  _import_graph.py    Workspace-wide reverse import graph + BFS queries
  _treesitter.py      Lazy-loaded tree-sitter parser registry
  _lang_handlers/      Pluggable import parsers (PythonHandler, extensible)

web_ops/            Web intelligence
  fetcher.py          Stealth Chrome + Crawl4AI page fetch with truncation
  searcher.py         Exa neural search API client

file_watcher/       File system watching (watchfiles)
tests/              Test suite (unit, integration, e2e, snapshots)
specs/              Feature specifications
```

Detailed READMEs are in `web_ops/`, `cli/`, and `lsp/`. See
`AGENTS.md` for development conventions and tooling.

---

## Tests

```bash
# All tests (~4.5 min)
pytest

# LSP integration (LspClient, symbols, diagnostics)
pytest tests/integration/lsp/ -v

# Import graph (unit + integration + schema)
pytest tests/unit/codebase/test_import_graph.py \
       tests/integration/test_import_graph.py \
       tests/e2e/test_import_graph_schema.py -v

# E2E: CLI + REST API (starts server)
pytest tests/e2e/test_lsp_cli.py -v

# Run by keyword
pytest -k "import_graph"
```

---

## Key Design Decisions

| Decision | Why |
|---|---|
| Daemon per workspace, auto-started | Keeps LSP server alive across CLI invocations — no re-indexing on every query |
| `force_polling=True` | Docker-mounted volumes don't get inotify events |
| Crash-fast | Watcher or LSP crash → daemon exits → next query auto-restarts fresh. Stale state is worse than a clean start |
| Thin layers everywhere | CLI, REST routes, public API — all ~10-line wrappers. Library owns the logic |
| REST API, not direct import | Universal endpoint for CLI, MCP, browser consumers. Same API regardless of transport |
| Server-side workspace detection | CLI sends absolute paths (cwd / file); server calls `detect_workspace()` via git. Zero git knowledge in CLI |
| Standalone CLI with isolated venv | `cli/install.sh` creates `~/.aivocode-cli/` — only `httpx` + stdlib. Zero impact on the devcontainer's conda env |

## Gotchas

- **`from __future__ import annotations`** must be the very first statement
  in any file that uses it (PEP 236).
- **Unix socket path limit** is 108 bytes — the socket hash is truncated to
  24 hex chars to stay under the limit.
- **Workspace detection** is server-side. CLI sends absolute paths and
  the server calls `detect_workspace()` via git. No `lsp` imports in the CLI.
- **`detect_workspace()`** accepts both files and directories. Passing
  `Path.cwd()` works for `start`/`stop`/`status`.
- **File existence** is checked before calling the LSP server — missing
  files return a clean JSON error instead of crashing the daemon.
- **Daemon `start_new_session=True`** survives parent exit. Tests clean up
  with `POST /lsp/stop` and remove socket files.
- **Smoke/probe files** under `tmp/` must not use `test_` prefix — only real
  pytest tests may. This keeps `affected-tests` output accurate.
- **`python -m cli` for development** picks up uncommitted changes from the
  current worktree without reinstalling.
