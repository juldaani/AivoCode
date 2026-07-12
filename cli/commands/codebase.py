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


def _handle_architecture(args: argparse.Namespace) -> None:
    body: dict = {
        "hotspots": args.hotspots,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/architecture", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_tree(args: argparse.Namespace) -> None:
    body = {"workspace": _resolve_workspace(args.workspace), "suffix": args.suffix}
    result = asyncio.run(_post("/codebase/tree", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_read(args: argparse.Namespace) -> None:
    _symbol_handler(args, "/codebase/read-symbol")


def _handle_incoming(args: argparse.Namespace) -> None:
    body: dict = {
        "file": args.file,
        "symbol_name": args.symbol,
        "line": getattr(args, "line", None),
        "max": args.max,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/incoming-calls", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_outgoing(args: argparse.Namespace) -> None:
    body: dict = {
        "file": args.file,
        "symbol_name": args.symbol,
        "line": getattr(args, "line", None),
        "max": args.max,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
        "workspace_only": args.workspace_only,
    }
    result = asyncio.run(_post("/codebase/outgoing-calls", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_references(args: argparse.Namespace) -> None:
    body: dict = {
        "file": args.file,
        "symbol_name": args.symbol,
        "line": getattr(args, "line", None),
        "max": args.max,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/references", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_overview(args: argparse.Namespace) -> None:
    body = {
        "file": args.file,
        "depth": args.depth,
        "workspace": _resolve_workspace(args.workspace),
    }
    result = asyncio.run(_post("/codebase/overview", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_explain(args: argparse.Namespace) -> None:
    body: dict = {
        "file": args.file,
        "symbol_name": args.symbol,
        "line": getattr(args, "line", None),
        "max": args.max,
        "workspace": _resolve_workspace(getattr(args, "workspace", None)),
    }
    result = asyncio.run(_post("/codebase/explain", body))
    _print_json(result, pretty=args.pretty_format)


def _handle_search(args: argparse.Namespace) -> None:
    body: dict = {
        "query": args.query,
        "kind": args.kind,
        "limit": args.limit,
        "path": args.path,
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
        "max": args.max,
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
    """Add ``file``, ``--symbol``, ``--line``, ``--workspace`` arguments.

    ``--symbol`` is the name of a named code element — a function, class,
    method, variable, etc. — as reported by the language server
    (document symbols).  Names are case‑sensitive and must match exactly.
    When multiple symbols in the file have the same name, use ``--line``
    to pick the right one (the error response will list candidates).
    """
    parser.add_argument("file", type=str, help="Source file path.")
    parser.add_argument(
        "--symbol", "-s", type=str, required=True,
        help=(
            "Symbol name (function, class, method, etc.).  Case‑sensitive "
            "exact match.  Use --line to disambiguate when multiple symbols "
            "in the file share the same name."
        ),
    )
    parser.add_argument("--line", "-l", type=int, default=None,
                        help="Line number for disambiguation (1‑based).")
    parser.add_argument("--workspace", type=str,
                        help="Workspace root path (auto-detected if omitted).")


# ── Subparser registration ─────────────────────────────────────────────────────


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    cb_parser = subparsers.add_parser(
        "codebase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Codebase exploration — LSP + import‑graph analysis.",
        description=(
            "High‑level codebase exploration tools for AI agents.\n"
            "\n"
            "These tools combine two analysis engines:\n"
            "  • LSP (language server)  — precise symbol‑level queries.\n"
            "  • Import graph (tree‑sitter)  — file‑level dependency queries.\n"
            "\n"
            "Symbol‑based commands (e.g. read‑symbol, incoming‑calls) take a ``file`` "
            "and ``--symbol`` name.  When multiple symbols in the file share a name, "
            "use ``--line`` to disambiguate.  The response includes an ``error`` key "
            "with guidance if disambiguation is needed.\n"
            "\n"
            "Most tools return compact JSON.  Add --pretty-format for indented output (for human debugging only).  "
            "All file paths can be relative or absolute; the server auto‑detects the "
            "git workspace."
        ),
    )
    cb_sub = cb_parser.add_subparsers(title="commands", dest="codebase_command")
    cb_sub.required = True

    # ── tree ───────────────────────────────────────────────────────────
    tp = cb_sub.add_parser(
        "tree", parents=[_GLOBAL_OPTIONS],
        help="Recursive file/directory tree.",
        description=(
            "Build a recursive file/directory tree for the workspace.  "
            "Filesystem‑only (no LSP).  Hidden entries (``.git``, "
            "``node_modules``, ``__pycache__``, etc.) are excluded.  "
            "Optionally filter to files matching a suffix (e.g. ``.py``)."
        ),
    )
    tp.add_argument("--workspace", type=str)
    tp.add_argument("--suffix", type=str, default=None,
                    help="Only include files with this extension (e.g. '.py').")
    tp.set_defaults(func=_handle_tree)

    # ── read ───────────────────────────────────────────────────────────
    rdp = cb_sub.add_parser(
        "read-symbol", parents=[_GLOBAL_OPTIONS],
        help="Read the full body of a symbol.",
        description=(
            "Read the complete source body of a named symbol (function, class, "
            "method, etc.).  Returns the raw source text, truncated at 10 000 chars "
            "with a notice if exceeded.  Also includes any import statements "
            "inside the symbol's body range."
        ),
    )
    _add_symbol_args(rdp)
    rdp.set_defaults(func=_handle_read)

    # ── incoming-calls ─────────────────────────────────────────────────
    icp = cb_sub.add_parser(
        "incoming-calls", parents=[_GLOBAL_OPTIONS],
        help="Who calls this symbol? (LSP call hierarchy)",
        description=(
            "List all callers of a symbol, grouped by file.  Uses LSP call‑hierarchy "
            "protocol.  Each call site includes a source snippet (~200 chars).  "
            "When there are many sites, excess ones are compacted to bare line "
            "numbers (see --max)."
        ),
    )
    _add_symbol_args(icp)
    icp.add_argument("--max", type=int, default=50,
                      help="Max total call sites before compaction (default 50).")
    icp.set_defaults(func=_handle_incoming)

    # ── outgoing-calls ─────────────────────────────────────────────────
    ocp = cb_sub.add_parser(
        "outgoing-calls", parents=[_GLOBAL_OPTIONS],
        help="What does this symbol call? (LSP call hierarchy)",
        description=(
            "List everything a symbol calls, grouped by file.  Uses LSP call‑hierarchy.  "
            "By default, external calls (stdlib, site‑packages) are excluded.  "
            "Use --include-external to show them."
        ),
    )
    _add_symbol_args(ocp)
    ocp.add_argument("--max", type=int, default=50,
                      help="Max total call sites before compaction (default 50).")
    ocp.add_argument("--include-external", action="store_false", dest="workspace_only",
                      help="Include external (stdlib/site-packages) calls in output.")
    ocp.set_defaults(func=_handle_outgoing, workspace_only=True)

    # ── references ─────────────────────────────────────────────────────
    refp = cb_sub.add_parser(
        "references", parents=[_GLOBAL_OPTIONS],
        help="Where is this symbol used? (LSP references)",
        description=(
            "Find all usages of a symbol across the workspace.  Uses LSP "
            "``textDocument/references``.  Includes the definition site itself.  "
            "Call sites are grouped by file with source snippets."
        ),
    )
    _add_symbol_args(refp)
    refp.add_argument("--max", type=int, default=50,
                      help="Max total reference sites before compaction (default 50).")
    refp.set_defaults(func=_handle_references)

    # ── definition ──────────────────────────────────────────────────────
    defp = cb_sub.add_parser(
        "definition", parents=[_GLOBAL_OPTIONS],
        help="Go-to-definition with snippet (LSP).",
        description=(
            "Return the definition site AND type‑definition site for a "
            "symbol, with ~200‑char source snippets.  Uses LSP ``textDocument/"
            "definition`` + ``textDocument/typeDefinition``.  The type‑definition "
            "may be null for primitives or built‑ins."
        ),
    )
    _add_symbol_args(defp)
    defp.set_defaults(func=_handle_definition)

    # ── hover ───────────────────────────────────────────────────────────
    hvp = cb_sub.add_parser(
        "hover", parents=[_GLOBAL_OPTIONS],
        help="Signature + docstring (LSP hover — works on external libs).",
        description=(
            "Return the signature, type info, and docstring for a symbol "
            "as markdown.  Uses LSP ``textDocument/hover``.  Works on "
            "external library symbols (stdlib, installed packages), not "
            "just your own code."
        ),
    )
    _add_symbol_args(hvp)
    hvp.set_defaults(func=_handle_hover)

    # ── diagnostics ─────────────────────────────────────────────────────
    dgp = cb_sub.add_parser(
        "diagnostics", parents=[_GLOBAL_OPTIONS],
        help="LSP diagnostics (type errors, warnings, hints).",
        description=(
            "Return LSP diagnostics for a file, grouped by severity "
            "(error, warning, information, hint).  These are the language "
            "server's own analysis — type errors, undefined variables, etc.  "
            "Includes counts for each severity level.  Results are capped at "
            "--max (errors get priority)."
        ),
    )
    dgp.add_argument("file", type=str, help="Source file to check.")
    dgp.add_argument("--max", type=int, default=50,
                      help="Max diagnostics to return (default 50).")
    dgp.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    dgp.set_defaults(func=_handle_diagnostics)

    # ── overview ───────────────────────────────────────────────────────
    ovp = cb_sub.add_parser(
        "overview", parents=[_GLOBAL_OPTIONS],
        help="File table of contents — signatures, previews, ref counts.",
        description=(
            "Build a table of contents for a file.  Shows only callable/"
            "type‑defining symbols (functions, classes, methods, etc.) — "
            "not variables or constants.  For each symbol: signature line, "
            "body preview (up to 400 chars), and reference counts per file.  "
            "--depth controls how many nesting levels to show (0 = top‑level "
            "only, 1 = includes direct children, etc.).  Beyond that depth, "
            "children are collapsed to a count."
        ),
    )
    ovp.add_argument("file", type=str, help="Source file path.")
    ovp.add_argument("--depth", "-d", type=int, default=0,
                      help="Symbol tree depth (default 0 = top-level only).")
    ovp.add_argument("--workspace", type=str)
    ovp.set_defaults(func=_handle_overview)

    # ── explain ────────────────────────────────────────────────────────
    exp = cb_sub.add_parser(
        "explain", parents=[_GLOBAL_OPTIONS],
        help="Full symbol report (body + definition + callers + callees + refs).",
        description=(
            "Comprehensive symbol report combining: body text (truncated at "
            "6 000 chars), definition + type‑definition, incoming calls, "
            "outgoing calls, and references.  Each sub‑list gets an even "
            "share of the --max budget (e.g. --max 100 = ~33 each).  "
            "This is the most information‑dense single‑symbol query."
        ),
    )
    _add_symbol_args(exp)
    exp.add_argument("--max", type=int, default=100,
                      help="Total site budget across all sub-lists (divided evenly, default 100).")
    exp.set_defaults(func=_handle_explain)

    # ── search ──────────────────────────────────────────────────────────
    sp = cb_sub.add_parser(
        "search", parents=[_GLOBAL_OPTIONS],
        help="Search symbols across the workspace (LSP workspace/symbol).",
        description=(
            "Workspace‑wide symbol search via LSP ``workspace/symbol``.  "
            "This is a fuzzy name search against the language server's "
            "symbol index — NOT a text/grep search.  Results can be filtered "
            "by --kind (e.g. 'Class', 'Function') and --path (substring match "
            "against the file path).  Capped at --limit results."
        ),
    )
    sp.add_argument("query", type=str, help="Symbol name search query.")
    sp.add_argument("--kind", type=str, default=None,
                    help="Filter by symbol kind (e.g. 'Class', 'Function'). Case‑insensitive.")
    sp.add_argument("--limit", type=int, default=40,
                    help="Max results (default 40).")
    sp.add_argument("--path", type=str, default=None,
                     help="Only show results whose file path contains this substring.")
    sp.add_argument("--workspace", type=str)
    sp.set_defaults(func=_handle_search)

    # ── impact ──────────────────────────────────────────────────────────
    imp = cb_sub.add_parser(
        "impact", parents=[_GLOBAL_OPTIONS],
        help="Change impact: LSP callers + file‑level import blast radius.",
        description=(
            "Two‑view change impact analysis:\n"
            "  • Symbol level (LSP) — incoming calls, outgoing calls, references.  "
            "Shows exactly who calls/uses the changed symbol.\n"
            "  • File level (import graph) — all files that transitively import "
            "the changed file, up to --depth hops.  Catches dependents even if "
            "they don't directly use the changed symbol.\n"
            "Each symbol‑level sub‑list gets an even share of the --max budget."
        ),
    )
    _add_symbol_args(imp)
    imp.add_argument("--depth", "-d", type=int, default=10,
                      help="Import hops for file-level blast radius (default 10).")
    imp.add_argument("--max", type=int, default=100,
                      help="Total site budget across sub-lists (divided evenly, default 100).")
    imp.set_defaults(func=_handle_impact)

    # ── architecture ─────────────────────────────────────────────────────
    arch = cb_sub.add_parser(
        "architecture", parents=[_GLOBAL_OPTIONS],
        help="Repo architecture: import graph, entry points, hotspots.",
        description=(
            "Generate an architecture report from the import graph (no LSP).  "
            "Includes:\n"
            "  • structure — nested directory‑level import graph showing what each "
            "dir imports and is imported by.\n"
            "  • entry_points — files with zero transitive dependents (not tests).\n"
            "  • hotspots — files ranked by transitive dependent count.\n"
            "  • summary — total files/directories indexed.\n"
            "File discovery uses ``git ls-files`` (respects .gitignore)."
        ),
    )
    arch.add_argument("--hotspots", type=int, default=20,
                       help="Max hotspots to return (default 20).")
    arch.add_argument("--workspace", type=str, default=None,
                       help="Workspace root path (auto-detected if omitted).")
    arch.set_defaults(func=_handle_architecture)

    # ── import-dependents ───────────────────────────────────────────────
    idp = cb_sub.add_parser(
        "import-dependents", parents=[_GLOBAL_OPTIONS],
        help="Files that import this file (import graph — no LSP).",
        description=(
            "Return files that (transitively) import the given file, using the "
            "import graph.  Each result shows the file path and how many import "
            "hops away (--depth).  --depth=1 returns direct importers only."
        ),
    )
    idp.add_argument("file", type=str, help="Source file to check.")
    idp.add_argument("--depth", "-d", type=int, default=1,
                      help="How many import hops to follow (1 = direct only, 0 = unlimited).")
    idp.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    idp.set_defaults(func=_handle_import_dependents)

    # ── import-dependencies ─────────────────────────────────────────────
    idd = cb_sub.add_parser(
        "import-dependencies", parents=[_GLOBAL_OPTIONS],
        help="What files does this file import? (import graph — no LSP).",
        description=(
            "Return the files that this file directly imports, using the "
            "import graph.  Only direct imports — no transitive hops."
        ),
    )
    idd.add_argument("file", type=str, help="Source file to check.")
    idd.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    idd.set_defaults(func=_handle_import_dependencies)

    # ── affected-tests ──────────────────────────────────────────────────
    atp = cb_sub.add_parser(
        "affected-tests", parents=[_GLOBAL_OPTIONS],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Which test files are affected if this file changes?",
        description="Find test files affected by a change via the import graph.",
        epilog=(
            "Limitation: only finds tests that import the target file "
            "(or its transitive dependents up to --depth).  E2e / integration "
            "tests that exercise the target via HTTP, CLI subprocess, or "
            "other non-import paths will NOT be found — run those separately."
        ),
    )
    atp.add_argument("file", type=str,
                      help="File whose changes you want to check (e.g. the file you edited).")
    atp.add_argument("--depth", "-d", type=int, default=10,
                      help="How many import hops to follow (default 10).")
    atp.add_argument("--workspace", type=str,
                      help="Workspace root path (auto-detected if omitted).")
    atp.set_defaults(func=_handle_affected_tests)
