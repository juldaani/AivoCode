"""Stealth web page fetching library — CloakBrowser + Crawl4AI.

What this module provides
- FetchResult: dataclass holding markdown, success flag, HTTP status, error,
  structured links, ToC entries, and truncation metadata.
- fetch_url(): async function that fetches a URL via CloakBrowser + Crawl4AI
  with caching, truncation, ToC generation, and section extraction.

Why this exists
- Single entry point for web fetching — used by CLI, Python agents, and
  future transport layers without modification.
- Content-aware: large pages (> 5000 chars) are automatically truncated to a
  table of contents with section previews, preventing agents from pulling
  huge pages into context.  Full content is cached on disk for section-level
  retrieval on demand.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from cloakbrowser import launch_async

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_WAIT_UNTIL_CHOICES: tuple[str, ...] = ("domcontentloaded", "load", "networkidle")
_WaitUntil = Literal["domcontentloaded", "load", "networkidle"]

_OUTPUT_FORMAT_CHOICES: tuple[str, ...] = ("fit", "raw")
_OutputFormat = Literal["fit", "raw"]


@dataclass
class FetchResult:
    """Result of a ``fetch_url()`` call.

    Fields:
        markdown: Page body as markdown.  When content exceeds the truncation
            threshold, this contains a human-readable message explaining that
            the full content was saved and a table of contents follows.
            On failure, empty string.
        success: ``True`` if the crawl completed and content was extracted.
        status_code: HTTP status.  ``None`` if the server was never reached.
        error: Error label.  ``None`` on success.
        navigation: Structured navigation links (internal/external).  Populated
            only when ``include_navigation=True`` is passed to ``fetch_url()``.
            ``None`` otherwise.
        toc: Table of contents entries when content is truncated.  ``None``
            when content fits under the threshold or a specific section was
            requested via ``heading`` / ``index`` / ``line_range``.
        total_chars: Total character count of the full original content.
            ``0`` on failure or when a section was extracted.
    """

    markdown: str = ""
    success: bool = False
    status_code: int | None = None
    error: str | None = field(default=None, compare=False)
    navigation: dict[str, list[dict[str, Any]]] | None = None
    toc: list[dict[str, Any]] | None = None
    total_chars: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CDP_PORT: int = 9243
_PAGE_TIMEOUT_MS: int = 10_000
# Extra delay (seconds) after wait conditions are satisfied before capturing.
# Kept at zero because ``load`` already guarantees scripts are executed;
# frameworks that fetch data after hydration (SPAs with API calls) should
# use ``--js-render`` (networkidle) instead.
_DELAY_BEFORE_RETURN_HTML_S: float = 0.0
_DEFAULT_WAIT_UNTIL: _WaitUntil = "load"
_DEFAULT_OUTPUT_FORMAT: _OutputFormat = "fit"
_PRUNING_THRESHOLD: float = 0.35
# Character threshold above which content is truncated and replaced with a
# table of contents.  Full content is always saved to cache for later retrieval.
_TRUNCATION_THRESHOLD: int = 5_000

# Directory where fetched page content is cached on disk.
# Relative to the workspace root.
_CACHE_DIR: Path = Path("tmp/aivocode/cache")

# Cache TTL in seconds.  After this period the cache is considered stale and
# a fresh fetch is triggered automatically.  News sites update frequently;
# 15 min balances freshness against repeated browser launches.
_CACHE_TTL_S: float = 900

# Maximum number of cached files.  When exceeded, the oldest files (by
# modification time) are evicted to keep the cache within bounds.
_CACHE_MAX_FILES: int = 200

# Maximum number of lines that can be returned via ``line_range`` requests.
# Prevents agents from pulling the entire page through range queries.
_LINE_RANGE_MAX: int = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_error(buf_text: str) -> str:
    """Extract a concise error message from verbose Crawl4AI output."""
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


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_key(url: str) -> str:
    """Derive a short, stable filename from a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16] + ".md"


