"""CLI subcommand: codebase — high-level codebase exploration tools.

Thin-UI layer: parses CLI arguments and sends HTTP requests to the
aivocode REST API server.  No business logic lives here — all
intelligence is server-side.

Commands
- ``aivocode codebase root`` — list top-level workspace directories
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cli._utils import _GLOBAL_OPTIONS, _post, _print_json


# ── Helpers ────────────────────────────────────────────────────────────────────


def _resolve_workspace(args_workspace: str | None) -> str:
    """Return an absolute path string for the workspace resolution hint."""
    if args_workspace:
        return str(Path(args_workspace).resolve())
    return str(Path.cwd())


# ── Handlers ───────────────────────────────────────────────────────────────────


def _handle_root(args: argparse.Namespace) -> None:
    """Handle ``aivocode codebase root``."""
    body = {"workspace": _resolve_workspace(args.workspace)}
    result = asyncio.run(_post("/codebase/root", body))
    _print_json(result, pretty=args.pretty_format)


# ── Subparser registration ─────────────────────────────────────────────────────


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``codebase`` command group on the given subparser group."""
    cb_parser = subparsers.add_parser(
        "codebase",
        help="Codebase exploration tools.",
        description="High-level codebase exploration tools for AI agents.",
    )
    cb_sub = cb_parser.add_subparsers(
        title="commands",
        dest="codebase_command",
    )
    cb_sub.required = True

    # ── root ───────────────────────────────────────────────────────────
    root_parser = cb_sub.add_parser(
        "root",
        parents=[_GLOBAL_OPTIONS],
        help="List top-level directories in the workspace.",
        description="List top-level non-hidden directories in the workspace root.",
    )
    root_parser.add_argument(
        "--workspace",
        type=str,
        help="Workspace root path (auto-detected if omitted).",
    )
    root_parser.set_defaults(func=_handle_root)
