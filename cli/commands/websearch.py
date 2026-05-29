"""CLI subcommand: websearch — neural web/code search via the REST API.

Thin UI layer: parses CLI arguments, sends an HTTP POST to the
aivocode REST API, and prints the result as JSON.  No processing
logic lives here — the server handles the Exa Search API.
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

from cli._utils import _GLOBAL_OPTIONS, _post, _print_json


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
        parents=[_GLOBAL_OPTIONS],
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
    parser.set_defaults(func=_handle)


def _handle(args: argparse.Namespace) -> int:
    """Execute the websearch command via HTTP POST."""
    body: dict = {
        "query": args.query,
        "type": args.type,
        "num_results": args.num_results,
        "highlights": not args.full_text,
        "text": args.full_text,
    }
    if args.include_domains:
        body["include_domains"] = args.include_domains
    if args.exclude_domains:
        body["exclude_domains"] = args.exclude_domains

    try:
        result = asyncio.run(_post("/web_ops/websearch", body))
        _print_json(result, pretty=args.pretty_format)
        return 0 if result.get("success") else 1
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=args.pretty_format)
        return 1
