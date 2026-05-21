"""Stealth web page fetching library — CloakBrowser + Crawl4AI.

What this module provides
- FetchResult: dataclass holding markdown, success flag, HTTP status, error details,
  and optional structured links.
- fetch_url(): async function that launches a stealth browser via CloakBrowser,
  connects Crawl4AI via CDP, fetches a URL, and returns structured results.
  Includes automatic retry for transient failures and configurable output format
  (raw markdown vs fit markdown with boilerplate removed).

Why this exists
- Single reusable entry point for web fetching — used by CLI, Python agents, and
  future transport layers (FastAPI, MCP) without modification.
- Separation of concerns: this module handles browser lifecycle, fetching,
  library log suppression, retry logic, and content format; callers own I/O.

How to use
- Importable API::

    from web_ops import fetch_url, FetchResult

    # Fit markdown (default) — main content with boilerplate stripped.
    result = await fetch_url("https://example.com")
    print(result.markdown)

    # Raw markdown — full page converted to markdown, links included inline.
    result = await fetch_url("https://example.com", output_format="raw")

See Also
- web_ops.tst_web_fetch for the reference implementation this was extracted from.
"""

from __future__ import annotations

import asyncio
import io
import re
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Literal

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from cloakbrowser import launch_async

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# Allowed values for wait_until, mapped to Playwright navigation events.
_WAIT_UNTIL_CHOICES: tuple[str, ...] = ("domcontentloaded", "load", "networkidle")
_WaitUntil = Literal["domcontentloaded", "load", "networkidle"]

# Allowed values for the output format parameter.
_OUTPUT_FORMAT_CHOICES: tuple[str, ...] = ("fit", "raw")
_OutputFormat = Literal["fit", "raw"]


@dataclass
class FetchResult:
    """Result of a ``fetch_url()`` call.

    Fields:
        markdown: Page body as markdown.  Always safe to use — empty string on
            failure.  For ``"fit"`` format this is the main content with
            boilerplate removed (nav, ads, sidebars stripped).  For ``"raw"``
            format this is the full page converted to markdown.
        success: ``True`` if the crawl completed and content was extracted.
        status_code: HTTP status from the final response.  ``None`` if the
            fetch never reached a server (timeout, DNS failure, CDP error).
        error: Human-readable error label.  ``None`` on success.  Common values:
            ``"Timeout waiting for page to load"``, ``"DNS resolution failed"``,
            ``"Connection refused"``, ``"empty"``.
        links: Structured link data (internal/external) populated only when
            ``output_format="fit"``, since raw markdown already contains links
            inline.  ``None`` otherwise.
    """

    markdown: str = ""
    success: bool = False
    status_code: int | None = None
    error: str | None = field(default=None, compare=False)
    links: dict[str, list[dict[str, Any]]] | None = None
    # compare=False for error because it's diagnostic, not identity.


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default CDP port used to bridge CloakBrowser and Crawl4AI.
_CDP_PORT: int = 9243

# Time limit (ms) for each individual page load attempt.
_PAGE_TIMEOUT_MS: int = 10_000

# Extra delay (seconds) after wait conditions are satisfied before capturing.
_DELAY_BEFORE_RETURN_HTML_S: float = 2.0

_DEFAULT_WAIT_UNTIL: _WaitUntil = "networkidle"

# Default output format: "fit" strips boilerplate for cleaner agent input.
_DEFAULT_OUTPUT_FORMAT: _OutputFormat = "fit"

# Pruning threshold (0–1). Higher = more aggressive removal.
# 0.48 is the Crawl4AI default — empirically good for most pages.
_PRUNING_THRESHOLD: float = 0.28

# Maximum retry attempts for transient failures.
_MAX_RETRIES: int = 2

# Delay between retry attempts (seconds).
_RETRY_DELAY_S: float = 0.5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_error(buf_text: str) -> str:
    """Extract a concise error message from verbose Crawl4AI / browser output.

    Args:
        buf_text: The captured output from a single fetch attempt.

    Returns:
        A short error label, or ``"Crawl failed"`` if no known pattern matches.
    """
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
        match = re.search(r"net::(ERR_\w+)", buf_text)
        if match:
            return f"Network error ({match.group(1)})"
    if "Timeout" in buf_text and "ms exceeded" in buf_text:
        return "Timeout waiting for page to load"
    return "Crawl failed"


def _is_transient_failure(result: FetchResult) -> bool:
    """Return ``True`` if the failure looks transient and worth retrying."""
    if result.status_code is None:
        return True
    if result.status_code >= 500:
        return True
    return False


