"""Read the full body text of a named symbol.

Why this exists
- Agents need to read the source code of a specific function or class
  without pulling in the entire file.  ``read_symbol`` resolves the name,
  reads the body range, and returns just that text.
"""

from __future__ import annotations

from pathlib import Path

from codebase._resolve import ResolvedSymbol, relativize
from codebase._snippet import read_range


# ── Import extraction ─────────────────────────────────────────────────────────


def _extract_imports(
    file_path: str | Path,
    language: str = "python",
    *,
    top_level_only: bool = True,
) -> list[dict]:
    """Extract import statements from a source file using tree-sitter.

    Delegates to the registered ``LanguageHandler`` for *language*.
    Unsupported languages return ``[]``.

    Parameters
    ----------
    file_path : str or Path
        Path to the source file.
    language : str
        Language identifier (``"python"``, ``"typescript"``, etc.).
    top_level_only : bool
        When ``True`` (default), only top-level (module-scope) imports are
        returned.  When ``False``, all imports are returned including lazy
        imports inside function bodies — each gets ``lazy: True``.

    Returns
    -------
    list[dict]
        Each entry has ``line`` (1-indexed), ``statement`` (raw source text),
        and ``lazy`` (``False`` for top-level, ``True`` for nested).
    """
    from codebase._lang_handlers import get_handler_by_language

    handler = get_handler_by_language(language)
    if handler is None:
        return []

    raw_imports = handler.extract_imports(Path(file_path))
    result: list[dict] = []
    for ri in raw_imports:
        if top_level_only and ri.lazy:
            continue
        result.append({
            "line": ri.line,
            "statement": ri.statement,
            "lazy": ri.lazy,
        })
    return result


# ── Symbol reader ──────────────────────────────────────────────────────────────


def _read_symbol(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict:
    """Read the full body of *symbol* from *file_path*.

    Returns a dict with ``symbol``, ``body``, ``range_line_char``,
    ``file``, and ``imports`` (all import statements in the file).
    """
    body = read_range(file_path, symbol.range_start[0], symbol.range_end[0])
    ws = workspace or Path.cwd()
    return {
        "symbol": symbol.name,
        "kind": symbol.kind,
        "body": body,
        "range_line_char": {
            "start": list(symbol.range_start),
            "end": list(symbol.range_end),
        },
        "imports": _extract_imports(file_path, top_level_only=False),
    }
