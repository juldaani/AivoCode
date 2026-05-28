"""Web operations utilities — stealth fetching, extraction, and neural search.

What this package provides
- ``fetch_urls``: stealth web page fetcher via CloakBrowser + Crawl4AI.
- ``FetchResult``: structured result dataclass (markdown, success, HTTP status,
  error, navigation, ToC, truncation metadata).
- ``web_search``: neural search via the Exa Search API
  (web and code — same endpoint, vary ``type`` and query).
- ``SearchResult`` / ``ResultItem``: dataclasses for search results.
- Serializers available directly from each sub-module:
  ``from web_ops.fetcher import result_to_output_json`` and
  ``from web_ops.searcher import result_to_output_json``.

How to use
- Import and call::

    from web_ops import fetch_urls, web_search

    page = await fetch_urls("https://example.com")
    print(page.markdown)

    results = await web_search("latest AI news")
    for r in results.results:
        print(r.title, r.url)

See Also
- ``web_ops.fetcher`` for the full fetch module documentation.
- ``web_ops.searcher`` for the search module documentation.
"""

from web_ops.fetcher import FetchResult, fetch_urls
from web_ops.searcher import ResultItem, SearchResult, web_search

__all__ = [
    "fetch_urls",
    "FetchResult",
    "ResultItem",
    "SearchResult",
    "web_search",
]
