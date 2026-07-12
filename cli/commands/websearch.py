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
        help="Neural web search via the Exa API.",
        description=(
            "Search the web using the Exa neural search API and return results as JSON.\n"
            "\n"
            "Requires an Exa API key (set via ``EXA_API_KEY`` env var or "
            "``.aivocode.env`` file at the repo root).  Every call costs a "
            "fraction of a cent — the ``cost_dollars`` field in the output "
            "reports the actual cost.\n"
            "\n"
            "By default, each result includes ``highlights`` (query‑relevant excerpts).  "
            "Use --full-text to get the complete page text instead (up to ~10 000 chars)."
        ),
    )
    parser.add_argument(
        "query",
        type=str,
        help=(
            "Natural‑language search query.  Be specific for best results.  "
            "Include language/framework for code searches "
            "(e.g. ``'python asyncio gather'``)."
        ),
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=_SEARCH_TYPE_CHOICES,
        default="auto",
        help=(
            "Search type (speed ↔ depth ↔ cost trade‑off):\n"
            "  auto           — Exa picks the best approach (default).\n"
            "  fast           — Lowest latency, less thorough.\n"
            "  instant        — Fast neural search.\n"
            "  deep‑lite      — LLM‑powered (cheaper than full deep).\n"
            "  deep           — Full deep research with synthesis (more expensive).\n"
            "  deep‑reasoning — Most thorough deep search (most expensive)."
        ),
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=10,
        help="Number of results to return (1–100). Default 10. Basic plans may cap at 10.",
    )
    parser.add_argument(
        "--include-domains",
        type=str,
        action="append",
        default=None,
        help=(
            "Only return results from this domain.  Repeatable "
            "(e.g. --include-domains docs.python.org --include-domains github.com)."
        ),
    )
    parser.add_argument(
        "--exclude-domains",
        type=str,
        action="append",
        default=None,
        help="Exclude results from this domain.  Repeatable.",
    )
    parser.add_argument(
        "--full-text",
        action="store_true",
        default=False,
        help=(
            "Return the full page text for each result instead of highlights.  "
            "Text is capped at ~10 000 chars per result.  When enabled, highlights "
            "are NOT returned — you cannot get both from the CLI."
        ),
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
