"""Codebase exploration tools — agent-facing derived intelligence on top of LSP.

What this module provides
- High-level, single-call tools for codebase exploration designed for AI
  agents.  Compose multiple LSP primitives into one response so agents
  spend fewer round-trips understanding code.

Why this exists
- Raw LSP tools expose protocol-level data (URIs, ranges, raw kinds).
  Agents need semantic answers (what does this function do? who calls
  it? what would break if I changed it?).  This module composes the
  low-level LSP calls into high-level "understanding primitives."

How to use
    from codebase import get_repo_tree
    tree = get_repo_tree(Path("/workspaces/my-project"))
    # → {"root": [...], "workspace": "...", "query": {...}}

Public API
----------
- get_repo_tree : build a recursive ``{"dirname/": [...]}`` tree.
- read_symbol : read the full body of a symbol.
- incoming_calls / outgoing_calls : call hierarchy.
- find_references : where is this symbol used?
- file_overview : file ToC with signatures and reference counts.
- explain_symbol : full symbol report (body, callers, callees, references).
- search_symbols : workspace-wide symbol search.
- analyze_impact : change impact (incoming + outgoing + references).
- import_dependents : who (transitively) imports this file? (zero LSP)
- import_dependencies : what does this file import? (zero LSP)
- affected_test_files : which test files are affected? (zero LSP)

See Also
- lsp/  — raw LSP protocol layer (hover, definition, references, etc.)
"""

from __future__ import annotations

from pathlib import Path

from codebase._analyze import (
    _explain,
    _impact,
    _incoming_calls,
    _outgoing_calls,
    _overview,
    _references,
    _search,
)
from codebase._read import _read_symbol
from codebase._resolve import ResolvedSymbol, relativize, resolve_symbol
from codebase._tree import _build_tree


# ── Query helper ───────────────────────────────────────────────────────────────


def _make_query(command: str, **kwargs: object) -> dict:
    """Build a query metadata block, omitting ``None`` values."""
    return {"command": command, **{k: v for k, v in kwargs.items() if v is not None}}


def _format_info(info: dict) -> str | None:
    """Convert graph info dict to an optional human-readable status string.

    Returns ``None`` when there is nothing noteworthy to report (no errors,
    no skipped files).  Otherwise returns a compact status string like
    ``"103 files indexed, 2 errors"``.
    """
    indexed = info.get("files_indexed", 0)
    skipped = info.get("files_skipped", 0)
    errors = info.get("errors", [])

    has_news = skipped > 0 or errors
    if not has_news:
        return None

    parts = [f"{indexed} files indexed"]
    if skipped:
        parts.append(f"{skipped} skipped")
    if errors:
        parts.append(f"{len(errors)} errors")

    return ", ".join(parts)


def get_repo_tree(
    workspace: Path | None = None,
    *,
    suffix: str | None = None,
) -> dict:
    """Build a recursive file/directory tree for the workspace.

    Returns a nested structure where each entry is either:

    - ``"filename"`` for files, or
    - ``{"dirname/": [...children]}`` for directories.

    Hidden entries (``.git``, ``__pycache__``, etc.) are excluded.

    Parameters
    ----------
    workspace : Path or None
        Absolute path to the workspace root.  Defaults to ``Path.cwd()``.
    suffix : str or None
        When set (e.g. ``".py"``), only files with that extension are
        included.  Empty directories are pruned.
    """
    ws = workspace or Path.cwd()
    return {
        "root": _build_tree(ws, suffix=suffix),
        "workspace": str(ws),
        "query": _make_query("tree", suffix=suffix),
    }


async def read_symbol(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "read",
) -> dict:
    """Read the full body text of *symbol_name* in *file_path*.

    Returns a dict with ``symbol``, ``kind``, ``body``, ``range_line_char``,
    ``file``, ``imports``, and ``query``.  The ``imports`` list contains all
    import statements in the file, including lazy imports inside function
    bodies.  Each entry has ``{line, statement, lazy}`` — ``lazy`` is
    ``True`` for imports nested inside a ``def``/``class`` body.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = _read_symbol(sym, file_path, workspace)
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    return result


async def incoming_calls(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "incoming-calls",
) -> dict:
    """List incoming call hierarchy for *symbol_name*.

    Returns a dict with ``symbol``, ``kind``, ``file``, ``incoming_calls``,
    and ``query``.  Each call entry includes a ``locality`` field
    (``"same_file"``, ``"cross_file"``, or ``"external"``)."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "file": relativize(file_path, ws_rel),
        "incoming_calls": await _incoming_calls(sym, file_path, workspace),
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    return result


