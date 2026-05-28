"""CLI subcommand: lsp — LSP daemon operations.

Thin UI layer: parses CLI arguments and delegates all processing to the
``lsp`` library package.  No daemon logic, workspace detection, or
serialization lives here.

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

from lsp import (
    detect_workspace,
    daemon_status,
    daemon_stop,
    query_document_symbols,
    result_to_output_json,
)
from lsp._daemon import ensure_daemon


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_workspace(args_workspace: str | None) -> Path:
    """Resolve workspace from --workspace flag or auto-detect from cwd."""
    if args_workspace:
        return Path(args_workspace).resolve()
    return detect_workspace(Path.cwd())


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

    # ── symbols ──────────────────────────────────────────────────────────
    sym_parser: argparse.ArgumentParser = lsp_sub.add_parser(
        "symbols",
        help="Query document symbols for a file.",
        description="Query document symbols from the LSP daemon and output as JSON.",
    )
    sym_parser.add_argument(
        "file",
        type=str,
        help=(
            "File path relative to the git repo root "
            "(e.g. mock_pkg/utils.py)."
        ),
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

    # ── start ────────────────────────────────────────────────────────────
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

    # ── stop ─────────────────────────────────────────────────────────────
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

    # ── status ───────────────────────────────────────────────────────────
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


# ── Handlers ──────────────────────────────────────────────────────────────────


def _handle_symbols(args: argparse.Namespace) -> int:
    """Execute the ``lsp symbols`` command."""
    workspace: Path | None = None
    if args.workspace:
        workspace = Path(args.workspace)

    result = asyncio.run(
        query_document_symbols(
            Path(args.file),
            workspace=workspace,
        )
    )
    print(result_to_output_json(result), flush=True)
    return 0 if result.get("error") is None else 1


def _handle_start(args: argparse.Namespace) -> int:
    """Execute the ``lsp start`` command."""
    workspace = _resolve_workspace(args.workspace)

    socket_path = ensure_daemon(workspace)

    result = {
        "workspace": str(workspace),
        "running": True,
        "socket": str(socket_path),
    }
    print(result_to_output_json(result), flush=True)
    return 0


def _handle_stop(args: argparse.Namespace) -> int:
    """Execute the ``lsp stop`` command."""
    workspace = _resolve_workspace(args.workspace)

    daemon_stop(workspace)

    result = {
        "workspace": str(workspace),
        "running": False,
    }
    print(result_to_output_json(result), flush=True)
    return 0


def _handle_status(args: argparse.Namespace) -> int:
    """Execute the ``lsp status`` command."""
    workspace = _resolve_workspace(args.workspace)

    result = daemon_status(workspace)
    print(result_to_output_json(result), flush=True)
    return 0 if result.get("running") else 1
