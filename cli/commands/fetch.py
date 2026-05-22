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
            "(1-based, 'start-end', max 100 lines). Repeatable."
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
    parser.set_defaults(func=handle)


async def _fetch_multi(
    url: str,
    wait_until: str,
    headings: list[str],
    line_ranges: list[str],
    refresh_cache: bool,
) -> tuple[list[str], list[str]]:
    """Extract multiple sections, fetching the page once if needed.

    Ensures the page is cached first so subsequent section extractions
    are instant cache reads rather than repeated browser launches.

    Each success string is annotated with its selector.
    """
    successes: list[str] = []
    errors: list[str] = []

    # Ensure the page is cached — fetch once (or use existing cache).
    cache_seed = await fetch_url(
        url,
        wait_until=wait_until,
        refresh_cache=refresh_cache,
    )
    if not cache_seed.success:
        return [], [f"Failed to fetch {url}: {cache_seed.error}"]

    # Extract each section from the now-fresh cache.
    for heading in headings:
        r = await fetch_url(
            url, wait_until=wait_until, heading=heading,
        )
        if r.success and r.markdown:
            successes.append(f"[heading: {heading}]\n\n{r.markdown}")
        else:
            errors.append(f"heading '{heading}': {r.error or 'no content'}")

    for lr in line_ranges:
        r = await fetch_url(
            url, wait_until=wait_until, line_range=lr,
        )
        if r.success and r.markdown:
            successes.append(f"[lines: {lr}]\n\n{r.markdown}")
        else:
            errors.append(f"line-range '{lr}': {r.error or 'no content'}")

    return successes, errors


def handle(args: argparse.Namespace) -> int:
    """Execute the fetch command and return an exit code."""
    headings = args.heading or []
    line_ranges = args.line_range or []
    wait_until = "networkidle" if args.js_render else args.wait_until

    has_multi = len(headings) + len(line_ranges) > 1

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

    if has_multi:
        # Multiple sections: fetch once, extract all, merge.
        successes, errors = asyncio.run(
            _fetch_multi(
                args.url,
                wait_until=wait_until,
                headings=headings,
                line_ranges=line_ranges,
                refresh_cache=args.refresh_cache,
            )
        )
        combined = "\n\n---\n\n".join(successes) if successes else ""
        output: dict = {
            "success": bool(successes),
            "status_code": None,
            "error": "; ".join(errors) if errors else None,
            "toc_n_chars": 0,
            "markdown": combined,
            "navigation": None,
            "toc": None,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False), flush=True)
        if args.verbose:
            print(
                f"Done. {len(successes)} sections extracted ({', '.join(errors)})" if errors
                else f"Done. {len(successes)} sections extracted.",
                file=sys.stderr,
                flush=True,
            )
        return 0 if successes else 1

    # Single-selector or full-page path.
    heading_arg = headings[0] if headings else None
    range_arg = line_ranges[0] if line_ranges else None

    result = asyncio.run(
        fetch_url(
            args.url,
            wait_until=wait_until,
            heading=heading_arg,
            line_range=range_arg,
            refresh_cache=args.refresh_cache,
            include_navigation=args.navigation,
        )
    )

    toc_n_chars = (
        len(json.dumps(result.toc, ensure_ascii=False))
        if result.toc is not None
        else 0
    )
    output = {
        "success": result.success,
        "status_code": result.status_code,
        "error": result.error,
        "toc_n_chars": toc_n_chars,
        "markdown": result.markdown,
        "navigation": result.navigation,
        "toc": result.toc,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False), flush=True)

    if args.verbose:
        if result.success:
            nav_info = ""
            if result.navigation:
                n_int = len(result.navigation.get("internal", []))
                n_ext = len(result.navigation.get("external", []))
                nav_info = f" ({n_int} internal, {n_ext} external links)"
            if result.toc:
                # Count entries: triples are chunks, dicts are sections.
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
                print(
                    f"Done. {len(result.markdown)} chars{nav_info}.",
                    file=sys.stderr, flush=True,
                )
        else:
            print(
                f"Error: fetch failed (error={result.error}, status={result.status_code})",
                file=sys.stderr, flush=True,
            )

    return 0 if result.success else 1
