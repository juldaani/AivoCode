# cli

Thin HTTP client for the aivocode REST API. Parses CLI arguments, sends HTTP
requests, prints JSON. All processing happens server‑side. The CLI has zero
imports from ``lsp``, ``web_ops``, or ``file_watcher`` — only ``httpx`` + stdlib.

## Install (standalone, isolated)

```bash
# One command — creates dedicated venv, installs CLI, links binary.
./cli/install.sh

# Or custom venv path (for Dockerfiles):
./cli/install.sh --venv /opt/aivocode-cli
```

This installs ``aivocode-cli`` into an isolated venv (``~/.aivocode-cli/``).
``httpx`` and its deps live only there — zero impact on your devcontainer's
conda env or system Python.

After install:

```bash
# Default is http://aivocode:8000 (compose service name). Override for local dev:
export AIVOCODE_URL=http://localhost:8000
aivocode lsp symbols src/main.py
aivocode webfetch https://example.com
aivocode websearch "python asyncio"

# Codebase exploration (agent-facing tools)
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
```

## Commands

```
aivocode lsp symbols <file> [--workspace PATH] [--pretty-format]
aivocode lsp start [--workspace PATH] [--pretty-format]
aivocode lsp stop [--workspace PATH] [--pretty-format]
aivocode lsp status [--workspace PATH] [--pretty-format]
aivocode codebase tree [--suffix .py] [--workspace PATH] [--pretty-format]
aivocode codebase overview <file> [--depth N] [--workspace PATH] [--pretty-format]
aivocode codebase read <file> --symbol NAME [--line N] [--workspace PATH] [--pretty-format]
aivocode codebase explain <file> --symbol NAME [--line N] [--workspace PATH] [--pretty-format]
aivocode codebase search <query> [--kind CLASS] [--limit N] [--workspace PATH] [--pretty-format]
aivocode codebase incoming-calls <file> --symbol NAME [--line N] [--pretty-format]
aivocode codebase outgoing-calls <file> --symbol NAME [--line N] [--include-external] [--pretty-format]
aivocode codebase references <file> --symbol NAME [--line N] [--pretty-format]
aivocode codebase impact <file> --symbol NAME [--line N] [--pretty-format]
aivocode codebase import-dependents <file> [--depth N] [--workspace PATH] [--pretty-format]
aivocode codebase import-dependencies <file> [--workspace PATH] [--pretty-format]
aivocode codebase affected-tests <file> [--depth N] [--workspace PATH] [--pretty-format]
aivocode webfetch <url> [options] [--pretty-format]
aivocode websearch <query> [options] [--pretty-format]
```

The CLI connects to the REST API at ``$AIVOCODE_URL`` (defaults to
``http://aivocode:8000`` — the compose service name; override via env var for local dev).

## Global flag: ``--pretty-format``

Available on every subcommand.  Produces indented, multi‑line JSON output
for human readability:

```
aivocode lsp status --pretty-format
aivocode webfetch --pretty-format https://example.com
```

Without it, output is compact single‑line JSON (saves tokens for agent consumers).

## Workspace detection

The CLI no longer does client‑side workspace detection.  It sends absolute
paths (cwd or file path) to the REST API, and the **server** detects the git
workspace root via ``git rev-parse --show-toplevel``.

- ``lsp symbols <file>`` — CLI resolves the file to absolute, server detects
  workspace from the file's parent directory.
- ``lsp start`` / ``stop`` / ``status`` — CLI sends ``pwd`` (absolute), server
  detects workspace from cwd.
- ``--workspace PATH`` — CLI resolves to absolute, sends as explicit override.
  Server uses it directly (no detection).

## Flags

### lsp

All lsp subcommands accept ``--workspace PATH`` (override git‑based detection,
now server‑side).

### webfetch

| Flag | Purpose |
|---|---|
| ``--heading TEXT`` | Extract a section by heading (repeatable) |
| ``--line-range N-M`` | Extract lines from the cached page (repeatable) |
| ``--navigation`` | Include page links (internal/external) |
| ``--js-render`` | Wait for JS-heavy SPAs to settle |
| ``--wait-until`` | ``load`` (default), ``domcontentloaded``, or ``networkidle`` |
| ``--refresh-cache`` | Bypass cache, always fetch fresh |

### websearch

| Flag | Purpose |
|---|---|
| ``--type`` | ``auto`` (default), ``fast``, ``instant``, ``deep-lite``, ``deep``, ``deep-reasoning`` |
| ``--num-results N`` | Number of results (default 10) |
| ``--include-domains DOMAIN`` | Restrict to domain (repeatable) |
| ``--exclude-domains DOMAIN`` | Exclude domain (repeatable) |
| ``--full-text`` | Return full page text instead of highlights |

## Development (from repo root)

When developing the aivocode repo itself, you can still use:

```bash
python -m cli lsp symbols tests/data/mock_repos/python/mock_pkg/utils.py
```

This picks up uncommitted changes immediately — no reinstall needed.

## Structure

```
cli/
├── pyproject.toml       # Standalone package: aivocode-cli (dep: httpx only)
├── install.sh           # Isolated venv install script
├── __init__.py
├── __main__.py          # python -m cli entry point
├── main.py              # Argparse dispatch
├── _utils.py            # Shared: HTTP transport, JSON output, --pretty-format
└── commands/
    ├── lsp.py           # lsp subcommand (symbols, start, stop, status)
    ├── codebase.py      # codebase subcommand (tree, overview, read, explain, search, impact)
    ├── webfetch.py      # webfetch subcommand
    └── websearch.py     # websearch subcommand
```

## REST API reference

| Method | Path | Body / Params |
|---|---|---|
| ``POST`` | ``/lsp/symbols`` | ``{"file": "...", "workspace?": "..."}`` |
| ``POST`` | ``/lsp/start`` | ``{"workspace": "..."}`` |
| ``POST`` | ``/lsp/stop`` | ``{"workspace": "..."}`` |
| ``GET`` | ``/lsp/status`` | ``?workspace=...`` |
| ``POST`` | ``/codebase/tree`` | ``{"suffix?": ".py", "workspace?": "..."}`` |
| ``POST`` | ``/codebase/overview`` | ``{"file": "...", "depth?": 0, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/read`` | ``{"file": "...", "symbol_name": "...", "line?": N, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/explain`` | ``{"file": "...", "symbol_name": "...", "line?": N, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/search`` | ``{"query": "...", "kind?": "...", "limit?": 50, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/incoming-calls`` | ``{"file": "...", "symbol_name": "...", "line?": N, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/outgoing-calls`` | ``{"file": "...", "symbol_name": "...", "line?": N, "workspace_only?": true}`` |
| ``POST`` | ``/codebase/references`` | ``{"file": "...", "symbol_name": "...", "line?": N, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/impact`` | ``{"file": "...", "symbol_name": "...", "line?": N, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/import-dependents`` | ``{"file": "...", "depth?": 1, "workspace?": "..."}`` |
| ``POST`` | ``/codebase/import-dependencies`` | ``{"file": "...", "workspace?": "..."}`` |
| ``POST`` | ``/codebase/affected-tests`` | ``{"file": "...", "depth?": 4, "workspace?": "..."}`` |
| ``POST`` | ``/web_ops/webfetch`` | ``{"url": "...", "wait_until?": "load", ...}`` |
| ``POST`` | ``/web_ops/websearch`` | ``{"query": "...", "num_results?": 10, ...}`` |
| ``GET`` | ``/health`` | — |