async def _fetch_once(
    url: str,
    wait_until: _WaitUntil,
    output_format: _OutputFormat,
) -> FetchResult:
    """Perform a single fetch attempt, suppressing library output.

    Lifecycle
      1. Launch CloakBrowser with CDP remote debugging enabled.
      2. Redirect stdout/stderr to a buffer so library diagnostic output does
         not leak into the agent's markdown stream.
      3. Connect Crawl4AI to the CDP endpoint, run, and capture the result.
      4. Close the browser (always, even on failure).
      5. On failure, parse the captured buffer for a concise error label.

    Args:
        url: The fully-qualified URL to fetch.
        wait_until: Playwright navigation event to wait for.
        output_format: ``"fit"`` for main-content-only markdown with structured
            link data; ``"raw"`` for full-page markdown (no link extraction).

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
        buf = io.StringIO()

        with redirect_stdout(buf), redirect_stderr(buf):
            browser_config = BrowserConfig(
                browser_mode="cdp",
                cdp_url=f"http://127.0.0.1:{_CDP_PORT}",
            )

            # Build the run config based on output format.
            if output_format == "fit":
                run_config = CrawlerRunConfig(
                    wait_until=wait_until,
                    page_timeout=_PAGE_TIMEOUT_MS,
                    delay_before_return_html=_DELAY_BEFORE_RETURN_HTML_S,
                    markdown_generator=DefaultMarkdownGenerator(
                        content_filter=PruningContentFilter(
                            threshold=_PRUNING_THRESHOLD,
                        ),
                    ),
                )
            else:
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

        # Extract markdown — priority depends on format.
        if output_format == "fit":
            # Try fit_markdown first, fall back to raw_markdown if filter
            # produces nothing, fall back to the top-level markdown string.
            md_obj = result.markdown
            if hasattr(md_obj, "fit_markdown") and md_obj.fit_markdown:
                markdown = md_obj.fit_markdown
            elif hasattr(md_obj, "raw_markdown") and md_obj.raw_markdown:
                markdown = md_obj.raw_markdown
            else:
                markdown = str(md_obj) if md_obj else ""
        else:
            # Raw: use the top-level markdown string or raw_markdown.
            md_obj = result.markdown
            if hasattr(md_obj, "raw_markdown") and md_obj.raw_markdown:
                markdown = md_obj.raw_markdown
            else:
                markdown = str(md_obj) if md_obj else ""

        if not markdown:
            return FetchResult(
                success=True,
                status_code=result.status_code,
                markdown="",
                error="empty",
            )

        # Extract structured links for fit mode (raw already has them inline).
        # Keep only href and text — the other Crawl4AI fields (base_domain,
        # scores, head_data) are noise for agent consumption.
        links: dict[str, list[dict[str, Any]]] | None = None
        if output_format == "fit" and result.links:
            links = {
                "internal": [
                    {"href": link["href"], "text": link["text"]}
                    for link in result.links.get("internal", [])
                ],
                "external": [
                    {"href": link["href"], "text": link["text"]}
                    for link in result.links.get("external", [])
                ],
            }

        return FetchResult(
            success=True,
            status_code=result.status_code,
            markdown=markdown,
            links=links,
        )

    finally:
        await browser.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_url(
    url: str,
    *,
    wait_until: _WaitUntil = _DEFAULT_WAIT_UNTIL,
    output_format: _OutputFormat = _DEFAULT_OUTPUT_FORMAT,
) -> FetchResult:
    """Fetch a URL via CloakBrowser + Crawl4AI and return structured results.

    Automatically retries once (2 total attempts) for transient failures such
    as timeouts and network errors.  Deterministic failures (4xx HTTP responses)
    are returned immediately without retrying.

    Lifecycle
      1. Attempt the fetch via ``_fetch_once()``.
      2. If it fails with a transient error, wait briefly and retry once.
      3. Return the best available result.

    Args:
        url: The fully-qualified URL to fetch (e.g. ``https://example.com``).
        wait_until: Playwright navigation event to wait for before capturing HTML.
            - ``"networkidle"`` (default): no network activity for 500 ms.
            - ``"load"``: page load event fired (JS has run, resources loaded).
            - ``"domcontentloaded"``: DOM ready, JS may not have executed yet.
        output_format: Desired output format.
            - ``"fit"`` (default): main content with boilerplate stripped (nav,
              ads, sidebars removed). Includes structured ``.links`` field.
            - ``"raw"``: full page HTML converted to markdown. Links are
              included inline in the markdown; ``.links`` is ``None``.

    Returns:
        ``FetchResult`` with ``.markdown``, ``.success``, ``.status_code``,
        ``.error``, and optionally ``.links`` populated.  On failure,
        ``.success`` is ``False`` and ``.markdown`` is ``""`` — the caller
        never receives ``None``.

    Raises:
        Only unrecoverable programming errors — e.g. CloakBrowser binary not
        found, broken CDP handshake.  Runtime failures (HTTP errors, timeouts,
        empty responses) are returned as ``FetchResult(success=False)``.

    Side effects:
        Launches and tears down a CloakBrowser subprocess per attempt.
    """
    last_result = FetchResult(success=False, error="No attempts made")

    for attempt in range(1, _MAX_RETRIES + 1):
        last_result = await _fetch_once(url, wait_until, output_format)

        if last_result.success:
            return last_result

        if not _is_transient_failure(last_result):
            break

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    return last_result
