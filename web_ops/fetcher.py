"""Stealth web page fetching library — CloakBrowser + Crawl4AI.

What this module provides
- FetchResult: dataclass holding markdown, success flag, HTTP status, and error details.
- fetch_url(): async function that launches a stealth browser via CloakBrowser,
  connects Crawl4AI via CDP, fetches a URL, and returns structured results.
  Includes automatic retry for transient failures.

Why this exists
- Single reusable entry point for web fetching — used by CLI, Python agents, and
  future transport layers (FastAPI, MCP) without modification.
- Separation of concerns: this module handles browser lifecycle, fetching,
  library log suppression, and retry logic; callers own I/O (print, log, exit).

How to use
- Importable API::

    from web_ops import fetch_url, FetchResult

    result = await fetch_url("https://example.com")
    print(result.markdown)

See Also
- web_ops.tst_web_fetch for the reference implementation this was extracted from.
"""

from __future__ import annotations

import asyncio
import io
import re
from contextlib import redirect_stderr, redirect_stdout
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
            ``"Timeout waiting for page to load"``, ``"DNS resolution failed"``,
            ``"Connection refused"``, ``"empty"``.
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

# Time limit (ms) for each individual page load attempt.
# Kept moderate so that ``networkidle`` does not hang forever on sites with
# long-polling / WebSocket connections.  On timeout the function retries once
# automatically, so a transient spike does not cause a permanent failure.
_PAGE_TIMEOUT_MS: int = 10_000

# Extra delay (seconds) after ``wait_until`` and ``wait_for`` conditions are
# satisfied, before capturing the final HTML.  Gives time for late-rendering
# widgets and hydration to complete.
_DELAY_BEFORE_RETURN_HTML_S: float = 2.0

_DEFAULT_WAIT_UNTIL: _WaitUntil = "networkidle"

# Maximum number of fetch attempts for transient failures.
# Failures that look deterministic (4xx HTTP responses) are not retried.
_MAX_RETRIES: int = 2

# Delay between retry attempts, in seconds.
_RETRY_DELAY_S: float = 0.5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_error(buf_text: str) -> str:
    """Extract a concise error message from verbose Crawl4AI / browser output.

    Crawl4AI and CloakBrowser emit multi-line diagnostic output (stack traces,
    code context, ANTIBOT fallback logs) directly to stdout/stderr.  This
    function scans that output for well-known error patterns and returns a
    single short label suitable for ``FetchResult.error``.

    Args:
        buf_text: The captured output from a single fetch attempt.

    Returns:
        A short error label, or ``"Crawl failed"`` if no known pattern matches.
    """
    # Ordered from most specific → least specific.
    if "ERR_NAME_NOT_RESOLVED" in buf_text:
        return "DNS resolution failed"
    if "ERR_CONNECTION_REFUSED" in buf_text:
        return "Connection refused"
    if "ERR_CONNECTION_TIMED_OUT" in buf_text:
        return "Connection timed out"
    if "ERR_CONNECTION_CLOSED" in buf_text:
        return "Connection closed"
    if "ERR_CONNECTION_RESET" in buf_text:
        return "Connection reset"
    if "net::ERR_" in buf_text:
        # Catch-all for other Chrome network errors.
        match = re.search(r"net::(ERR_\w+)", buf_text)
        if match:
            return f"Network error ({match.group(1)})"

    if "Timeout" in buf_text and "ms exceeded" in buf_text:
        return "Timeout waiting for page to load"

    return "Crawl failed"


def _is_transient_failure(result: FetchResult) -> bool:
    """Return ``True`` if the failure looks transient and worth retrying.

    Transient failures: timeouts, network errors, server errors (5xx).
    Deterministic failures: client errors (4xx) — retrying won't help.
    """
    if result.status_code is None:
        # Never reached the server — likely timeout or network issue.
        return True
    if result.status_code >= 500:
        # Server error — may recover.
        return True
    # 4xx or other status — the server explicitly rejected the request.
    return False


async def _fetch_once(
    url: str,
    wait_until: _WaitUntil,
) -> FetchResult:
    """Perform a single fetch attempt, suppressing library output.

    Lifecycle
      1. Launch CloakBrowser with CDP remote debugging enabled.
      2. Redirect stdout/stderr to a buffer so Crawl4AI/CloakBrowser diagnostic
         output does not leak into the agent's markdown stream.
      3. Connect Crawl4AI to the CDP endpoint, run, and capture the result.
      4. Close the browser (always, even on failure).
      5. On failure, parse the captured buffer for a concise error label.

    Args:
        url: The fully-qualified URL to fetch.
        wait_until: Playwright navigation event to wait for.

    Returns:
        ``FetchResult`` — never ``None``.
    """
    browser = await launch_async(
        headless=True,
        args=[
            f"--remote-debugging-port={_CDP_PORT}",
            "--remote-debugging-address=127.0.0.1",
        ],
    )

    try:
        # Capture all library output so it does not leak into the agent's
        # stdout / stderr.  On success we discard it; on failure we parse it
        # for a concise error label.
        buf = io.StringIO()

        with redirect_stdout(buf), redirect_stderr(buf):
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

        # --- translate Crawl4AI result → FetchResult -----------------------

        if result is None:
            return FetchResult(
                success=False,
                error=_parse_error(buf.getvalue()) or "Crawler returned no result",
            )

        if not result.success:
            return FetchResult(
                success=False,
                status_code=result.status_code,
                error=_parse_error(buf.getvalue()),
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_url(
    url: str,
    *,
    wait_until: _WaitUntil = _DEFAULT_WAIT_UNTIL,
) -> FetchResult:
    """Fetch a URL via CloakBrowser + Crawl4AI and return structured results.

    Automatically retries once (2 total attempts) for transient failures such
    as timeouts and network errors.  Deterministic failures (4xx HTTP responses)
    are returned immediately without retrying.

    Lifecycle
      1. Attempt the fetch via ``_fetch_once()``.
      2. If it fails with a transient error, wait briefly and retry once.
      3. Return the best available result (success if any attempt succeeded,
         otherwise the last failure).

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
        Launches and tears down a CloakBrowser subprocess per attempt.
    """
    last_result = FetchResult(success=False, error="No attempts made")

    for attempt in range(1, _MAX_RETRIES + 1):
        last_result = await _fetch_once(url, wait_until)

        if last_result.success:
            return last_result

        # Do not retry deterministic failures (4xx).
        if not _is_transient_failure(last_result):
            break

        # Brief pause before retrying to let transient conditions settle
        # (e.g. DNS propagation, server restart, CDP port release).
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    return last_result
