"""CLI subcommand: lsp — LSP daemon operations via REST API.

Thin UI layer: parses CLI arguments and sends HTTP requests to the
aivocode REST API server.  No daemon logic, no workspace detection —
all business logic lives server-side.

Commands
- ``aivocode lsp symbols <file>``  — query document symbols
- ``aivocode lsp start``            — ensure daemon is running
- ``aivocode lsp stop``             — graceful shutdown
- ``aivocode lsp status``           — check daemon health
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx

from cli._utils import _GLOBAL_OPTIONS, _get, _post, _print_json


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_path(args_workspace: str | None) -> str:
    """Return an absolute path string for the workspace resolution hint.

    If ``--workspace`` is given, resolves it to absolute.  Otherwise
    returns the current working directory as an absolute path.  The
    server calls ``detect_workspace()`` on whatever path we send,
    so we don't need git knowledge client-side.
    """
    if args_workspace:
        return str(Path(args_workspace).resolve())
    return str(Path.cwd())


# ── Subparser registration ────────────────────────────────────────────────────


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

    # ── symbols ────────────────────────────────────────────────────────
    sym_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "symbols",
        parents=[_GLOBAL_OPTIONS],
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
            "Git repo root. Auto-detected server-side via "
            "``git rev-parse --show-toplevel`` from the file path if not provided."
        ),
    )
    sym_parser.set_defaults(func=_handle_symbols)

    # ── start ──────────────────────────────────────────────────────────
    start_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "start",
        parents=[_GLOBAL_OPTIONS],
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
            "Path within the git workspace (or the workspace itself). "
            "Auto-detected server-side from cwd if not provided."
        ),
    )
    start_parser.set_defaults(func=_handle_start)

    # ── stop ───────────────────────────────────────────────────────────
    stop_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "stop",
        parents=[_GLOBAL_OPTIONS],
        help="Shut down the LSP daemon.",
        description="Gracefully shut down the LSP daemon for a workspace. Idempotent.",
    )
    stop_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Path within the git workspace (or the workspace itself). "
            "Auto-detected server-side from cwd if not provided."
        ),
    )
    stop_parser.set_defaults(func=_handle_stop)

    # ── status ─────────────────────────────────────────────────────────
    status_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "status",
        parents=[_GLOBAL_OPTIONS],
        help="Check LSP daemon health.",
        description="Check whether the LSP daemon is running for a workspace.",
    )
    status_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Path within the git workspace (or the workspace itself). "
            "Auto-detected server-side from cwd if not provided."
        ),
    )
    status_parser.set_defaults(func=_handle_status)


# ── Handlers ──────────────────────────────────────────────────────────────────


def _handle_symbols(args: argparse.Namespace) -> int:
    """Execute the ``lsp symbols`` command via HTTP POST."""
    # Resolve file to absolute — server detects workspace from it.
    file_abs = str(Path(args.file).resolve())

    body: dict = {"file": file_abs}
    if args.workspace:
        body["workspace"] = str(Path(args.workspace).resolve())

    try:
        result = asyncio.run(_post("/lsp/symbols", body))
        _print_json(result, pretty=args.pretty_format)
        return 0 if result.get("error") is None else 1
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=args.pretty_format)
        return 1


def _handle_start(args: argparse.Namespace) -> int:
    """Execute the ``lsp start`` command via HTTP POST."""
    ws = _resolve_path(args.workspace)

    try:
        result = asyncio.run(_post("/lsp/start", {"workspace": ws}))
        _print_json(result, pretty=args.pretty_format)
        return 0
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=args.pretty_format)
        return 1


def _handle_stop(args: argparse.Namespace) -> int:
    """Execute the ``lsp stop`` command via HTTP POST."""
    ws = _resolve_path(args.workspace)

    try:
        result = asyncio.run(_post("/lsp/stop", {"workspace": ws}))
        _print_json(result, pretty=args.pretty_format)
        return 0
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=args.pretty_format)
        return 1


def _handle_status(args: argparse.Namespace) -> int:
    """Execute the ``lsp status`` command via HTTP GET."""
    ws = _resolve_path(args.workspace)

    try:
        result = asyncio.run(_get("/lsp/status", {"workspace": ws}))
        _print_json(result, pretty=args.pretty_format)
        return 0 if result.get("running") else 1
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=args.pretty_format)
        return 1
