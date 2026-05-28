"""Exa web search module — neural search via the Exa Search API.

What this module provides
- ``SearchResult``: dataclass holding query, results, cost, success flag, and error.
- ``ResultItem``: dataclass holding a single search result (title, url, highlights,
  text, published_date, author).
- ``web_search()``: async function — neural search via the Exa API.  Defaults to
  ``type="auto"`` and ``highlights=True``.  For code searches, pass
  code-focused queries (e.g. "python asyncio gather error handling").
  Web and code share the same ``POST /search`` endpoint — no category
  parameter needed.
- ``result_to_output_json()``: serialize any ``SearchResult`` to the standard
  agent-facing JSON format.

Why this exists
- Single entry point for Exa-powered search — used by CLI, coding agents, and
  future transport layers without modification.
- Same endpoint serves both web and code queries: just vary ``type`` and
  query style.  No separate function needed.
- Uses the Exa Python SDK (``exa_py``), which reads ``EXA_API_KEY`` from the
  environment automatically.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from exa_py import Exa
from exa_py.api import SearchResponse as _ExaSearchResponse


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_SEARCH_TYPE_CHOICES: tuple[str, ...] = (
    "auto",
    "fast",
    "instant",
    "deep-lite",
    "deep",
    "deep-reasoning",
)
_SearchType = str  # One of the above literals — kept as str for simplicity.


@dataclass
class ResultItem:
    """A single search result from an Exa query.

    Fields:
        title: Page title.  Empty string if unavailable.
        url: Canonical URL of the result.
        published_date: ISO-format publication date, if available. ``None``
            when the source does not carry date metadata.
        author: Page author, if available. ``None`` for most web pages.
        highlights: Query-relevant excerpts from the page content.  Returned
            only when ``highlights=True`` is passed to the search call.
            ``None`` when highlights were not requested.
        text: Full page text (markdown) when requested via ``text`` in the
            contents options.  ``None`` when text extraction was not requested.
    """

    title: str = ""
    url: str = ""
    published_date: str | None = None
    author: str | None = None
    highlights: list[str] | None = None
    text: str | None = None

    @classmethod
    def from_exa_result(cls, exa_item: Any) -> ResultItem:
        """Build a ``ResultItem`` from an ``exa_py`` result object."""
        return cls(
            title=exa_item.title or "",
            url=exa_item.url or "",
            published_date=exa_item.published_date or None,
            author=exa_item.author or None,
            highlights=list(exa_item.highlights) if exa_item.highlights else None,
            text=exa_item.text or None,
        )


@dataclass
class SearchResult:
    """Result of a ``web_search()`` call.

    Fields:
        query: The search query that produced these results.
        results: Ordered list of ``ResultItem`` objects (best match first).
            Empty list when the search returned no results or failed.
        cost_dollars: Total cost in USD for this search call.  Typically
            fractions of a cent.  ``0.0`` when the call failed before reaching
            the API.
        search_time: Time in seconds the search took on the Exa side.
            ``None`` when unavailable or the call failed.
        success: ``True`` if the API returned results (including empty results).
            ``False`` when an error occurred before any results were obtained.
        error: Human-readable error description.  ``None`` on success.
            Set to a non-``None`` string only when ``success`` is ``False``.
    """

    query: str = ""
    results: list[ResultItem] = field(default_factory=list)
    cost_dollars: float = 0.0
    search_time: float | None = None
    success: bool = False
    error: str | None = field(default=None, compare=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _get_client(api_key: str | None = None) -> Exa:
    """Create an Exa client, reading the API key from env or parameter.

    The Exa SDK automatically reads ``EXA_API_KEY`` from the environment
    when no key is passed.  We additionally check ``os.environ`` ourselves
    to produce a clear error before the SDK raises.
    """
    key = api_key or os.environ.get("EXA_API_KEY")
    if not key:
        raise ValueError(
            "No Exa API key found. Set the EXA_API_KEY environment variable."
        )
    return Exa(api_key=key)


def _build_contents(
    highlights: bool = True,
    text: bool | dict[str, Any] = False,
    summary: bool | dict[str, Any] = False,
) -> dict[str, Any] | None:
    """Build the ``contents`` dict for an Exa search call.

    On the /search endpoint, text/highlights/summary must be nested under
    a ``contents`` key.  Returns ``None`` when no content is requested.
    """
    opts: dict[str, Any] = {}
    if highlights:
        opts["highlights"] = highlights
    if text:
        opts["text"] = text
    if summary:
        opts["summary"] = summary
    return opts if opts else None


async def web_search(
    query: str,
    *,
    api_key: str | None = None,
    type: str = "auto",
    num_results: int = 10,
    highlights: bool = True,
    text: bool | dict[str, Any] = False,
    summary: bool | dict[str, Any] = False,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
    category: str | None = None,
    livecrawl: str | None = None,  # deprecated, but kept for compat
) -> SearchResult:
    """Perform a general web search via Exa.

    Defaults to ``type="auto"`` with ``highlights=True`` for token-efficient
    excerpts.

    Args:
        query: Search query.  Use natural language; be specific for best
            results (e.g. "latest AI regulation updates in the EU").
        api_key: Exa API key.  If ``None``, reads ``EXA_API_KEY`` from
            the environment.
        type: Search type.  One of ``"auto"``, ``"fast"``, ``"instant"``,
            ``"deep-lite"``, ``"deep"``, ``"deep-reasoning"``.
            Default ``"auto"``.
        num_results: Number of results to return (1–100).  Default 10.
        highlights: If ``True``, return query-relevant highlights for each
            result.  Default ``True``.
        text: If ``True`` or a dict with ``maxCharacters``, return full page
            text.  Default ``False``.
        summary: If ``True`` or a dict with ``query``, return an LLM-generated
            summary per result.  Default ``False``.
        include_domains: Restrict results to these domains.
        exclude_domains: Exclude results from these domains.
        start_published_date: ISO 8601 date string — only return results
            published on or after this date.
        end_published_date: ISO 8601 date string — only return results
            published on or before this date.
        category: Vertical category filter.  One of ``"company"``, ``"people"``,
            ``"research paper"``, ``"news"``, ``"personal site"``,
            ``"financial report"``.
        livecrawl: Deprecated.  Use ``contents.maxAgeHours`` instead.

    Returns:
        ``SearchResult`` with query, results, cost, and success flag.
        Never raises — errors are captured in ``SearchResult.error``.

    Example::

        result = await web_search("Paris population 2025")
        for item in result.results:
            print(item.title, item.url)
    """
    try:
        client = _get_client(api_key)
    except ValueError as exc:
        return SearchResult(query=query, success=False, error=str(exc))

    contents = _build_contents(highlights=highlights, text=text, summary=summary)

    # Build kwargs for exa.search(), filtering out None values that would
    # conflict with the SDK's defaults.
    kwargs: dict[str, Any] = {
        "num_results": num_results,
        "type": type,
    }
    if contents:
        kwargs["contents"] = contents
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
    if start_published_date:
        kwargs["start_published_date"] = start_published_date
    if end_published_date:
        kwargs["end_published_date"] = end_published_date
    if category:
        kwargs["category"] = category

    try:
        response: _ExaSearchResponse = client.search(query, **kwargs)
    except Exception as exc:
        return SearchResult(
            query=query,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
        )

    # Extract cost — cost_dollars may be None on error responses.
    cost = 0.0
    if response.cost_dollars is not None:
        cost = response.cost_dollars.total

    return SearchResult(
        query=query,
        results=[ResultItem.from_exa_result(r) for r in response.results],
        cost_dollars=cost,
        search_time=response.search_time if response.search_time else None,
        success=True,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _serialize_item(item: ResultItem) -> dict[str, Any]:
    """Convert a single ``ResultItem`` to a JSON-safe dict, omitting
    ``None``-valued keys to reduce output size."""
    d: dict[str, Any] = {"title": item.title, "url": item.url}
    if item.published_date is not None:
        d["published_date"] = item.published_date
    if item.author is not None:
        d["author"] = item.author
    if item.highlights is not None:
        d["highlights"] = item.highlights
    if item.text is not None:
        d["text"] = item.text
    return d


def result_to_output_json(result: SearchResult) -> str:
    """Serialize a ``SearchResult`` to a compact JSON string for agent consumers.

    Excludes ``None``-valued fields from both the top-level result and each
    ``ResultItem`` to minimize token usage.  Single‑line output (no indent).

    Args:
        result: The ``SearchResult`` to serialize.

    Returns:
        A JSON string suitable for printing or piping.

    Example::

        result = await web_search("latest AI news")
        print(result_to_output_json(result))
    """
    top: dict[str, Any] = {
        "query": result.query,
        "results": [_serialize_item(it) for it in result.results],
        "cost_dollars": result.cost_dollars,
        "success": result.success,
    }
    if result.search_time is not None:
        top["search_time"] = result.search_time
    if not result.success and result.error:
        top["error"] = result.error
    return json.dumps(top, ensure_ascii=False)
