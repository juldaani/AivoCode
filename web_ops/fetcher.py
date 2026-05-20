"""Stealth web page fetching library — CloakBrowser + Crawl4AI.

What this module provides
- FetchResult: dataclass holding markdown, success flag, HTTP status, and error details.
- fetch_url(): async function that launches a stealth browser via CloakBrowser,
  connects Crawl4AI via CDP, fetches a URL, and returns structured results.

Why this exists
- Single reusable entry point for web fetching — used by CLI, Python agents, and
  future transport layers (FastAPI, MCP) without modification.
- Separation of concerns: this module handles browser lifecycle and fetching only;
  callers own I/O (print, log, exit).

How to use
- Importable API::

    from web_ops import fetch_url, FetchResult

    result = await fetch_url("https://example.com")
    print(result.markdown)

See Also
- web_ops.tst_web_fetch for the reference implementation this was extracted from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from cloakbrowser import launch_async

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# Allowed values for wait_until, mapped to Playwright navigation events.
_WAIT_UNTIL_CHOICES: tuple[str, ...] = ("domcontentloaded", "load", "networkidle")
_WaitUntil = Literal["domcontentloaded", "load", "networkidle"]


@dataclass
class FetchResult:
    """Result of a ``fetch_url()`` call.

    Fields:
        markdown: Page body converted to markdown.  Always safe to use — empty
            string on failure.
        success: ``True`` if the crawl completed and content was extracted.
        status_code: HTTP status from the final response.  ``None`` if the
            fetch never reached a server (timeout, DNS failure, CDP error).
        error: Human-readable error label.  ``None`` on success.  Common values:
            ``"timeout"``, ``"empty"``, or upstream Crawl4AI error strings.
    """

    markdown: str = ""
    success: bool = False
    status_code: int | None = None
    error: str | None = field(default=None, compare=False)
    # compare=False because error is diagnostic, not identity.


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default CDP port used to bridge CloakBrowser and Crawl4AI.
# Must match between the browser launch args and the BrowserConfig cdp_url.
_CDP_PORT: int = 9243

# Time limit (ms) for the entire page load.  Kept moderate so that ``networkidle``
# does not hang forever on sites with long-polling / WebSocket connections that
# keep network activity alive indefinitely.  Increase if targeting very slow SPAs.
_PAGE_TIMEOUT_MS: int = 10_000

# Extra delay (seconds) after ``wait_until`` and ``wait_for`` conditions are
# satisfied, before capturing the final HTML.  Gives time for late-rendering
# widgets and hydration to complete.
_DELAY_BEFORE_RETURN_HTML_S: float = 2.0

_DEFAULT_WAIT_UNTIL: _WaitUntil = "networkidle"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_url(
    url: str,
    *,
    wait_until: _WaitUntil = _DEFAULT_WAIT_UNTIL,
) -> FetchResult:
    """Fetch a URL via CloakBrowser + Crawl4AI and return structured results.

    Lifecycle
      1. Launch CloakBrowser with CDP remote debugging enabled.
      2. Connect Crawl4AI's ``AsyncWebCrawler`` to the CDP endpoint.
      3. Call ``arun()`` — wait for the requested navigation event plus the
         post-render buffer delay, then capture and convert the page to
         markdown.
      4. Close the browser (always, even on failure).

    Args:
        url: The fully-qualified URL to fetch (e.g. ``https://example.com``).
        wait_until: Playwright navigation event to wait for before capturing HTML.
            - ``"networkidle"`` (default): no network activity for 500 ms.
            - ``"load"``: page load event fired (JS has run, resources loaded).
            - ``"domcontentloaded"``: DOM ready, JS may not have executed yet.

    Returns:
        ``FetchResult`` with ``.markdown``, ``.success``, ``.status_code``,
        and ``.error`` populated.  On failure, ``.success`` is ``False`` and
        ``.markdown`` is ``""`` — the caller never receives ``None``.

    Raises:
        Only unrecoverable programming errors — e.g. CloakBrowser binary not
        found, broken CDP handshake.  Runtime failures (HTTP errors, timeouts,
        empty responses) are returned as ``FetchResult(success=False)``.

    Side effects:
        Launches and tears down a CloakBrowser subprocess per call.
    """
    # Step 1: launch stealth browser with remote debugging (CDP).
    browser = await launch_async(
        headless=True,
        args=[
            f"--remote-debugging-port={_CDP_PORT}",
            "--remote-debugging-address=127.0.0.1",
        ],
    )

    try:
        # Step 2: connect Crawl4AI to the stealth browser via CDP and run.
        browser_config = BrowserConfig(
            browser_mode="cdp",
            cdp_url=f"http://127.0.0.1:{_CDP_PORT}",
        )
        run_config = CrawlerRunConfig(
            wait_until=wait_until,
            page_timeout=_PAGE_TIMEOUT_MS,
            delay_before_return_html=_DELAY_BEFORE_RETURN_HTML_S,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url, config=run_config)

            if result is None:
                return FetchResult(
                    success=False,
                    error="Crawler returned no result",
                )

            if not result.success:
                return FetchResult(
                    success=False,
                    status_code=result.status_code,
                    error="Crawl failed",
                )

            markdown = result.markdown or ""
            if not markdown:
                return FetchResult(
                    success=True,
                    status_code=result.status_code,
                    markdown="",
                    error="empty",
                )

            return FetchResult(
                success=True,
                status_code=result.status_code,
                markdown=markdown,
            )

    finally:
        # Always close the browser, even if crawling or CDP handshake fails.
        # Exceptions during close are swallowed — the original error (if any)
        # should propagate, not a secondary cleanup failure.
        await browser.close()
