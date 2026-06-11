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
    """Read the full body text of *symbol_name* in *file_path*."""
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
    """List incoming call hierarchy for *symbol_name*."""
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
    command: str = "outgoing-calls",
) -> dict:
    """List outgoing call hierarchy for *symbol_name*."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "file": relativize(file_path, ws_rel),
        "outgoing_calls": await _outgoing_calls(sym, file_path, workspace),
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
    """List all reference sites for *symbol_name* (includes definition)."""
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
    """Build a file overview ToC with signatures and reference counts."""
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
    """Full symbol report: body, definers, callers, callees, references."""
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
