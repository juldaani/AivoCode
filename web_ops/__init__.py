"""Web operations utilities — stealth fetching, extraction, and content processing.

What this package provides
- fetch_url: stealth web page fetcher via CloakBrowser + Crawl4AI.
- FetchResult: structured result dataclass (markdown, success, status, error).

How to use
- Import and call::

    from web_ops import fetch_url, FetchResult

    result = await fetch_url("https://example.com")
    print(result.markdown)

See Also
- web_ops.fetcher for the full module documentation.
- web_ops.tst_web_fetch for the standalone reference implementation.
"""

from web_ops.fetcher import FetchResult, fetch_urls, result_to_output_json

__all__ = ["fetch_urls", "FetchResult", "result_to_output_json"]
