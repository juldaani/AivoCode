#!/usr/bin/env python3
"""Test script: fetch a URL and print its content as markdown.

Uses CloakBrowser for stealth browser launch (bot detection bypass) and
Crawl4AI for page fetching / markdown conversion.

Defaults to ``wait_until="networkidle"`` (SPA-safe) with a 15s page timeout
and 2s post-render buffer — works for both static sites and JS-heavy SPAs.

Usage (module invocation):
    python -m web-ops.tst_web_fetch https://example.com
    python -m web-ops.tst_web_fetch https://spa-site.com --wait-until load

Usage (script invocation):
    python web-ops/tst_web_fetch.py https://example.com

Dependencies:
    pip install crawl4ai cloakbrowser
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Literal, Sequence

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

# When executed as a script, Python sets sys.path[0] to the script's directory,
# which can break package imports. Add the repo root to support both invocation styles.
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from cloakbrowser import launch_async  # noqa: E402

# Default CDP port used to bridge CloakBrowser and Crawl4AI.
# Must match between the browser launch args and the BrowserConfig cdp_url.
_CDP_PORT = 9243

# Allowed values for the --wait-until CLI flag, mapped to Playwright navigation events.
_WAIT_UNTIL_CHOICES: tuple[str, ...] = ("domcontentloaded", "load", "networkidle")
_WaitUntil = Literal["domcontentloaded", "load", "networkidle"]

# Time limit for the entire page load. Kept short (15s) so that networkidle
# does not hang on sites with long-polling / WebSocket connections that
# keep network activity alive indefinitely. Increase if targeting very slow SPAs.
_PAGE_TIMEOUT_MS = 15_000

# Extra delay after wait_until and wait_for conditions are satisfied, before
# capturing the final HTML. Gives time for late-rendering widgets and hydration.
_DELAY_BEFORE_RETURN_HTML_S = 2.0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Returns a namespace with:
        url: the target URL to fetch.
        wait_until: Playwright navigation event to wait for before capturing.
    """
    parser = argparse.ArgumentParser(
        prog="web-ops.tst_web_fetch",
        description="Fetch a URL via CloakBrowser + Crawl4AI and print its markdown content.",
    )
    parser.add_argument(
        "url",
        type=str,
        help="The URL to fetch (e.g. https://example.com).",
    )
    parser.add_argument(
        "--wait-until",
        type=str,
        choices=_WAIT_UNTIL_CHOICES,
        default="networkidle",
        help=(
            "When to consider the page ready for capture. "
            "'networkidle' (default) waits for no network activity for 500ms — "
            "correct for SPAs but may hang on long-polling pages. "
            "Fall back to 'load' or 'domcontentloaded' for those."
        ),
    )
    return parser.parse_args(argv)


async def _fetch(url: str, *, wait_until: _WaitUntil = "networkidle") -> str:
    """Launch a stealth browser, fetch the URL via Crawl4AI, and return markdown.

    Lifecycle:
      1. Launch CloakBrowser with CDP remote debugging enabled.
      2. Connect Crawl4AI's AsyncWebCrawler to the CDP endpoint.
      3. Call arun() — wait for the requested navigation event + buffer delay,
         then capture and convert the page to markdown.
      4. Close the browser.

    Args:
        url: The fully-qualified URL to fetch.
        wait_until: Playwright event to wait for before capturing HTML.
            - ``"networkidle"`` (default): no network activity for 500ms.
            - ``"load"``: page load event fired (JS has run, resources loaded).
            - ``"domcontentloaded"``: DOM ready, JS may not have executed yet.

    Returns:
        The page body converted to markdown. Returns an empty string on failure.

    Side effects:
        Launches and tears down a CloakBrowser subprocess.
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
                print(f"Error: crawler returned no result for {url}", file=sys.stderr)
                return ""

            if not result.success:
                print(
                    f"Error: crawl failed for {url} (status: {result.status_code})",
                    file=sys.stderr,
                )
                return ""

            return result.markdown or ""

    finally:
        # Always close the browser, even if crawling fails.
        await browser.close()


async def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: parse args, fetch the URL, and print markdown to stdout.

    Returns:
        0 on success, 1 on fetch failure, 2 on invalid input.
    """
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if not args.url:
        print("Error: no URL provided.", file=sys.stderr)
        return 2

    print(f"Fetching {args.url} ...", file=sys.stderr, flush=True)

    try:
        markdown = await _fetch(args.url, wait_until=args.wait_until)
    except Exception:
        # Let specific exceptions propagate so we get a proper traceback
        # for debugging, then return a non-zero exit code.
        import traceback

        traceback.print_exc(file=sys.stderr)
        return 1

    if not markdown:
        return 1

    # Print the markdown content to stdout so it can be piped/redirected.
    print(markdown, flush=True)
    print(
        f"Done. {len(markdown)} characters of markdown extracted.",
        file=sys.stderr,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
