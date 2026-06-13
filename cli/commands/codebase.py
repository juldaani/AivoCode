"""CLI subcommand: codebase — high-level codebase exploration tools.

Thin-UI layer: parses CLI arguments and sends HTTP requests to the
aivocode REST API server.  No business logic lives here — all
intelligence is server-side.

Commands
- ``aivocode codebase tree``         — recursive file/dir listing
- ``aivocode codebase read``         — read a symbol's body text
- ``aivocode codebase incoming-calls`` — who calls this symbol?
- ``aivocode codebase outgoing-calls`` — what does this symbol call?
- ``aivocode codebase references``   — where is this symbol used?
- ``aivocode codebase overview``     — file ToC with signatures
- ``aivocode codebase explain``      — full symbol report
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cli._utils import _GLOBAL_OPTIONS, _post, _print_json


# ── Helpers ────────────────────────────────────────────────────────────────────


def _resolve_workspace(args_workspace: str | None) -> str:
    if args_workspace:
        return str(Path(args_workspace).resolve())
    return str(Path.cwd())


def _symbol_handler(args: argparse.Namespace, endpoint: str) -> None:
    body: dict = {
        "file": args.file,
        "symbol_name": args.symbol,
        "line": getattr(args, "line", None),
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post(endpoint, body))
    _print_json(result, pretty=args.pretty_format)


# ── Handlers ───────────────────────────────────────────────────────────────────


def _handle_tree(args: argparse.Namespace) -> None:
    body = {"workspace": _resolve_workspace(args.workspace), "suffix": args.suffix}
    result = asyncio.run(_post("/codebase/tree", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_read(args: argparse.Namespace) -> None:
    _symbol_handler(args, "/codebase/read")


def _handle_incoming(args: argparse.Namespace) -> None:
    _symbol_handler(args, "/codebase/incoming-calls")


def _handle_outgoing(args: argparse.Namespace) -> None:
    body: dict = {
        "file": args.file,
        "symbol_name": args.symbol,
        "line": getattr(args, "line", None),
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
        "workspace_only": args.workspace_only,
    }
    result = asyncio.run(_post("/codebase/outgoing-calls", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_references(args: argparse.Namespace) -> None:
    _symbol_handler(args, "/codebase/references")


def _handle_overview(args: argparse.Namespace) -> None:
    body = {
        "file": args.file,
        "depth": args.depth,
        "workspace": _resolve_workspace(args.workspace),
    }
    result = asyncio.run(_post("/codebase/overview", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_explain(args: argparse.Namespace) -> None:
    _symbol_handler(args, "/codebase/explain")


def _handle_search(args: argparse.Namespace) -> None:
    body: dict = {
        "query": args.query,
        "kind": args.kind,
        "limit": args.limit,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/search", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_impact(args: argparse.Namespace) -> None:
    body: dict = {
        "file": args.file,
        "symbol_name": args.symbol,
        "line": getattr(args, "line", None),
        "depth": args.depth,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/impact", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_definition(args: argparse.Namespace) -> None:
    _symbol_handler(args, "/codebase/definition")


def _handle_hover(args: argparse.Namespace) -> None:
    _symbol_handler(args, "/codebase/hover")


def _handle_diagnostics(args: argparse.Namespace) -> None:
    body: dict = {
        "file": args.file,
        "max": args.max,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/diagnostics", body))
    _print_json(result, pretty=args.pretty_format)


# ── Import-graph handlers ───────────────────────────────────────────────────────


def _handle_import_dependents(args: argparse.Namespace) -> None:
    body = {
        "file": args.file,
        "depth": args.depth,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/import-dependents", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_import_dependencies(args: argparse.Namespace) -> None:
    body = {
        "file": args.file,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/import-dependencies", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_affected_tests(args: argparse.Namespace) -> None:
    body = {
        "file": args.file,
        "depth": args.depth,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/affected-tests", body))
    _print_json(result, pretty=args.pretty_format)


# ── Shared argument definitions ────────────────────────────────────────────────

def _add_symbol_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=str, help="Source file path.")
    parser.add_argument("--symbol", "-s", type=str, required=True, help="Symbol name.")
    parser.add_argument("--line", "-l", type=int, default=None,
                        help="Line number for disambiguation.")
    parser.add_argument("--workspace", type=str,
                        help="Workspace root path (auto-detected if omitted).")


# ── Subparser registration ─────────────────────────────────────────────────────


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    cb_parser = subparsers.add_parser(
        "codebase",
        help="Codebase exploration tools.",
        description="High-level codebase exploration tools for AI agents.",
    )
    cb_sub = cb_parser.add_subparsers(title="commands", dest="codebase_command")
    cb_sub.required = True

    # ── tree ───────────────────────────────────────────────────────────
    tp = cb_sub.add_parser("tree", parents=[_GLOBAL_OPTIONS],
                            help="Recursive file/directory tree.")
    tp.add_argument("--workspace", type=str)
    tp.add_argument("--suffix", type=str, default=None)
    tp.set_defaults(func=_handle_tree)

    # ── read ───────────────────────────────────────────────────────────
    rdp = cb_sub.add_parser("read", parents=[_GLOBAL_OPTIONS],
                             help="Read a symbol's body text.")
    _add_symbol_args(rdp)
    rdp.set_defaults(func=_handle_read)

    # ── incoming-calls ─────────────────────────────────────────────────
    icp = cb_sub.add_parser("incoming-calls", parents=[_GLOBAL_OPTIONS],
                             help="Who calls this symbol?")
    _add_symbol_args(icp)
    icp.set_defaults(func=_handle_incoming)

    # ── outgoing-calls ─────────────────────────────────────────────────
    ocp = cb_sub.add_parser("outgoing-calls", parents=[_GLOBAL_OPTIONS],
                             help="What does this symbol call?")
    _add_symbol_args(ocp)
    ocp.add_argument("--include-external", action="store_false", dest="workspace_only",
                      help="Include external (stdlib/site-packages) calls in output.")
    ocp.set_defaults(func=_handle_outgoing, workspace_only=True)

    # ── references ─────────────────────────────────────────────────────
    refp = cb_sub.add_parser("references", parents=[_GLOBAL_OPTIONS],
                              help="Where is this symbol used?")
    _add_symbol_args(refp)
    refp.set_defaults(func=_handle_references)

    # ── definition ──────────────────────────────────────────────────────
    defp = cb_sub.add_parser("definition", parents=[_GLOBAL_OPTIONS],
                              help="Go-to-definition with snippet.")
    _add_symbol_args(defp)
    defp.set_defaults(func=_handle_definition)

    # ── hover ───────────────────────────────────────────────────────────
    hvp = cb_sub.add_parser("hover", parents=[_GLOBAL_OPTIONS],
                             help="Signature + docstring (works on external libs).")
    _add_symbol_args(hvp)
    hvp.set_defaults(func=_handle_hover)

    # ── diagnostics ─────────────────────────────────────────────────────
    dgp = cb_sub.add_parser("diagnostics", parents=[_GLOBAL_OPTIONS],
                             help="File diagnostics with snippets.")
    dgp.add_argument("file", type=str, help="Source file to check.")
    dgp.add_argument("--max", type=int, default=50,
                      help="Max diagnostics to return (default 50).")
    dgp.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    dgp.set_defaults(func=_handle_diagnostics)

    # ── overview ───────────────────────────────────────────────────────
    ovp = cb_sub.add_parser("overview", parents=[_GLOBAL_OPTIONS],
                             help="File ToC with signatures and ref counts.")
    ovp.add_argument("file", type=str, help="Source file path.")
    ovp.add_argument("--depth", "-d", type=int, default=0,
                      help="Symbol tree depth (default 0 = top-level only).")
    ovp.add_argument("--workspace", type=str)
    ovp.set_defaults(func=_handle_overview)

    # ── explain ────────────────────────────────────────────────────────
    exp = cb_sub.add_parser("explain", parents=[_GLOBAL_OPTIONS],
                             help="Full symbol report.")
    _add_symbol_args(exp)
    exp.set_defaults(func=_handle_explain)

    # ── search ──────────────────────────────────────────────────────────
    sp = cb_sub.add_parser("search", parents=[_GLOBAL_OPTIONS],
                            help="Search symbols across the workspace.")
    sp.add_argument("query", type=str, help="Search query string.")
    sp.add_argument("--kind", type=str, default=None,
                    help="Filter by symbol kind (e.g. 'Class', 'Function').")
    sp.add_argument("--limit", type=int, default=50,
                    help="Max results (default 50).")
    sp.add_argument("--workspace", type=str)
    sp.set_defaults(func=_handle_search)

    # ── impact ──────────────────────────────────────────────────────────
    imp = cb_sub.add_parser("impact", parents=[_GLOBAL_OPTIONS],
                             help="Change impact: symbol callers + file-level blast radius.")
    _add_symbol_args(imp)
    imp.add_argument("--depth", "-d", type=int, default=10,
                      help="How many import hops for file-level blast radius (default 10).")
    imp.set_defaults(func=_handle_impact)

    # ── import-dependents ───────────────────────────────────────────────
    idp = cb_sub.add_parser("import-dependents", parents=[_GLOBAL_OPTIONS],
                             help="Files that import this file (use --depth for transitives).")
    idp.add_argument("file", type=str, help="Source file to check.")
    idp.add_argument("--depth", "-d", type=int, default=1,
                      help="How many import hops to follow (1 = direct only, 0 = unlimited).")
    idp.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    idp.set_defaults(func=_handle_import_dependents)

    # ── import-dependencies ─────────────────────────────────────────────
    idd = cb_sub.add_parser("import-dependencies", parents=[_GLOBAL_OPTIONS],
                             help="What files does this file import?")
    idd.add_argument("file", type=str, help="Source file to check.")
    idd.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    idd.set_defaults(func=_handle_import_dependencies)

    # ── affected-tests ──────────────────────────────────────────────────
    atp = cb_sub.add_parser("affected-tests", parents=[_GLOBAL_OPTIONS],
                             help="Which test files are affected if this file changes?")
    atp.add_argument("file", type=str,
                      help="File whose changes you want to check (e.g. the file you edited).")
    atp.add_argument("--depth", "-d", type=int, default=10,
                      help="How many import hops to follow (default 10).")
    atp.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    atp.set_defaults(func=_handle_affected_tests)
