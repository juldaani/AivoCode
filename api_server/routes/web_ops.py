"""Web operations route handlers — thin wrappers around the ``web_ops`` library.

Every route delegates directly to the corresponding public ``web_ops.*``
function.  No business logic lives here — this module has the same role
as ``cli/commands/webfetch.py`` before the HTTP refactor.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from web_ops import fetch_urls, web_search

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
    """
    result = await fetch_urls(
        body.url,
        wait_until=body.wait_until,  # type: ignore[arg-type]
        headings=body.headings,
        line_ranges=body.line_ranges,
        refresh_cache=body.refresh_cache,
        include_navigation=body.include_navigation,
    )
    # Build a plain dict from the FetchResult attributes.  FetchResult is
    # a plain class (not a dataclass), so we construct the dict manually
    # rather than using ``dataclasses.asdict()``.
    return {
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


@router.post("/websearch")
async def websearch(body: WebsearchBody):
    """Search the web or code via the Exa Search API.

    All parameters mirror the ``web_search()`` public API.  Requires
    ``EXA_API_KEY`` in the server environment (loaded from ``.env``).
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
