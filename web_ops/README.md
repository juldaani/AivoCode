# web_ops

Stealth web fetching via CloakBrowser + Crawl4AI with content-aware truncation and ToC generation.

## Public API

```python
from web_ops import fetch_urls, result_to_output_json, FetchResult
```

| Function | Purpose |
|---|---|
| `fetch_urls(url, *, headings, line_ranges, ...)` | Fetch a URL or extract sections. Returns `FetchResult`. |
| `result_to_output_json(result)` | Serialize a `FetchResult` to the standard JSON format. |
| `result_to_output_json(result, compact_toc=False)` | Pretty-print the ToC for human readability. |

## Usage

```python
import asyncio
from web_ops import fetch_urls, result_to_output_json

# Full page fetch — truncated to ToC if > 10 000 chars
result = asyncio.run(fetch_urls("https://example.com"))
print(result_to_output_json(result))

# Extract a section by heading
result = asyncio.run(fetch_urls("https://example.com", headings=["API Reference"]))
print(result.markdown)

# Extract multiple sections in one call
result = asyncio.run(fetch_urls(
    "https://docs.python.org/3/library/functions.html",
    headings=["abs()", "all()", "any()"],
))
print(result.markdown)
```

## CLI

```
python -m cli webfetch https://example.com
python -m cli webfetch https://example.com --heading "API Reference"
python -m cli webfetch https://nodejs.org/api/fs.html --pretty-format
```

## How it works

1. Launches a stealth browser via CloakBrowser at CDP port 9243
2. Crawl4AI connects and captures the page as raw markdown
3. Content > 10 000 chars → chunked into a heading-aware tree, projected to a compact ToC
4. Full content cached to disk (`tmp/aivocode/cache/`) for 15 min, with section-level retrieval
5. Feed-page detection warns when the ToC may be unreliable (short lines, many links)
