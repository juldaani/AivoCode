"""CLI subcommand: fetch — fetch a URL and output structured result as JSON.

Uses ``web_ops.fetch_url`` (CloakBrowser + Crawl4AI) under the hood.
Outputs the full ``FetchResult`` as JSON to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from web_ops import fetch_url


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``fetch`` command on the given subparser group."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "fetch",
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
        default="networkidle",
        help=(
            "When to consider the page ready for capture. "
            "'networkidle' (default) waits for no network activity for 500 ms."
        ),
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=("fit", "raw"),
        default="fit",
        help=(
            "Content format for the extracted markdown. "
            "'fit' (default) strips boilerplate. 'raw' returns full page."
        ),
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
        "--index",
        type=int,
        default=None,
        help="Extract a section by ToC index number.",
    )
    parser.add_argument(
        "--line-range",
        type=str,
        default=None,
        help="Extract lines from the cached page (1-based, 'start-end', max 100 lines).",
    )
    parser.set_defaults(func=handle)


def handle(args: argparse.Namespace) -> int:
    """Execute the fetch command and return an exit code.

    Returns:
        0 on success, 1 on fetch failure.
    """
    # Take the first heading if multiple were passed.
    # For multiple headings, the agent should make multiple calls.
    heading_arg = args.heading[0] if args.heading else None

    status_parts = [f"Fetching {args.url}"]
    if heading_arg:
        status_parts.append(f"(heading: {heading_arg})")
    if args.index is not None:
        status_parts.append(f"(index: {args.index})")
    if args.line_range:
        status_parts.append(f"(line-range: {args.line_range})")
    if args.refresh_cache:
        status_parts.append("(refreshing cache)")
    print(" ".join(status_parts) + " ...", file=sys.stderr, flush=True)

    result = asyncio.run(
        fetch_url(
            args.url,
            wait_until=args.wait_until,
            output_format=args.output_format,
            heading=heading_arg,
            index=args.index,
            line_range=args.line_range,
            refresh_cache=args.refresh_cache,
        )
    )

    output: dict = {
        "success": result.success,
        "status_code": result.status_code,
        "error": result.error,
        "markdown": result.markdown,
        "links": result.links,
        "toc": result.toc,
        "total_chars": result.total_chars,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False), flush=True)

    # Human-readable summary to stderr.
    if result.success:
        if result.toc:
            print(
                f"Done. {result.total_chars} chars total, "
                f"{len(result.toc)} ToC entries.",
                file=sys.stderr,
                flush=True,
            )
        else:
            link_info = ""
            if result.links:
                n_int = len(result.links.get("internal", []))
                n_ext = len(result.links.get("external", []))
                link_info = f" ({n_int} internal, {n_ext} external links)"
            print(
                f"Done. {len(result.markdown)} chars{link_info}.",
                file=sys.stderr,
                flush=True,
            )
    else:
        print(
            f"Error: fetch failed (error={result.error}, status={result.status_code})",
            file=sys.stderr,
            flush=True,
        )

    return 0 if result.success else 1
