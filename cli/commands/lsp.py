"""CLI subcommand: lsp — LSP daemon operations via REST API.

Thin UI layer: parses CLI arguments and sends HTTP requests to the
aivocode REST API server.  No daemon logic, workspace detection, or
serialization lives here (workspace detection is a local git operation
and stays).

Commands
- ``aivocode lsp symbols <file>``  — query document symbols
- ``aivocode lsp start``            — ensure daemon is running
- ``aivocode lsp stop``             — graceful shutdown
- ``aivocode lsp status``           — check daemon health
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

from lsp._workspace import detect_workspace


# ── HTTP transport ────────────────────────────────────────────────────

_AIVOCODE_URL = os.environ.get("AIVOCODE_URL", "http://localhost:8000")


async def _post(path: str, body: dict) -> dict:
    """Send a POST request to the REST API, return parsed JSON."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{_AIVOCODE_URL}{path}", json=body)
        resp.raise_for_status()
        return resp.json()


async def _get(path: str, params: dict) -> dict:
    """Send a GET request to the REST API, return parsed JSON."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_AIVOCODE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()


# ── Helpers ───────────────────────────────────────────────────────────


def _resolve_workspace(args_workspace: str | None) -> Path:
    """Resolve workspace from --workspace flag or auto-detect from cwd."""
    if args_workspace:
        return Path(args_workspace).resolve()
    return detect_workspace(Path.cwd())


def _print_json(data: dict) -> None:
    """Print a dict as a single-line JSON string to stdout."""
    print(json.dumps(data, ensure_ascii=False), flush=True)


# ── Subparser registration ────────────────────────────────────────────


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``lsp`` command group on the given subparser group."""
    lsp_parser: argparse.ArgumentParser = subparsers.add_parser(
        "lsp",
        help="LSP daemon operations.",
        description="Manage the LSP daemon and query document symbols.",
    )
    lsp_sub = lsp_parser.add_subparsers(
        title="commands",
        dest="lsp_command",
    )
    lsp_sub.required = True

    # ── symbols ──────────────────────────────────────────────────────
    sym_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "symbols",
        help="Query document symbols for a file.",
        description="Query document symbols from the LSP daemon and output as JSON.",
    )
    sym_parser.add_argument(
        "file",
        type=str,
        help="File path relative to the git repo root (e.g. mock_pkg/utils.py).",
    )
    sym_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Git repo root. Auto-detected via ``git rev-parse --show-toplevel`` "
            "from the file path if not provided."
        ),
    )
    sym_parser.set_defaults(func=_handle_symbols)

    # ── start ────────────────────────────────────────────────────────
    start_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "start",
        help="Ensure the LSP daemon is running.",
        description=(
            "Start the LSP daemon for a workspace if not already running. "
            "No-op if already running."
        ),
    )
    start_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Git repo root. Auto-detected from cwd "
            "via ``git rev-parse --show-toplevel`` if not provided."
        ),
    )
    start_parser.set_defaults(func=_handle_start)

    # ── stop ─────────────────────────────────────────────────────────
    stop_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "stop",
        help="Shut down the LSP daemon.",
        description="Gracefully shut down the LSP daemon for a workspace. Idempotent.",
    )
    stop_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Git repo root. Auto-detected from cwd "
            "via ``git rev-parse --show-toplevel`` if not provided."
        ),
    )
    stop_parser.set_defaults(func=_handle_stop)

    # ── status ───────────────────────────────────────────────────────
    status_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "status",
        help="Check LSP daemon health.",
        description="Check whether the LSP daemon is running for a workspace.",
    )
    status_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Git repo root. Auto-detected from cwd "
            "via ``git rev-parse --show-toplevel`` if not provided."
        ),
    )
    status_parser.set_defaults(func=_handle_status)


# ── Handlers ──────────────────────────────────────────────────────────


def _handle_symbols(args: argparse.Namespace) -> int:
    """Execute the ``lsp symbols`` command via HTTP POST."""
    body: dict = {"file": args.file}
    if args.workspace:
        body["workspace"] = args.workspace

    try:
        result = asyncio.run(_post("/lsp/symbols", body))
        _print_json(result)
        return 0 if result.get("error") is None else 1
    except httpx.HTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _handle_start(args: argparse.Namespace) -> int:
    """Execute the ``lsp start`` command via HTTP POST."""
    ws = _resolve_workspace(args.workspace)

    try:
        result = asyncio.run(_post("/lsp/start", {"workspace": str(ws)}))
        _print_json(result)
        return 0
    except httpx.HTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _handle_stop(args: argparse.Namespace) -> int:
    """Execute the ``lsp stop`` command via HTTP POST."""
    ws = _resolve_workspace(args.workspace)

    try:
        result = asyncio.run(_post("/lsp/stop", {"workspace": str(ws)}))
        _print_json(result)
        return 0
    except httpx.HTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _handle_status(args: argparse.Namespace) -> int:
    """Execute the ``lsp status`` command via HTTP GET."""
    ws = _resolve_workspace(args.workspace)

    try:
        result = asyncio.run(
            _get("/lsp/status", {"workspace": str(ws)})
        )
        _print_json(result)
        return 0 if result.get("running") else 1
    except httpx.HTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
