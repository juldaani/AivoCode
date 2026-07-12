"""Shared CLI utilities — HTTP transport, JSON output, and global argparse options.

What this module provides
- ``_AIVOCODE_URL``: the REST API base URL (from ``$AIVOCODE_URL`` env var,
  defaults to ``http://aivocode:8000`` — the compose service name).
- ``_post(path, body)``: async HTTP POST returning parsed JSON.
- ``_get(path, params)``: async HTTP GET returning parsed JSON.
- ``_print_json(data, *, pretty)``: print a dict as JSON to stdout.
- ``_GLOBAL_OPTIONS``: argparse parent parser with ``--pretty-format``.

Why this exists
- Every CLI subcommand needs the same HTTP transport and output logic.
  Rather than duplicating ``_post`` / ``_get`` / ``_print_json`` in each
  command module, they live here as the single source of truth.
- ``_GLOBAL_OPTIONS`` is used via ``parents=[_GLOBAL_OPTIONS]`` so that
  ``--pretty-format`` is available on every subcommand without repetition.

Usage (in a command module)::

    from cli._utils import _GLOBAL_OPTIONS, _post, _get, _print_json

    def add_subparser(subparsers):
        parser = subparsers.add_parser("foo", parents=[_GLOBAL_OPTIONS], ...)
        parser.set_defaults(func=_handle_foo)

    def _handle_foo(args):
        result = asyncio.run(_post("/foo", {"bar": args.bar}))
        _print_json(result, pretty=args.pretty_format)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx


# ── REST API endpoint ─────────────────────────────────────────────────────────

_AIVOCODE_URL: str = os.environ.get("AIVOCODE_URL", "http://aivocode:8000")


async def _post(path: str, body: dict) -> dict:
    """Send a POST request to the REST API, return parsed JSON dict.

    Raises ``httpx.HTTPError`` on transport or HTTP-level failures.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{_AIVOCODE_URL}{path}", json=body)
        resp.raise_for_status()
        return resp.json()


async def _get(path: str, params: dict) -> dict:
    """Send a GET request to the REST API, return parsed JSON dict.

    Raises ``httpx.HTTPError`` on transport or HTTP-level failures.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_AIVOCODE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()


# ── JSON output ───────────────────────────────────────────────────────────────


def _print_json(data: dict, *, pretty: bool = False) -> None:
    """Print *data* as a JSON string to stdout.

    When *pretty* is ``True``, the output is indented for human readability.
    Otherwise it is a compact single-line string (saves tokens for agent
    consumers).
    """
    indent: int | None = 2 if pretty else None
    print(
        json.dumps(data, indent=indent, ensure_ascii=False),
        flush=True,
    )


# ── Global argparse options (shared across all subcommands) ───────────────────
# Used via ``parents=[_GLOBAL_OPTIONS]`` so that ``--pretty-format`` appears in
# the help of every leaf subparser without manual repetition.

_GLOBAL_OPTIONS = argparse.ArgumentParser(add_help=False)
_GLOBAL_OPTIONS.add_argument(
    "--pretty-format",
    action="store_true",
    default=False,
    help="Pretty-print JSON output with indentation (for human debugging only; default: compact).",
)
