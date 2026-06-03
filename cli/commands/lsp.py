"""CLI subcommand: lsp — LSP daemon operations via REST API.

Thin UI layer: parses CLI arguments and sends HTTP requests to the
aivocode REST API server.  No daemon logic, no workspace detection —
all business logic lives server-side.

Commands
- ``aivocode lsp symbols <file>``        — query document symbols
- ``aivocode lsp start``                  — ensure daemon is running
- ``aivocode lsp stop``                   — graceful shutdown
- ``aivocode lsp status``                 — check daemon health
- ``aivocode lsp workspace-symbol <q>``   — search symbols across workspace
- ``aivocode lsp definition <file> -l N -c N``   — go-to definition
- ``aivocode lsp type-definition <file> -l N -c N`` — go-to type definition
- ``aivocode lsp references <file> -l N -c N``     — find references
- ``aivocode lsp hover <file> -l N -c N``          — hover info
- ``aivocode lsp incoming-calls <file> -l N -c N`` — incoming call hierarchy
- ``aivocode lsp outgoing-calls <file> -l N -c N`` — outgoing call hierarchy
- ``aivocode lsp rename-edits <file> -l N -c N -n X`` — preview rename
- ``aivocode lsp diagnostics <file>``      — query diagnostics
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
        description=(
            "Kill the LSP daemon and remove all sockets for the current "
            "workspace (detected from cwd).  No arguments needed — always "
            "does a full cleanup."
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

    # ── Shared position arguments ───────────────────────────────────────
    # Used by definition, type-definition, references, hover,
    # incoming-calls, outgoing-calls, rename-edits.
    _POSITION_OPTIONS = argparse.ArgumentParser(add_help=False)
    _POSITION_OPTIONS.add_argument(
        "-l", "--line",
        type=int,
        required=True,
        help="Line number (1-indexed).",
    )
    _POSITION_OPTIONS.add_argument(
        "-c", "--character",
        type=int,
        required=True,
        help="Character offset (1-indexed).",
    )

    # ── workspace-symbol ───────────────────────────────────────────────
    wsym_parser = lsp_sub.add_parser(
        "workspace-symbol",
        parents=[_GLOBAL_OPTIONS],
        help="Search symbols across the workspace.",
        description="Fuzzy search for symbols by name across the entire workspace.",
    )
    wsym_parser.add_argument("query", type=str, help="Search query string.")
    wsym_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    wsym_parser.set_defaults(func=_handle_workspace_symbol)

    # ── definition ─────────────────────────────────────────────────────
    def_parser = lsp_sub.add_parser(
        "definition",
        parents=[_GLOBAL_OPTIONS, _POSITION_OPTIONS],
        help="Go-to definition.",
        description="Find where the symbol at a position is defined.",
    )
    def_parser.add_argument("file", type=str, help="File path.")
    def_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    def_parser.set_defaults(func=_handle_definition)

    # ── type-definition ─────────────────────────────────────────────────
    tdef_parser = lsp_sub.add_parser(
        "type-definition",
        parents=[_GLOBAL_OPTIONS, _POSITION_OPTIONS],
        help="Go-to type definition.",
        description="Find where the type of the symbol at a position is declared.",
    )
    tdef_parser.add_argument("file", type=str, help="File path.")
    tdef_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    tdef_parser.set_defaults(func=_handle_type_definition)

    # ── references ─────────────────────────────────────────────────────
    ref_parser = lsp_sub.add_parser(
        "references",
        parents=[_GLOBAL_OPTIONS, _POSITION_OPTIONS],
        help="Find references.",
        description="Find all references to the symbol at a position.",
    )
    ref_parser.add_argument("file", type=str, help="File path.")
    ref_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    ref_parser.set_defaults(func=_handle_references)

    # ── hover ──────────────────────────────────────────────────────────
    hover_parser = lsp_sub.add_parser(
        "hover",
        parents=[_GLOBAL_OPTIONS, _POSITION_OPTIONS],
        help="Hover information.",
        description="Get signature, type info, and docstring for a symbol.",
    )
    hover_parser.add_argument("file", type=str, help="File path.")
    hover_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    hover_parser.set_defaults(func=_handle_hover)

    # ── incoming-calls ─────────────────────────────────────────────────
    inc_parser = lsp_sub.add_parser(
        "incoming-calls",
        parents=[_GLOBAL_OPTIONS, _POSITION_OPTIONS],
        help="Incoming call hierarchy.",
        description="Find callers — who calls the function at a position.",
    )
    inc_parser.add_argument("file", type=str, help="File path.")
    inc_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    inc_parser.set_defaults(func=_handle_incoming_calls)

    # ── outgoing-calls ─────────────────────────────────────────────────
    outc_parser = lsp_sub.add_parser(
        "outgoing-calls",
        parents=[_GLOBAL_OPTIONS, _POSITION_OPTIONS],
        help="Outgoing call hierarchy.",
        description="Find callees — what the function at a position calls.",
    )
    outc_parser.add_argument("file", type=str, help="File path.")
    outc_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    outc_parser.set_defaults(func=_handle_outgoing_calls)

    # ── rename-edits ───────────────────────────────────────────────────
    ren_parser = lsp_sub.add_parser(
        "rename-edits",
        parents=[_GLOBAL_OPTIONS, _POSITION_OPTIONS],
        help="Preview rename edits.",
        description="Preview what files would change if the symbol were renamed (no files modified).",
    )
    ren_parser.add_argument("file", type=str, help="File path.")
    ren_parser.add_argument(
        "-n", "--new-name",
        type=str,
        required=True,
        help="New name for the symbol.",
    )
    ren_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    ren_parser.set_defaults(func=_handle_rename_edits)

    # ── diagnostics ────────────────────────────────────────────────────
    diag_parser = lsp_sub.add_parser(
        "diagnostics",
        parents=[_GLOBAL_OPTIONS],
        help="Query diagnostics.",
        description="Get type errors, warnings, and other diagnostics for a file.",
    )
    diag_parser.add_argument("file", type=str, help="File path.")
    diag_parser.add_argument("--workspace", type=str, default=None, help="Git repo root.")
    diag_parser.set_defaults(func=_handle_diagnostics)


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
    """Execute the ``lsp stop`` command via HTTP POST.

    Always uses cwd for workspace detection — no ``--workspace`` flag.
    The server detects the git root server-side.
    """
    ws = str(Path.cwd())

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


# ── Handler helpers ────────────────────────────────────────────────────────────


def _build_body(args: argparse.Namespace, *, extra: dict | None = None) -> dict:
    """Build the JSON body for an HTTP POST from common CLI args.

    Resolves file to absolute path and optionally includes workspace.
    Mutations via *extra* are applied last (e.g. {``"new_name"``: ...}).
    """
    body: dict = {"file": str(Path(args.file).resolve())}
    if args.workspace:
        body["workspace"] = str(Path(args.workspace).resolve())
    if extra:
        body.update(extra)
    return body


def _post_handler(endpoint: str, body: dict, pretty: bool) -> int:
    """Common POST + print + error-handling pattern for all handlers."""
    try:
        result = asyncio.run(_post(endpoint, body))
        _print_json(result, pretty=pretty)
        return 0 if result.get("error") is None else 1
    except httpx.HTTPError:
        _print_json({"error": "REST API unavailable"}, pretty=pretty)
        return 1


# ── New handlers ───────────────────────────────────────────────────────────────


def _handle_workspace_symbol(args: argparse.Namespace) -> int:
    """Execute ``lsp workspace-symbol <query>``."""
    body: dict = {"query": args.query}
    if args.workspace:
        body["workspace"] = str(Path(args.workspace).resolve())
    return _post_handler("/lsp/workspace-symbol", body, args.pretty_format)


def _handle_definition(args: argparse.Namespace) -> int:
    body = _build_body(args, extra={"line": args.line, "character": args.character})
    return _post_handler("/lsp/definition", body, args.pretty_format)


def _handle_type_definition(args: argparse.Namespace) -> int:
    body = _build_body(args, extra={"line": args.line, "character": args.character})
    return _post_handler("/lsp/type-definition", body, args.pretty_format)


def _handle_references(args: argparse.Namespace) -> int:
    body = _build_body(args, extra={"line": args.line, "character": args.character})
    return _post_handler("/lsp/references", body, args.pretty_format)


def _handle_hover(args: argparse.Namespace) -> int:
    body = _build_body(args, extra={"line": args.line, "character": args.character})
    return _post_handler("/lsp/hover", body, args.pretty_format)


def _handle_incoming_calls(args: argparse.Namespace) -> int:
    body = _build_body(args, extra={"line": args.line, "character": args.character})
    return _post_handler("/lsp/call-hierarchy-incoming", body, args.pretty_format)


def _handle_outgoing_calls(args: argparse.Namespace) -> int:
    body = _build_body(args, extra={"line": args.line, "character": args.character})
    return _post_handler("/lsp/call-hierarchy-outgoing", body, args.pretty_format)


def _handle_rename_edits(args: argparse.Namespace) -> int:
    body = _build_body(
        args,
        extra={
            "line": args.line,
            "character": args.character,
            "new_name": args.new_name,
        },
    )
    return _post_handler("/lsp/rename-edits", body, args.pretty_format)


def _handle_diagnostics(args: argparse.Namespace) -> int:
    body = _build_body(args)
    return _post_handler("/lsp/diagnostics", body, args.pretty_format)