async def outgoing_calls(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    workspace_only: bool = True,
    command: str = "outgoing-calls",
) -> dict:
    """List outgoing call hierarchy for *symbol_name*.

    By default (``workspace_only=True``), external calls (stdlib,
    site-packages) are excluded.  Pass ``workspace_only=False`` to include
    them.  Each call entry has a ``locality`` field: ``"same_file"``,
    ``"cross_file"``, or ``"external"``.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "file": relativize(file_path, ws_rel),
        "outgoing_calls": await _outgoing_calls(
            sym, file_path, workspace, workspace_only=workspace_only,
        ),
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    return result


async def find_references(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "references",
) -> dict:
    """List all reference sites for *symbol_name* (includes definition).

    Each reference entry includes a ``locality`` field
    (``"same_file"``, ``"cross_file"``, or ``"external"``)."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "file": relativize(file_path, ws_rel),
        "references": await _references(sym, file_path, workspace),
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    return result


async def file_overview(
    file_path: str | Path,
    *,
    depth: int = 0,
    workspace: Path | None = None,
    command: str = "overview",
) -> dict:
    """Build a file overview ToC with signatures and reference counts.

    Returns ``file``, ``imports`` (top-level only, each with
    ``{line, statement, lazy}``), ``symbols``, ``symbol_count``,
    ``depth``, and ``query``."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await _overview(file_path, depth=depth, workspace=workspace)
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), depth=depth,
    )
    return result


async def explain_symbol(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "explain",
) -> dict:
    """Full symbol report: body, definers, callers, callees, references.

    Body text is truncated at 6000 characters (with a truncation note)
    to keep responses agent-friendly.  Call and reference entries include
    a ``locality`` field."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = await _explain(sym, file_path, workspace)
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    return result


async def search_symbols(
    query: str,
    *,
    kind: str | None = None,
    limit: int = 50,
    workspace: Path | None = None,
    command: str = "search",
) -> dict:
    """Search the workspace for symbols matching *query*."""
    result = await _search(query, kind=kind, limit=limit, workspace=workspace)
    result["query"] = _make_query(command, arg=query, kind=kind, limit=limit)
    return result


async def analyze_impact(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "impact",
) -> dict:
    """Change impact: incoming calls + outgoing calls + references."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = await _impact(sym, file_path, workspace)
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    return result


# ── Import-graph tools ─────────────────────────────────────────────────────────


async def import_dependents(
    file_path: str | Path,
    *,
    depth: int = 1,
    workspace: Path | None = None,
    command: str = "import-dependents",
) -> dict:
    """Return files that (transitively) import *file_path*.

    Uses the import graph maintained by the daemon — zero LSP queries.
    Each entry includes ``file`` and ``depth``.
    """
    from lsp import detect_workspace
    from lsp import query_import_dependents

    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await query_import_dependents(
        Path(file_path), depth=depth, workspace=workspace,
    )
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), depth=depth,
    )
    # Polish: remove duplicate depth, format info
    result.pop("depth", None)
    info = _format_info(result.pop("info", {}))
    if info is not None:
        result["info"] = info
    return result


async def import_dependencies(
    file_path: str | Path,
    *,
    workspace: Path | None = None,
    command: str = "import-dependencies",
) -> dict:
    """Return the files that *file_path* directly imports."""
    from lsp import detect_workspace
    from lsp import query_import_dependencies

    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await query_import_dependencies(
        Path(file_path), workspace=workspace,
    )
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
    )
    # Polish: format info
    info = _format_info(result.pop("info", {}))
    if info is not None:
        result["info"] = info
    return result


async def affected_test_files(
    file_path: str | Path,
    *,
    depth: int = 10,
    workspace: Path | None = None,
    command: str = "affected-tests",
) -> dict:
    """Return test files that (transitively) import *file_path*."""
    from lsp import detect_workspace
    from lsp import query_import_affected_tests

    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await query_import_affected_tests(
        Path(file_path), depth=depth, workspace=workspace,
    )
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), depth=depth,
    )
    # Polish: remove duplicate depth, format info
    result.pop("depth", None)
    info = _format_info(result.pop("info", {}))
    if info is not None:
        result["info"] = info
    return result
