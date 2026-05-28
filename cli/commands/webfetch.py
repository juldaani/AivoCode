"""CLI subcommand: webfetch — fetch a URL and output structured result as JSON.

Thin UI layer: parses CLI arguments, calls ``web_ops.fetch_urls`` for all
processing (full‑page fetch, single/multi‑section extraction, JSON
serialization), and prints the result.  No processing logic lives here.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from web_ops import fetch_urls
from web_ops.fetcher import result_to_output_json


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``webfetch`` command on the given subparser group."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "webfetch",
        help="Fetch a URL and output the result as JSON.",
        description="Fetch a URL via CloakBrowser + Crawl4AI and output structured result as JSON.",
    )
    parser.add_argument(
        "url",
        type=str,
        help="The URL to fetch (e.g. https://example.com).",
    )
    parser.add_argument(
        "--wait-until",
        type=str,
        choices=("domcontentloaded", "load", "networkidle"),
        default="load",
        help=(
            "When to consider the page ready for capture. "
            "'load' (default) waits for all resources to load. "
            "Use 'networkidle' or --js-render for JS-heavy SPAs."
        ),
    )
    parser.add_argument(
        "--js-render",
        action="store_true",
        default=False,
        help="Enable full JavaScript rendering (alias for --wait-until networkidle). "
             "Use for SPAs or pages that fetch content dynamically.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        default=False,
        help="Bypass cache and always fetch fresh content from the web.",
    )
    parser.add_argument(
        "--heading",
        type=str,
        action="append",
        default=None,
        help="Extract a section by heading text (case-insensitive). Repeatable.",
    )
    parser.add_argument(
        "--line-range",
        type=str,
        action="append",
        default=None,
        help=(
            "Extract lines from the cached page "
            "(1-based, 'start-end'). Repeatable."
        ),
    )
    parser.add_argument(
        "--navigation",
        action="store_true",
        default=False,
        help="Include extracted page links (internal/external) in the result.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Show status messages to stderr (default: silent, JSON only).",
    )
    parser.add_argument(
        "--pretty-format",
        action="store_true",
        default=False,
        help="Pretty-print the toc field with indent=2 for human readability "
             "(default: compact single-line toc).",
    )
    parser.set_defaults(func=handle)


def handle(args: argparse.Namespace) -> int:
    """Execute the webfetch command and return an exit code."""
    headings = args.heading or []
    line_ranges = args.line_range or []
    wait_until = "networkidle" if args.js_render else args.wait_until
    is_multi = len(headings) + len(line_ranges) > 1

    # Status message.
    if args.verbose:
        status_parts = [f"Fetching {args.url}"]
        if args.js_render:
            status_parts.append("(JS render)")
        if headings:
            status_parts.append(f"(headings: {', '.join(headings)})")
        if line_ranges:
            status_parts.append(f"(ranges: {', '.join(line_ranges)})")
        if args.refresh_cache:
            status_parts.append("(refreshing cache)")
        print(" ".join(status_parts) + " ...", file=sys.stderr, flush=True)

    # ── All processing delegated to web_ops ─────────────────────────────
    result = asyncio.run(
        fetch_urls(
            args.url,
            wait_until=wait_until,
            headings=headings if headings else None,
            line_ranges=line_ranges if line_ranges else None,
            refresh_cache=args.refresh_cache,
            include_navigation=args.navigation,
        )
    )

    print(result_to_output_json(result, compact_toc=not args.pretty_format), flush=True)

    # ── Verbose stderr stats ────────────────────────────────────────────
    if args.verbose:
        if result.success:
            nav_info = ""
            if result.navigation:
                n_int = len(result.navigation.get("internal", []))
                n_ext = len(result.navigation.get("external", []))
                nav_info = f" ({n_int} internal, {n_ext} external links)"

            if is_multi:
                # Multi‑section: count successes from markdown.
                n_sections = len(headings) + len(line_ranges)
                n_errors = 0
                if result.error:
                    n_errors = result.error.count("; ") + 1
                n_ok = n_sections - n_errors
                msg = f"Done. {n_ok} sections extracted."
                if result.error:
                    msg += f" Errors: {result.error}"
                print(msg + nav_info + ".", file=sys.stderr, flush=True)
            elif result.toc:
                # Full page with ToC: count chunks and sections.
                n_chunks = sum(
                    1 for e in result.toc
                    if isinstance(e, list) and isinstance(e[0], int)
                )
                n_sections = sum(
                    1 for e in result.toc if isinstance(e, dict)
                )
                print(
                    f"Done. {result.total_chars} chars total, "
                    f"{n_chunks} chunks, {n_sections} sections{nav_info}.",
                    file=sys.stderr, flush=True,
                )
            else:
                # Single section or small page.
                print(
                    f"Done. {len(result.markdown)} chars{nav_info}.",
                    file=sys.stderr, flush=True,
                )
        else:
            print(
                f"Error: fetch failed (error={result.error}, "
                f"status={result.status_code})",
                file=sys.stderr, flush=True,
            )

    return 0 if result.success else 1
