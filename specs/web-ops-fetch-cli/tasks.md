# Tasks: web-ops-fetch-cli

## Status
- Total: 14
- Completed: 14
- Remaining: 0

---

## Tasks

### Group 1: Rename package
Checkpoint: `web-ops/` is renamed to `web_ops/` — valid Python import name.

- [x] 1.1 Rename `web-ops/` directory to `web_ops/`
  - `web-ops/` → `web_ops/` (rename)

### Group 2: Core library
Checkpoint: `from web_ops import fetch_url, FetchResult` works. `fetch_url()` launches a stealth browser via CloakBrowser, fetches via Crawl4AI, and returns a `FetchResult` with markdown + status details. No CLI code, no print().

- [x] 2.1 Create `web_ops/fetcher.py`
  - `web_ops/fetcher.py` (add) — `FetchResult` dataclass, `fetch_url()` async function, module-level constants (`_CDP_PORT`, `_PAGE_TIMEOUT_MS`, `_DELAY_BEFORE_RETURN_HTML_S`, `_DEFAULT_WAIT_UNTIL`). Extracts browser launch + Crawl4AI connection + result mapping logic from `tst_web_fetch.py` as a reusable library. On failure, returns `FetchResult(success=False)` with status_code and error populated — never raises for runtime conditions.

- [x] 2.2 Update `web_ops/__init__.py` to re-export public API
  - `web_ops/__init__.py` (edit: add imports and `__all__`) — `from web_ops.fetcher import fetch_url, FetchResult`

### Group 3: CLI package
Checkpoint: `python -m cli fetch <url>` works end-to-end, and `aivocode fetch <url>` works after Group 4.

- [x] 3.1 Create `cli/__init__.py` and `cli/commands/__init__.py`
  - `cli/__init__.py` (add) — package init with module docstring
  - `cli/commands/__init__.py` (add) — package init

- [x] 3.2 Create `cli/commands/fetch.py` — fetch subcommand
  - `cli/commands/fetch.py` (add) — `add_subparser(subparsers)` registers the `fetch` command with `url` positional and `--wait-until` optional. `handle(args) -> int` calls `asyncio.run(fetch_url(...))`, prints `result.markdown` to stdout, logs status to stderr, returns `0` if `result.success` else `1`.

- [x] 3.3 Create `cli/main.py` — argparse dispatcher
  - `cli/main.py` (add) — `main() -> int`: top-level argparse with subparsers. Imports `fetch.add_subparser` and registers it. On parse, dispatches to `args.func(args)`. Module docstring documents CLI structure and extensibility (future subcommands).

### Group 4: Build config
Checkpoint: `aivocode fetch <url>` works as a system command (via `pip install -e .` or equivalent).

- [x] 4.1 Create `pyproject.toml` at repo root
  - `pyproject.toml` (add) — minimal `[project]` metadata (name, version, requires-python) and `[project.scripts]` entry: `aivocode = "cli.main:main"`

- [x] 4.2 Install package in development mode
  - Shell: `pip install -e .` — makes `aivocode` available on PATH

### Group 5: Verification
Checkpoint: All acceptance criteria pass. Library import, CLI static + SPA + flag + failure cases, file preservation, lint.

- [x] 5.1 Verify Python import works
  - Shell: `python -c "from web_ops import fetch_url, FetchResult; print('OK')"`

- [x] 5.2 Smoke test: static page (no flag)
  - Shell: `aivocode fetch https://yle.fi/` — exits 0, markdown on stdout, logs on stderr

- [x] 5.3 Smoke test: SPA page (no flag, defaults to networkidle)
  - Shell: `aivocode fetch https://codesandbox.io/s/new` — exits 0, React content visible

- [x] 5.4 Smoke test: `--wait-until` flag override
  - Shell: `aivocode fetch https://example.com --wait-until load` — exits 0, respects override

- [x] 5.5 Smoke test: unreachable URL (failure case)
  - Shell: `aivocode fetch https://nonexistent.invalid` — exits non-zero (1), no markdown on stdout

- [x] 5.6 Verify reference implementation unchanged
  - Shell: `git diff --exit-code web_ops/tst_web_fetch.py` — no diff

- [x] 5.7 Lint check
  - Shell: `ruff check web_ops/ cli/` — passes with no errors
