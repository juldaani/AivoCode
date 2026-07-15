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
        help="Fetch a URL and return structured markdown as JSON.",
        description=(
            "Fetch a URL via a headless browser, convert the page to markdown, and "
            "return the result as JSON.\n"
            "\n"
            "Pages are automatically cached for 15 minutes (200‑entry LRU).  "
            "Use --refresh-cache to force a fresh fetch.\n"
            "\n"
            "Truncation: when a full‑page fetch exceeds --limit chars (default 20 000), "
            "the raw markdown is replaced with a compact table of contents (the ``toc`` "
            "field) to keep output manageable.  Use --heading or --line-range to retrieve "
            "specific sections from the ToC (capped at 10 000 chars per section).\n"
            "\n"
            "The ``url`` field is always present in the output so you can see "
            "exactly what was fetched."
        ),
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
            "'load' (default) waits for resources (images, CSS, etc.). "
            "'networkidle' waits until no network activity for 500 ms — "
            "use this or --js-render for JS‑heavy SPAs."
        ),
    )
    parser.add_argument(
        "--js-render",
        action="store_true",
        default=False,
        help=(
            "Enable full JavaScript rendering.  Sets --wait-until to "
            "'networkidle' so the browser waits for dynamic content to load. "
            "Use for SPAs or pages that fetch data after initial HTML load."
        ),
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        default=False,
        help=(
            "Bypass the cache (15‑minute TTL) and always launch a fresh "
            "browser to fetch the page."
        ),
    )
    parser.add_argument(
        "--heading",
        type=str,
        action="append",
        default=None,
        help=(
            "Extract a section by its heading as shown in the ``toc`` "
            "(case‑insensitive).  Use the exact heading text from the ToC — "
            "e.g. if the ToC shows ``{\"Getting Started\": [...]}``, pass "
            "``--heading \"Getting Started\"``.  Repeatable; multiple headings "
            "produce a combined output with ``[heading: …]`` labels."
        ),
    )
    parser.add_argument(
        "--line-range",
        type=str,
        action="append",
        default=None,
        help=(
            "Extract a range of lines from the cached markdown "
            "(1‑based, 'start-end', e.g. ``10-50``).  Repeatable."
        ),
    )
    parser.add_argument(
        "--navigation",
        action="store_true",
        default=False,
        help=(
            "Include extracted page links (``internal`` / ``external`` arrays) "
            "in the result.  Only returned on full‑page fetches (not section extracts)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20000,
        help=(
            "Character count above which a full‑page fetch substitutes a compact "
            "table of contents instead of raw markdown (default 20 000).  "
            "Does NOT affect section extraction via --heading / --line-range — "
            "those have a fixed 10 000‑char cap regardless of this value."
        ),
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help=(
            "Search the page content with hybrid (BM25 + substring) retrieval.  "
            "When set, the response contains ranked chunks with scores instead "
            "of raw markdown.  Use --query-page to paginate."
        ),
    )
    parser.add_argument(
        "--query-page",
        type=int,
        default=0,
        help=(
            "Zero‑based page index for paginated search results.  "
            "Each page returns 5 results.  Default 0."
        ),
    )
    parser.add_argument(
        "--query-substring-weight",
        type=float,
        default=0.4,
        help=(
            "Weight for the exact substring retriever (0–1).  BM25 gets "
            "1 minus this weight.  Higher values favour literal substring "
            "and phrase matching; lower values favour BM25 keyword matching.  "
            "Default 0.4."
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
    if args.query is not None:
        body["query"] = args.query
        body["query_page"] = args.query_page
        body["query_substring_weight"] = args.query_substring_weight

    try:
        result = asyncio.run(_post("/web_ops/webfetch", body))
        _print_json(result, pretty=args.pretty_format)
        return 0 if result.get("success") else 1
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=args.pretty_format)
        return 1
