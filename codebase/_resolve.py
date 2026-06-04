"""Resolve a symbol name to its LSP position within a file.

Why this exists
- Every symbol-name-based ``codebase`` command needs to turn a name like
  ``"Greeter"`` into a ``selection_range`` point before calling the
  relevant LSP method.  This module centralises document-symbol lookup,
  tree flattening, exact-name matching, and disambiguation so commands
  don't duplicate that logic.

How to use
    from codebase._resolve import resolve_symbol, ResolvedSymbol
    sym = resolve_symbol("mock_pkg/utils.py", "Greeter")
    # sym.line → 43, sym.kind → "Class"
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from lsp import query_document_symbols


# ── Errors ─────────────────────────────────────────────────────────────────────


class SymbolNotFoundError(LookupError):
    """Raised when *symbol_name* does not match any document symbol."""


class AmbiguousSymbolError(LookupError):
    """Raised when *symbol_name* matches multiple symbols and no *line* is given.

    Attributes
    ----------
    candidates : list[dict]
        Each candidate is ``{"symbol": ["kind", "name"], "line": N}``.
    """

    def __init__(self, candidates: list[dict], file_name: str, symbol_name: str):
        self.candidates = candidates
        self.file_name = file_name
        self.symbol_name = symbol_name
        super().__init__(
            f"Ambiguous symbol '{symbol_name}' matches {len(candidates)} symbols "
            f"in {file_name}. Use --line to disambiguate."
        )


# ── Resolved symbol ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResolvedSymbol:
    """A document symbol that has been looked up and resolved.

    All position values are 1-indexed (already normalised by the daemon).
    """

    name: str
    kind: str
    line: int  # selection_range.start.line
    character: int  # selection_range.start.character
    range_start: tuple[int, int]  # (line, character)
    range_end: tuple[int, int]  # (line, character)
    children: list[dict] = field(default_factory=list)


# ── Tree helpers ───────────────────────────────────────────────────────────────


def _deep_flatten(symbols: list[dict]) -> list[dict]:
    """Recursively flatten a symbol tree into a single-level list.

    Every node in the hierarchy (classes, methods, variables, etc.) is
    collected into one flat list so exact-name matching can find symbols
    at any nesting depth.  Children lists are preserved on each entry.
    """
    flat: list[dict] = []
    for sym in symbols:
        entry: dict = _symbol_to_entry(sym)
        children = sym.get("children") or []
        entry["children"] = _deep_flatten(children) if children else None
        flat.append(entry)
        if children:
            flat.extend(entry["children"])
    return flat


def _symbol_tree_by_depth(symbols: list[dict], depth: int, current_depth: int = 0) -> list[dict]:
    """Walk the symbol tree to *depth*, collecting all visible nodes.

    At *depth*, children are set to ``null`` (leaf marker) rather than
    omitted, so consumers can distinguish "has no children" from
    "children were not requested."  Used by ``overview``, not by symbol
    resolution.
    """
    flat: list[dict] = []
    for sym in symbols:
        entry = _symbol_to_entry(sym)
        children = sym.get("children") or []
        if current_depth < depth and children:
            entry["children"] = _symbol_tree_by_depth(children, depth, current_depth + 1)
        else:
            entry["children"] = None
        flat.append(entry)
    return flat


def _symbol_to_entry(sym: dict) -> dict:
    """Convert a raw document symbol dict to our internal entry shape."""
    return {
        "name": sym.get("name"),
        "kind": sym.get("kind"),
        "line": sym.get("selection_range", {}).get("start", {}).get("line"),
        "character": sym.get("selection_range", {}).get("start", {}).get("character"),
        "range_start": (
            sym["range"]["start"]["line"],
            sym["range"]["start"]["character"],
        ),
        "range_end": (
            sym["range"]["end"]["line"],
            sym["range"]["end"]["character"],
        ),
    }


def _find_by_name(
    flat_symbols: list[dict],
    name: str,
) -> list[dict]:
    """Return all entries whose ``name`` matches exactly (case-sensitive)."""
    return [s for s in flat_symbols if s.get("name") == name]


def _find_by_name_and_line(
    flat_symbols: list[dict],
    name: str,
    line: int,
) -> dict | None:
    """Return the entry matching *name* at *line*, or ``None``."""
    for s in flat_symbols:
        if s.get("name") == name and s.get("line") == line:
            return s
    return None


# ── Public resolver ────────────────────────────────────────────────────────────


async def resolve_symbol(
    file_path: str | Path,
    symbol_name: str,
    line: int | None = None,
    workspace: Path | None = None,
) -> ResolvedSymbol:
    """Resolve *symbol_name* to a position in *file_path*.

    Parameters
    ----------
    file_path : str or Path
        The source file to query.
    symbol_name : str
        Exact (case-sensitive) symbol name to look up.
    line : int or None
        1-indexed line for disambiguation.  Required when *symbol_name*
        matches more than one symbol.
    workspace : Path or None
        Workspace root for detect_workspace.  ``None`` means auto-detect.

    Returns
    -------
    ResolvedSymbol

    Raises
    ------
    SymbolNotFoundError
        No symbol with that name, or the *line* hint does not match.
    AmbiguousSymbolError
        Multiple matches and no *line* was provided.
    """
    result = await query_document_symbols(Path(file_path), workspace=workspace)
    if "error" in result:
        raise SymbolNotFoundError(
            f"Symbol '{symbol_name}' not found in {file_path}: {result['error']}"
        )

    symbols: list[dict] = result.get("symbols", [])
    flat = _deep_flatten(symbols)

    name_file = str(Path(file_path).name)
    matches = _find_by_name(flat, symbol_name)

    if not matches:
        raise SymbolNotFoundError(
            f"Symbol '{symbol_name}' not found in {name_file}"
        )

    if len(matches) == 1:
        s = matches[0]
    elif line is not None:
        s = _find_by_name_and_line(flat, symbol_name, line)
        if s is None:
            raise SymbolNotFoundError(
                f"Symbol '{symbol_name}' not found at line {line} in {name_file}"
            )
    else:
        candidates: list[dict] = [
            {
                "symbol": [m["kind"], m["name"]],
                "line": m["line"],
            }
            for m in matches
        ]
        raise AmbiguousSymbolError(candidates, name_file, symbol_name)

    return ResolvedSymbol(
        name=s["name"],
        kind=s["kind"],
        line=s["line"],
        character=s["character"],
        range_start=s["range_start"],
        range_end=s["range_end"],
        children=s.get("children", []),
    )
