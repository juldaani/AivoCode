"""Web operations route handlers — thin wrappers around the ``web_ops`` library.

Every route delegates directly to the corresponding public ``web_ops.*``
function.  No business logic lives here — this module has the same role
as ``cli/commands/webfetch.py`` before the HTTP refactor.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from web_ops import HybridSearcher, fetch_urls, web_search
from web_ops.fetcher import _flatten_chunks, _parse_chunked, _read_cache_markdown

router = APIRouter(prefix="/web_ops", tags=["web_ops"])


# ── Request models ────────────────────────────────────────────────────────────


class WebfetchBody(BaseModel):
    """Request body for POST /web_ops/webfetch."""

    url: str
    wait_until: Literal["domcontentloaded", "load", "networkidle"] = "load"
    headings: list[str] | None = None
    line_ranges: list[str] | None = None
    refresh_cache: bool = False
    include_navigation: bool = False
    limit: int = 20000
    # ── Hybrid search fields (optional — search mode activates when set) ──
    query: str | None = None
    query_page: int = 0
    query_vector_weight: float = 0.65


class WebsearchBody(BaseModel):
    """Request body for POST /web_ops/websearch."""

    query: str
    type: str = "auto"
    num_results: int = 10
    highlights: bool = True
    text: bool = False
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/webfetch")
async def webfetch(body: WebfetchBody):
    """Fetch a URL via CloakBrowser + Crawl4AI and return structured result.

    All parameters mirror the ``fetch_urls()`` public API.  The server
    handles browser automation and HTML → markdown conversion.

    When ``query`` is provided, the response switches to *search mode*:
    the page is chunked, flattened into text nodes, indexed with a hybrid
    (vector + BM25) retriever, and the top matching chunks are returned
    with scores — no raw markdown or ToC.
    """
    result = await fetch_urls(
        body.url,
        wait_until=body.wait_until,  # type: ignore[arg-type]
        headings=body.headings,
        line_ranges=body.line_ranges,
        refresh_cache=body.refresh_cache,
        include_navigation=body.include_navigation,
        limit=body.limit,
    )

    # ── Search mode ────────────────────────────────────────────────────
    if body.query is not None:
        if not result.success:
            return {
                "url": body.url,
                "success": False,
                "error": result.error or "Fetch failed",
            }

        # The normal fetch truncates large pages to a ToC placeholder.
        # For search we need the full content — read it from the on-disk
        # cache where it was stored during the original fetch.
        markdown = result.markdown
        if markdown == " ... ":
            cached = _read_cache_markdown(body.url)
            if cached is None:
                return {
                    "url": body.url,
                    "success": False,
                    "error": "Page was truncated but no cached full content found",
                }
            markdown = cached

        chunked = _parse_chunked(markdown)
        nodes = _flatten_chunks(chunked, include_headers=True)
        searcher = HybridSearcher()
        searcher.build(nodes, vector_weight=body.query_vector_weight)
        page_results, total = searcher.search(
            body.query, top_k=5, page=body.query_page,
        )

        import math
        total_pages = max(1, math.ceil(total / 5))
        return {
            "url": body.url,
            "success": True,
            "query": body.query,
            "query_page": body.query_page,
            "query_total_pages": total_pages,
            "query_num_chunks": len(nodes),
            "results": page_results,
        }

    # ── Normal mode (unchanged) ────────────────────────────────────────
    # Build a plain dict from the FetchResult attributes.  FetchResult is
    # a plain class (not a dataclass), so we construct the dict manually
    # rather than using ``dataclasses.asdict()``.
    response: dict = {
        "url": result.url,
        "markdown": result.markdown,
        "success": result.success,
        "status_code": result.status_code,
        "error": result.error,
        "navigation": result.navigation,
        "toc": result.toc,
        "chunked": result.chunked,
        "info": result.info,
        "total_chars": result.total_chars,
    }
    return {k: v for k, v in response.items() if v is not None}


@router.post("/websearch")
async def websearch(body: WebsearchBody):
    """Search the web or code via the Exa Search API.

    All parameters mirror the ``web_search()`` public API.  Requires
    ``EXA_API_KEY`` in the server environment (loaded from ``.aivocode.env``).
    """
    result = await web_search(
        body.query,
        type=body.type,
        num_results=body.num_results,
        highlights=body.highlights,
        text=body.text,
        include_domains=body.include_domains,
        exclude_domains=body.exclude_domains,
    )
    # Convert ResultItems to plain dicts.  ResultItem is a plain class
    # (not a dataclass), so we convert each item manually.
    return {
        "query": result.query,
        "results": [
            {
                "title": item.title,
                "url": item.url,
                "published_date": item.published_date,
                "author": item.author,
                "highlights": item.highlights,
                "text": item.text,
            }
            for item in result.results
        ],
        "cost_dollars": result.cost_dollars,
        "search_time": result.search_time,
        "success": result.success,
        "error": result.error,
    }
