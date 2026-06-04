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
    from codebase import get_repo_root_dirs
    dirs = get_repo_root_dirs(Path("/workspaces/my-project"))
    # → ["api_server", "cli", "lsp", "tests"]

Public API
----------
- get_repo_tree : build a recursive ``["dirname/", [...]]`` tree.
- get_repo_root_dirs : list top-level directories in a workspace.

See Also
- lsp/  — raw LSP protocol layer (hover, definition, references, etc.)
"""

from __future__ import annotations

from pathlib import Path

from codebase._analyze import (
    _explain,
    _incoming_calls,
    _outgoing_calls,
    _overview,
    _references,
)
from codebase._read import _read_symbol
from codebase._resolve import ResolvedSymbol, resolve_symbol
from codebase._root import _root_dirs
from codebase._tree import _build_tree


def get_repo_root_dirs(workspace: Path | None = None) -> list[str]:
    """Return sorted list of top-level directory names in the workspace.

    Hidden directories (starting with ``.``) are excluded.

    Parameters
    ----------
    workspace : Path or None
        Absolute path to the workspace root.  When ``None``, uses the
        current working directory.

    Returns
    -------
    list[str]
        Sorted directory names (not paths).  e.g. ``["cli", "lsp", "tests"]``.
    """
    return _root_dirs(workspace)


def get_repo_tree(
    workspace: Path | None = None,
    *,
    suffix: str | None = None,
) -> list:
    """Build a recursive file/directory tree for the workspace.

    Returns a nested list structure where each entry is either:

    - ``"filename"`` for files, or
    - ``["dirname/", [...children]]`` for directories.

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
    return _build_tree(ws, suffix=suffix)


async def read_symbol(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
) -> dict:
    """Read the full body text of *symbol_name* in *file_path*."""
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    return _read_symbol(sym, file_path)


async def incoming_calls(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
) -> dict:
    """List incoming call hierarchy for *symbol_name*."""
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    return {
        "symbol": [sym.kind, sym.name],
        "file": str(Path(file_path).resolve()),
        "incoming_calls": await _incoming_calls(sym, file_path, workspace),
    }


async def outgoing_calls(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
) -> dict:
    """List outgoing call hierarchy for *symbol_name*."""
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    return {
        "symbol": [sym.kind, sym.name],
        "file": str(Path(file_path).resolve()),
        "outgoing_calls": await _outgoing_calls(sym, file_path, workspace),
    }


async def find_references(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
) -> dict:
    """List all reference sites for *symbol_name* (includes definition)."""
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    return {
        "symbol": [sym.kind, sym.name],
        "file": str(Path(file_path).resolve()),
        "references": await _references(sym, file_path, workspace),
    }


async def file_overview(
    file_path: str | Path,
    *,
    depth: int = 0,
    workspace: Path | None = None,
) -> dict:
    """Build a file overview ToC with signatures and reference counts."""
    return await _overview(file_path, depth=depth, workspace=workspace)


async def explain_symbol(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
) -> dict:
    """Full symbol report: body, definers, callers, callees, references."""
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    return await _explain(sym, file_path, workspace)
