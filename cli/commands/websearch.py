"""CLI subcommand: websearch — neural web/code search via the Exa Search API.

Thin UI layer: parses CLI arguments, calls ``web_ops.web_search``, and prints
the result as JSON.  No processing logic lives here.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from web_ops import web_search
from web_ops.searcher import result_to_output_json


_SEARCH_TYPE_CHOICES = (
    "auto",
    "fast",
    "instant",
    "deep-lite",
    "deep",
    "deep-reasoning",
)


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``websearch`` command on the given subparser group."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "websearch",
        help="Search the web or code via the Exa API.",
        description=(
            "Perform a neural web or code search using the Exa Search API "
            "and output the result as JSON."
        ),
    )
    parser.add_argument(
        "query",
        type=str,
        help="Search query. Use natural language; be specific for best results. "
             "For code, include language/framework (e.g. 'python asyncio gather').",
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=_SEARCH_TYPE_CHOICES,
        default="auto",
        help="Search type. One of 'auto' (default), 'fast', 'instant', "
             "'deep-lite', 'deep', 'deep-reasoning'.",
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=10,
        help="Number of results to return (1-100). Default 10.",
    )
    parser.add_argument(
        "--include-domains",
        type=str,
        action="append",
        default=None,
        help="Restrict results to this domain. Repeatable "
             "(e.g. --include-domains github.com --include-domains stackoverflow.com).",
    )
    parser.add_argument(
        "--exclude-domains",
        type=str,
        action="append",
        default=None,
        help="Exclude results from this domain. Repeatable.",
    )
    parser.add_argument(
        "--full-text",
        action="store_true",
        default=False,
        help="Return full page text for each result (default: highlights only).",
    )
    parser.set_defaults(func=handle)


def handle(args: argparse.Namespace) -> int:
    """Execute the websearch command and return an exit code."""
    # ── All processing delegated to web_ops ─────────────────────────────
    result = asyncio.run(
        web_search(
            args.query,
            type=args.type,
            num_results=args.num_results,
            highlights=not args.full_text,
            text=args.full_text,
            include_domains=args.include_domains,
            exclude_domains=args.exclude_domains,
        )
    )

    print(result_to_output_json(result), flush=True)

    if not result.success:
        print(
            f"websearch: error: {result.error}",
            file=sys.stderr,
            flush=True,
        )

    return 0 if result.success else 1
