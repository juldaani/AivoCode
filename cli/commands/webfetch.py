"""CLI subcommand: webfetch — fetch a URL via the REST API.

Thin UI layer: parses CLI arguments, sends an HTTP POST to the
aivocode REST API, and prints the result as JSON.  No processing
logic lives here — the server handles CloakBrowser / Crawl4AI.
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

from cli._utils import _GLOBAL_OPTIONS, _post, _print_json


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``webfetch`` command on the given subparser group."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "webfetch",
        parents=[_GLOBAL_OPTIONS],
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
        "--limit",
        type=int,
        default=20000,
        help=(
            "Character count above which a full-page fetch returns a "
            "compact table of contents instead of raw markdown (default 20000)."
        ),
    )
    parser.set_defaults(func=_handle)


def _handle(args: argparse.Namespace) -> int:
    """Execute the webfetch command via HTTP POST."""
    wait_until = "networkidle" if args.js_render else args.wait_until
    headings = args.heading or []
    line_ranges = args.line_range or []

    body: dict = {
        "url": args.url,
        "wait_until": wait_until,
        "refresh_cache": args.refresh_cache,
        "include_navigation": args.navigation,
        "limit": args.limit,
    }
    if headings:
        body["headings"] = headings
    if line_ranges:
        body["line_ranges"] = line_ranges

    try:
        result = asyncio.run(_post("/web_ops/webfetch", body))
        _print_json(result, pretty=args.pretty_format)
        return 0 if result.get("success") else 1
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=args.pretty_format)
        return 1
