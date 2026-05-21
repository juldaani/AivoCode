"""CLI subcommand: fetch — fetch a URL and output structured result as JSON.

Uses ``web_ops.fetch_url`` (CloakBrowser + Crawl4AI) under the hood.
Outputs the full ``FetchResult`` as JSON to stdout — agents parse the
structured fields (markdown, success, links, error) directly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from web_ops import fetch_url

_WAIT_UNTIL_CHOICES: tuple[str, ...] = ("domcontentloaded", "load", "networkidle")
_OUTPUT_FORMAT_CHOICES: tuple[str, ...] = ("fit", "raw")


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
        choices=_WAIT_UNTIL_CHOICES,
        default="networkidle",
        help=(
            "When to consider the page ready for capture. "
            "'networkidle' (default) waits for no network activity for 500 ms — "
            "correct for SPAs but may hang on long-polling pages. "
            "Fall back to 'load' or 'domcontentloaded' for those."
        ),
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=_OUTPUT_FORMAT_CHOICES,
        default="fit",
        help=(
            "Content format for the extracted markdown. "
            "'fit' (default) returns the main article body with boilerplate "
            "(nav, ads, sidebars) stripped — links in the content are removed "
            "but available as structured links. "
            "'raw' returns the full page converted to markdown, links inline."
        ),
    )
    parser.set_defaults(func=handle)


def _format_links(result) -> dict | None:
    """Build a compact link summary for stderr, or None if no links."""
    if not result.links:
        return None
    return {
        "internal": len(result.links.get("internal", [])),
        "external": len(result.links.get("external", [])),
    }


def handle(args: argparse.Namespace) -> int:
    """Execute the fetch command and return an exit code.

    Prints the full ``FetchResult`` as JSON to stdout — agents parse
    ``.markdown``, ``.success``, ``.links``, ``.error`` directly.
    Status messages go to stderr.

    Returns:
        0 on success, 1 on fetch failure.
    """
    print(f"Fetching {args.url} ...", file=sys.stderr, flush=True)

    result = asyncio.run(
        fetch_url(args.url, wait_until=args.wait_until, output_format=args.output_format)
    )

    # Build a dict with all fields — explicit so the JSON schema is stable.
    output: dict = {
        "success": result.success,
        "status_code": result.status_code,
        "error": result.error,
        "markdown": result.markdown,
        "links": result.links,
    }

    # Structured result to stdout — agents parse this.
    print(json.dumps(output, indent=2, ensure_ascii=False), flush=True)

    # Human-readable summary to stderr.
    link_summary = _format_links(result)
    if result.success:
        parts = [f"Done. {len(result.markdown)} chars of markdown"]
        if link_summary:
            parts.append(f"({link_summary['internal']} internal, {link_summary['external']} external links)")
        print(" ".join(parts), file=sys.stderr, flush=True)
    else:
        print(
            f"Error: fetch failed (error={result.error}, status={result.status_code})",
            file=sys.stderr,
            flush=True,
        )

    return 0 if result.success else 1
