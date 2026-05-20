# Web Ops Fetch CLI

## Summary

Add a production-quality Python library (`web_ops.fetch_url`) for stealth web page fetching
(CloakBrowser + Crawl4AI) and a CLI (`aivocode fetch`) that agents invoke to fetch web content
as markdown. The library is transport-agnostic so the same function can be called from a CLI,
a Python script, or future FastAPI / MCP endpoints.

## Scope

### In scope
- Rename `web-ops/` → `web_ops/` for valid Python imports
- Create `web_ops/fetcher.py` with `FetchResult` dataclass and `fetch_url()` function
- Update `web_ops/__init__.py` to re-export `fetch_url` and `FetchResult`
- Create `cli/` package: `main.py` (argparse dispatcher) + `commands/fetch.py`
- Create minimal `pyproject.toml` at repo root with `[project.scripts]` entry
- Smoke-test: static page (yle.fi) + SPA (codesandbox.io) + `--wait-until` flag

### Out of scope
- Modifying `tst_web_fetch.py` (frozen reference implementation)
- Multi-fetch browser reuse / connection pooling
- FastAPI or MCP server endpoints (future transport layer)
- Docker Compose cross-container wiring
- Additional CLI subcommands beyond `fetch`
- Non-markdown output formats (HTML, JSON, screenshot)

## Requirements

- **R1**: `from web_ops import fetch_url, FetchResult` must work as a normal Python import
- **R2**: `await fetch_url(url)` returns a `FetchResult` containing `markdown`, `success`, `status_code`, and `error`
- **R3**: On recoverable failure (HTTP errors, timeouts, empty responses), returns `FetchResult(success=False)` with details — never raises
- **R4**: Raises only for unrecoverable programming errors (e.g. CloakBrowser binary not found, CDP handshake failure)
- **R5**: `aivocode fetch <url>` prints markdown to stdout, logs/status to stderr
- **R6**: `aivocode fetch <url> --wait-until {domcontentloaded,load,networkidle}` supported
- **R7**: Default `--wait-until` is `networkidle` (SPA-safe out of the box)
- **R8**: `aivocode fetch` returns exit code 0 on success, 1 on failure
- **R9**: `tst_web_fetch.py` remains unchanged
- **R10**: Same code path works for both static and JS-heavy (SPA) pages

## Proposed Design

### File Layout

```
                                   [NEW]
web_ops/                     <── web-ops/ (renamed)
├── __init__.py                    UPDATED — re-exports fetch_url, FetchResult
├── tst_web_fetch.py               FROZEN — no changes
└── fetcher.py                     NEW — FetchResult, fetch_url(), constants

cli/                               NEW
├── __init__.py
├── main.py                        argparse subcommand dispatcher
└── commands/
    ├── __init__.py
    └── fetch.py                   "fetch" subcommand handler

pyproject.toml                     NEW — project metadata + console_scripts
```

### Separation of Concerns

```
┌────────────────────────────────────────────────────────┐
│ web_ops/fetcher.py  — Library layer (no I/O opinions)  │
│                                                        │
│ async def fetch_url(url, *, wait_until) -> FetchResult:│
│     launch CloakBrowser (CDP)                          │
│     → connect Crawl4AI (AsyncWebCrawler)               │
│     → arun(url, CrawlerRunConfig(...))                 │
│     → close browser                                    │
│     → return FetchResult(markdown, success, status,    │
│                          error)                        │
│                                                        │
│ NO print(), NO sys.exit(), NO argparse.                │
│ Silent — caller decides what to do with the result.    │
└────────────────────────┬───────────────────────────────┘
                         │ import
        ┌────────────────┼────────────────┐
        ▼                                 ▼
┌───────────────────┐          ┌─────────────────────────┐
│ Python API usage  │          │ cli/commands/fetch.py   │
│ (agent code)      │          │ — CLI "UI" layer        │
│                   │          │                         │
│ from web_ops      │          │ def handle(args) -> int │
│   import fetch_url│          │   result = asyncio.run(  │
│                   │          │     fetch_url(url, ...)) │
│ result = await    │          │   print(result.markdown) │
│   fetch_url(url)  │          │   return 0 if result    │
│                   │          │     .success else 1      │
└───────────────────┘          └───────────┬─────────────┘
                                           │ registered by
                                           ▼
                                  ┌──────────────────┐
                                  │ cli/main.py       │
                                  │ def main() -> int │
                                  │   parser → subcmd │
                                  │   dispatch        │
                                  └──────┬───────────┘
                                         │ entry point
                                         ▼
                                  pyproject.toml
                                  [project.scripts]
                                  aivocode = "cli.main:main"
```

### Data Flow (CLI invocation)