def _cache_path(url: str) -> Path:
    return _CACHE_DIR / _cache_key(url)


def _cache_is_fresh(path: Path) -> bool:
    """Return True if the cache file exists and is within the TTL."""
    if not path.exists():
        return False
    age = time.time() - os.path.getmtime(str(path))
    return age < _CACHE_TTL_S


def _read_cache(url: str) -> str | None:
    """Read cached content, or None if not available."""
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _write_cache(url: str, content: str) -> None:
    """Write content to the cache directory and evict old entries if needed."""
    path = _cache_path(url)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _evict_if_needed()


def _evict_if_needed() -> None:
    """Remove oldest cache files if count exceeds ``_CACHE_MAX_FILES``.

    Files are sorted by modification time (oldest first) and surplus entries
    are deleted.  This runs after every cache write so the limit is a hard cap.
    """
    try:
        files = sorted(
            _CACHE_DIR.glob("*.md"),
            key=lambda p: os.path.getmtime(str(p)),
        )
    except OSError:
        return  # Directory doesn't exist or isn't readable — ignore.

    if len(files) <= _CACHE_MAX_FILES:
        return

    for old_file in files[: len(files) - _CACHE_MAX_FILES]:
        try:
            old_file.unlink()
        except OSError:
            pass  # Best-effort — don't fail the fetch over cleanup.


# ---------------------------------------------------------------------------
# Table of Contents
# ---------------------------------------------------------------------------


def _build_toc(markdown: str) -> list[dict[str, Any]]:
    """Parse markdown into a table of contents with section previews.

    Scans for ``#``, ``##``, ``###`` headings.  Each ToC entry includes the
    heading text, nesting level, line range, and a short preview of the
    section body.  Content before the first heading gets a virtual
    ``[Overview]`` entry at level 0.

    Args:
        markdown: The full markdown content.

    Returns:
        List of ToC entries, each with ``idx``, ``heading``, ``level``,
        ``line_range`` (1-based), and ``preview``.
    """
    lines = markdown.splitlines()
    # Find all heading positions.
    headings: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,3})\s+(.+)", line)
        if m:
            headings.append({
                "level": len(m.group(1)),
                "heading": m.group(2).strip(),
                "line": i + 1,  # 1-based
            })

    if not headings:
        # No headings at all — treat the whole thing as one entry.
        return [{
            "idx": 0,
            "heading": "[Overview]",
            "level": 0,
            "line_range": [1, len(lines)],
            "preview": _preview_lines(lines, 0, len(lines)),
        }]

    toc: list[dict[str, Any]] = []

    # Before the first heading: [Overview].
    if headings[0]["line"] > 1:
        preview = _preview_lines(lines, 0, headings[0]["line"] - 1)
        if preview:
            toc.append({
                "idx": 0,
                "heading": "[Overview]",
                "level": 0,
                "line_range": [1, headings[0]["line"] - 1],
                "preview": preview,
            })

    # Sections between headings.
    for i, h in enumerate(headings):
        start = h["line"]
        end = headings[i + 1]["line"] - 1 if i + 1 < len(headings) else len(lines)
        preview = _preview_lines(lines, start, end + 1)
        toc.append({
            "idx": len(toc),
            "heading": h["heading"],
            "level": h["level"],
            "line_range": [start, end],
            "preview": preview,
        })

    return toc


def _preview_lines(lines: list[str], start: int, end: int) -> str:
    """Extract the first meaningful ~120 chars from a section of lines.

    Skips blank lines and heading lines (which start with #).
    Returns up to 120 characters of the first content line, or empty string
    if the section has no body text.
    """
    for i in range(start, min(end, len(lines))):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("!["):
            continue  # image
        if stripped.startswith("|"):
            continue  # table
        return stripped[:120]
    return ""


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------


