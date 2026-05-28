# AGENTS

---

## Tooling (OpenCode)
- Runtime: Python 3.12 (see `env-aivocode.yml`).
- Ruff works automatically out of the box, through OpenCode. Opencode automatically
  calls ruff after file changes and notifies the agent of possible problems.

## Environments (Safety Rule)
- Do not build, edit, update, or remove environments in this repo.
- If an environment change is needed, ask the user to do it (or to explicitly request it).
- Do not read, expose, or commit secrets (e.g., `.env` files, credentials, API keys).

## Code Standards (Explicit)
- Line length: max 100 characters.
- Typing: follow PEP 484+; prefer explicit types for public functions/methods.
- `Any`: avoid unless there is a clear reason; document why when used.
- Exceptions: do not use generic `except Exception`; catch specific exceptions or let it fail.
- Imports: use `import numpy as np`.
- Performance: prefer NumPy vectorized operations over Python loops when feasible.

## Docs & Comments Policy
- Docstrings/comments should explain: what it does (short), why it exists/why this way,
  and how to use or extend it (contract, lifecycle, invariants).
- Assume junior dev or someone not familiar -> liberal and more explaining commenting policy.
- Module docstring: required for non-trivial/infrastructure modules (protocols,
  concurrency, parsing, caching). Include What/Why/How-to-read (entrypoints + flow). Prefer 
  a multi-line format with short sections and bullets when helpful.
- Public API (non-`_`): docstring required (purpose, key params/returns, side effects,
  assumptions).
- Private helpers (`_`): docstring when non-obvious (protocol/concurrency/edge cases)
  or reused.
- Inline comments: be liberal to improve readability; avoid only the truly obvious.
- If broad exception handling is intentional (e.g., background loops), add a brief
  comment explaining why it’s safe and what gets logged.

## Devcontainer
- Config: `.devcontainer/` — extends `ghcr.io/slamengine/devcontainer-base/opencode:latest`.
- Conda env is auto-activated in all shells (micromamba).

## Commands
### REST API server
- Start: `fastapi dev api_server/app.py` (development, auto-reload on changes).
- The server listens on `http://127.0.0.1:8000` by default.
- Endpoints are documented at `http://127.0.0.1:8000/docs` (Swagger UI).
- For production: `fastapi run api_server/app.py`

### CLI
- Run CLI commands: `python -m cli <subcommand> [args]` from the repo root.
- There is no global `aivocode` install — each worktree runs its own CLI code.
  Running `python -m cli` ensures imports resolve to the current worktree's
  `cli/`, `lsp/`, `web_ops/`, and `file_watcher/` packages.
- The CLI sends HTTP requests to the REST API server. Set `AIVOCODE_URL`
  to point to the correct server (defaults to `http://localhost:8000`).
- Examples:
  - `python -m cli lsp symbols mock_pkg/utils.py`
  - `python -m cli lsp start`
  - `python -m cli lsp stop`
  - `python -m cli lsp status`
  - `python -m cli webfetch https://example.com`
  - `python -m cli websearch "python asyncio" --num-results 5`

### Development with multiple worktrees
- Each worktree is self-contained: its own REST API server, its own daemon
  subprocess, its own code.  No global install, no cross-contamination.
- Start one server per worktree on different ports:

  ```bash
  # Terminal 1 — lsp-cli-endpoint
  cd /workspaces/lsp-cli-endpoint && fastapi dev api_server/app.py
  # → :8000

  # Terminal 2 — aivocode (main)
  cd /workspaces/aivocode && fastapi dev api_server/app.py --port 8001
  # → :8001
  ```

- Run CLI from the worktree you're working in, pointing to its own server:

  ```bash
  cd /workspaces/lsp-cli-endpoint
  AIVOCODE_URL=http://localhost:8000 python -m cli lsp symbols utils.py
  ```

  The default `AIVOCODE_URL=http://localhost:8000` means the CLI in each
  worktree connects to its own server by default (as long as you use the
  default port in that worktree).

- To query a different worktree, use absolute file paths and point to
  its server:

  ```bash
  cd /workspaces/lsp-cli-endpoint
  AIVOCODE_URL=http://localhost:8001 python -m cli lsp symbols /workspaces/aivocode/src/main.py
  ```

### Tests
- Run all tests: `pytest`
- Run a single file: `pytest path/to/test_file.py`
- Run a single test: `pytest path/to/test_file.py::TestClass::test_name`
- Run by keyword: `pytest -k "keyword"`

### Executing code
- Run Python code: `python -m module.path` or `python path/to/script.py`

---