```
aivocode fetch https://example.com --wait-until load
  │
  ▼
cli/main.py::main()
  │  argparse parses subcommand "fetch" + url + --wait-until
  ▼
cli/commands/fetch.py::handle(args)
  │  result = asyncio.run(fetch_url(args.url, wait_until=args.wait_until))
  ▼
web_ops/fetcher.py::fetch_url(url, wait_until)
  │  launch_async(headless=True, CDP port 9243)
  │  AsyncWebCrawler(config=BrowserConfig(browser_mode="cdp", cdp_url="http://127.0.0.1:9243"))
  │  crawler.arun(url, config=CrawlerRunConfig(wait_until=..., page_timeout=15000, delay=2.0))
  │  browser.close()
  ▼
returns FetchResult(markdown, success, status_code, error)
  │
  ▼
CLI prints result.markdown to stdout, logs "Done. N chars." to stderr
  │
returns 0 if result.success else 1
```

### Public API

```python
from web_ops import fetch_url, FetchResult

# Simple
result: FetchResult = await fetch_url("https://example.com")
print(result.markdown)  # str — page body, "" on failure

# Inspector failure with detail
if not result.success:
    match result.status_code:
        case 403: ...   # bot block — try different fingerprint
        case 404: ...   # dead link — stop trying
        case 500: ...   # server error — retry later
    if result.error:
        # e.g. "timeout", "CDP connection refused", "empty response"
        print(f"Fetch failed: {result.error}")

# With SPA tweak
result = await fetch_url("https://spa-site.com", wait_until="load")
```

### `FetchResult` Dataclass

```python
@dataclass
class FetchResult:
    markdown: str = ""
    success: bool = False
    status_code: int | None = None
    error: str | None = None
    # error values: "timeout", "empty", None (= no error), or a Crawl4AI message
```

| Field | Type | Meaning |
|---|---|---|
| `markdown` | `str` | Page body as markdown. Empty string on failure — always safe to use. |
| `success` | `bool` | `True` if the crawl completed and content was extracted. |
| `status_code` | `int \| None` | HTTP status from the response. `None` if the fetch never reached the server (timeout, DNS failure, CDP error). |
| `error` | `str \| None` | Human-readable error label. `None` on success. Common values: `"timeout"`, `"empty"`, Crawl4AI error string. |

### Constants (in `web_ops/fetcher.py`)

| Constant | Value | Purpose |
|---|---|---|
| `_CDP_PORT` | `9243` | Bridge port between CloakBrowser and Crawl4AI |
| `_PAGE_TIMEOUT_MS` | `15_000` | Max page load time — short to avoid hanging on long-polling pages |
| `_DELAY_BEFORE_RETURN_HTML_S` | `2.0` | Post-render buffer for hydration, animations |
| `_DEFAULT_WAIT_UNTIL` | `"networkidle"` | SPA-safe default |

### CLI Help (expected output)

```
usage: aivocode [-h] {fetch} ...

positional arguments:
  {fetch}
    fetch       Fetch a URL and print its content as markdown

options:
  -h, --help    show this help message and exit
```

```
usage: aivocode fetch [-h] [--wait-until {domcontentloaded,load,networkidle}] url
```

### pyproject.toml (minimal)

```toml
[project]
name = "aivocode"
version = "0.1.0"
requires-python = ">=3.12"

[project.scripts]
aivocode = "cli.main:main"
```

Only the `[project.scripts]` section is strictly required for the CLI. Other metadata (description, dependencies, authors) can be filled later.

### Why `FetchResult` instead of bare `str` or raising

The caller is an AI agent. The agent's workflow is:

```
1. Agent decides "I need the content of https://example.com"
2. Runs aivocode fetch https://example.com
3. Reads the output
```

If the fetch fails, the agent needs to know **why** to make an intelligent decision:

| Scenario | Bare `str` / `""` | `FetchResult` |
|---|---|---|
| Genuinely blank page | `""` — can't tell if real | `success=True, markdown=""` — real |
| 403 bot block | `""` — invisible | `success=False, status_code=403` → try proxy |
| 404 not found | `""` — invisible | `success=False, status_code=404` → stop, link dead |
| 500 server error | `""` — invisible | `success=False, status_code=500` → retry later |
| 15s timeout | `""` — invisible | `success=False, error="timeout"` → retry with `--wait-until load` |

`FetchResult.markdown` is always safe to use — it's `""` on failure. But agents that want
more intelligence can inspect `success`, `status_code`, and `error` without try/except.

Unrecoverable programming errors (e.g. CloakBrowser binary missing, broken CDP handshake)
DO raise — these are bugs, not runtime conditions.

## Acceptance Criteria

- [ ] `from web_ops import fetch_url, FetchResult` imports without error
- [ ] `aivocode fetch https://yle.fi` prints markdown to stdout, exits 0
- [ ] `aivocode fetch https://codesandbox.io/s/new` prints React SPA content, exits 0
- [ ] `aivocode fetch https://example.com --wait-until load` respects the override
- [ ] `aivocode fetch https://nonexistent.invalid` exits non-zero (1) with `success=False`
- [ ] `tst_web_fetch.py` is identical to its committed version (no changes)
- [ ] All log/status output goes to stderr; only `result.markdown` goes to stdout
- [ ] `ruff check web_ops/ cli/` passes