def _extract_section(
    content: str,
    *,
    heading: str | None = None,
    index: int | None = None,
    line_range: str | None = None,
) -> tuple[str, str | None]:
    """Extract a section from cached content.

    Returns ``(markdown, error)`` — error is ``None`` on success.

    Args:
        content: Full cached markdown content.
        heading: Exact heading text to match (e.g. ``"Tuoreimmat"``).
        index: ToC index number to extract.
        line_range: ``"start-end"`` line range (1-based, max 100 lines).

    Raises:
        Never — errors are returned as the second tuple element.
    """
    if line_range is not None:
        return _extract_line_range(content, line_range)

    toc = _build_toc(content)

    if index is not None:
        if index < 0 or index >= len(toc):
            return "", f"Index {index} out of range (0-{len(toc) - 1})"
        return _extract_by_toc_entry(content, toc[index])

    if heading is not None:
        matches = [e for e in toc if e["heading"].lower() == heading.lower()]
        if not matches:
            return "", f"Heading '{heading}' not found in table of contents"
        # If multiple headings with same text exist, return the first.
        # Caller can use --index for disambiguation.
        return _extract_by_toc_entry(content, matches[0])

    return "", "No section selector provided"


def _extract_line_range(content: str, line_range: str) -> tuple[str, str | None]:
    """Extract lines from a 1-based range string like ``"10-30"``.

    If the requested range exceeds ``_LINE_RANGE_MAX``, the content is
    truncated and a note is appended to the markdown so the caller knows
    the result is incomplete.
    """
    try:
        parts = line_range.split("-")
        if len(parts) != 2:
            return "", f"Invalid line range format: '{line_range}' — use 'start-end'"
        start = int(parts[0])
        end = int(parts[1])
    except ValueError:
        return "", f"Invalid line range: '{line_range}'"

    lines = content.splitlines()
    if start < 1:
        start = 1
    if start > len(lines):
        return "", f"Line range start {start} exceeds file length ({len(lines)} lines)"

    requested_count = end - start + 1
    truncated = requested_count > _LINE_RANGE_MAX
    if truncated:
        end = start + _LINE_RANGE_MAX - 1

    end = min(end, len(lines))
    markdown = "\n".join(lines[start - 1:end])

    if truncated:
        note = (
            f"\n\n[Content truncated: requested {requested_count} lines "
            f"but limit is {_LINE_RANGE_MAX}. Showing first {_LINE_RANGE_MAX} lines.]"
        )
        markdown += note

    return markdown, None


def _extract_by_toc_entry(
    content: str,
    entry: dict[str, Any],
) -> tuple[str, str | None]:
    """Extract lines covered by a ToC entry."""
    ls, le = entry["line_range"]
    lines = content.splitlines()
    # Clamp to content bounds.
    ls = max(1, ls)
    le = min(len(lines), le)
    return "\n".join(lines[ls - 1:le]), None


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


async def _fetch_once(
    url: str,
    wait_until: _WaitUntil,
    output_format: _OutputFormat,
    include_navigation: bool = False,
) -> FetchResult:
    """Perform a single fetch attempt (no caching, no truncation logic)."""
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

        # Extract markdown.
        if output_format == "fit":
            md_obj = result.markdown
            if hasattr(md_obj, "fit_markdown") and md_obj.fit_markdown:
                markdown = md_obj.fit_markdown
            elif hasattr(md_obj, "raw_markdown") and md_obj.raw_markdown:
                markdown = md_obj.raw_markdown
            else:
                markdown = str(md_obj) if md_obj else ""
        else:
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

        # Extract structured navigation links when requested.
        navigation: dict[str, list[dict[str, Any]]] | None = None
        if include_navigation and output_format == "fit" and result.links:
            navigation = {
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
            navigation=navigation,
            total_chars=len(markdown),
        )

    finally:
        await browser.close()


