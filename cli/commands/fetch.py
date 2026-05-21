"""CLI subcommand: fetch — fetch a URL and print its content as markdown.

Uses ``web_ops.fetch_url`` (CloakBrowser + Crawl4AI) under the hood.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from web_ops import fetch_url

_WAIT_UNTIL_CHOICES: tuple[str, ...] = ("domcontentloaded", "load", "networkidle")
_OUTPUT_FORMAT_CHOICES: tuple[str, ...] = ("fit", "raw")


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``fetch`` command on the given subparser group."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "fetch",
        help="Fetch a URL and print its content as markdown.",
        description="Fetch a URL via CloakBrowser + Crawl4AI and print the page body as markdown.",
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
            "Output format for the extracted content. "
            "'fit' (default) returns the main article body with boilerplate "
            "(nav, ads, sidebars) stripped — cleaner but links are removed "
            "from the markdown (available as structured data). "
            "'raw' returns the full page converted to markdown, links included inline."
        ),
    )
    parser.set_defaults(func=handle)


def handle(args: argparse.Namespace) -> int:
    """Execute the fetch command and return an exit code.

    Returns:
        0 on success, 1 on fetch failure.
    """
    print(f"Fetching {args.url} ...", file=sys.stderr, flush=True)

    result = asyncio.run(
        fetch_url(args.url, wait_until=args.wait_until, output_format=args.output_format)
    )

    if not result.success:
        details = f"status={result.status_code}" if result.status_code else ""
        err_info = f" (error: {result.error})" if result.error else ""
        print(f"Error: fetch failed for {args.url} {details}{err_info}".strip(), file=sys.stderr)
        return 1

    # Markdown to stdout — clean for piping / redirection.
    if result.markdown:
        print(result.markdown, flush=True)

    # Print a link summary to stderr when available (fit mode).
    if result.links:
        internal_count = len(result.links.get("internal", []))
        external_count = len(result.links.get("external", []))
        print(
            f"Links: {internal_count} internal, {external_count} external",
            file=sys.stderr,
            flush=True,
        )

    print(
        f"Done. {len(result.markdown)} characters of markdown extracted.",
        file=sys.stderr,
        flush=True,
    )
    return 0