def _truncation_message(total_chars: int) -> str:
    """Explain to the agent why content was truncated."""
    return (
        f"Content exceeds the {_TRUNCATION_THRESHOLD} character limit "
        f"({total_chars} chars total). Full content saved to cache. "
        f"Use --heading, --index, or --line-range to fetch specific sections. "
        f"Table of contents follows (see toc field)."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_url(
    url: str,
    *,
    wait_until: _WaitUntil = _DEFAULT_WAIT_UNTIL,
    output_format: _OutputFormat = _DEFAULT_OUTPUT_FORMAT,
    heading: str | None = None,
    index: int | None = None,
    line_range: str | None = None,
    refresh_cache: bool = False,
    include_navigation: bool = False,
) -> FetchResult:
    """Fetch a URL via CloakBrowser + Crawl4AI and return structured results.

    When content exceeds the truncation threshold (5000 chars), the full
    content is saved to a disk cache and the result includes a table of
    contents with section previews instead of the raw markdown.  Agents can
    then retrieve specific sections via ``heading``, ``index``, or
    ``line_range`` parameters — which read directly from cache.

    Args:
        url: The URL to fetch.
        wait_until: Playwright navigation event to wait for.
        output_format: ``"fit"`` (default) or ``"raw"``.
        heading: Exact heading text to extract from cache (case-insensitive).
        index: ToC index to extract from cache.
        line_range: ``"start-end"`` line range to extract from cache
            (1-based, max 100 lines).
        refresh_cache: If ``True``, always refetch from the web, ignoring any
            cached content.

    Returns:
        ``FetchResult`` — never ``None``.

    Side effects:
        Launches/takes down a CloakBrowser subprocess per fresh fetch.
        Writes/reads markdown files to ``tmp/aivocode/cache/``.
    """
    # ── Section extraction from cache (no fetch needed if fresh) ──────────
    wants_section = heading is not None or index is not None or line_range is not None

    if wants_section and not refresh_cache:
        cached = _read_cache(url)
        if cached is not None and _cache_is_fresh(_cache_path(url)):
            md, err = _extract_section(
                cached,
                heading=heading,
                index=index,
                line_range=line_range,
            )
            return FetchResult(
                success=err is None,
                markdown=md,
                error=err,
                total_chars=len(md),
            )
        # Cache missing or stale — fetch first, then extract from result.

    # ── Cache hit (no section requested, not refreshing) ─────────────────
    if not wants_section and not refresh_cache and _cache_is_fresh(_cache_path(url)):
        cached = _read_cache(url)
        if cached is not None:
            return _result_with_truncation(cached)

    # ── Fresh fetch ──────────────────────────────────────────────────────
    result = await _fetch_once(url, wait_until, output_format, include_navigation)
    if not result.success:
        return result

    # Persist to cache.
    full_markdown = result.markdown
    _write_cache(url, full_markdown)

    # If a section was requested, extract it from the fresh content.
    if wants_section:
        md, err = _extract_section(
            full_markdown,
            heading=heading,
            index=index,
            line_range=line_range,
        )
        return FetchResult(
            success=err is None,
            markdown=md,
            navigation=result.navigation,
            error=err,
            total_chars=len(md),
        )

    # Full result — apply truncation if needed.
    return _result_with_truncation(full_markdown, navigation=result.navigation)


def _result_with_truncation(
    markdown: str,
    navigation: dict[str, list[dict[str, Any]]] | None = None,
) -> FetchResult:
    """Build a FetchResult with optional truncation + ToC."""
    total_chars = len(markdown)
    if total_chars <= _TRUNCATION_THRESHOLD:
        return FetchResult(
            success=True,
            markdown=markdown,
            navigation=navigation,
            total_chars=total_chars,
        )
    # Truncate — replace markdown with explanatory message + ToC.
    toc = _build_toc(markdown)
    return FetchResult(
        success=True,
        markdown=_truncation_message(total_chars),
        navigation=navigation,
        toc=toc,
        total_chars=total_chars,
    )
