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
) -> dict:
    """Extract import statements, grouped by module-level vs lazy.

    Returns ``{"module": [...], "lazy": [...]}`` where each entry has
    ``{line, statement}``.  When *top_level_only* is ``True``, the
    ``"lazy"`` group is always empty.
    """
    from codebase._lang_handlers import get_handler_by_language

    handler = get_handler_by_language(language)
    if handler is None:
        return {"module": [], "lazy": []}

    raw_imports = handler.extract_imports(Path(file_path))
    module: list[dict] = []
    lazy: list[dict] = []
    for ri in raw_imports:
        entry = {"line": ri.line, "statement": ri.statement}
        if ri.lazy:
            if not top_level_only:
                lazy.append(entry)
        else:
            module.append(entry)
    return {"module": module, "lazy": lazy}


# ── Symbol reader ──────────────────────────────────────────────────────────────


# Threshold for truncating large symbol bodies (e.g. a class with many methods).
# Agents have a finite context window; returning 10k+ chars of a single symbol
# is rarely useful and eats into space for other tools.
_MAX_SYMBOL_CHARS = 10_000


def _read_symbol(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict:
    """Read the body of *symbol* from *file_path*.

    Returns a dict with ``symbol``, ``kind``, ``body``,
    ``range_line_char``, ``imports``, and ``truncated``.

    Bodies longer than ``_MAX_SYMBOL_CHARS`` (10 000 characters) are
    truncated to keep agent context manageable.  The ``truncated`` key
    is ``True`` when the returned body was cut; the truncation notice
    at the end of the body text reports how many characters were omitted.

    *imports* includes all file-level (module) imports plus only those
    lazy imports whose line falls **within** the symbol's own body
    range — lazy imports from other symbols in the same file are excluded.
    """
    body = read_range(file_path, symbol.range_start[0], symbol.range_end[0])
    ws = workspace or Path.cwd()

    truncated = False
    if len(body) > _MAX_SYMBOL_CHARS:
        remaining = len(body) - _MAX_SYMBOL_CHARS
        body = (
            body[:_MAX_SYMBOL_CHARS]
            + f"\n... [truncated at {_MAX_SYMBOL_CHARS} chars,"
            f" {remaining} more chars not shown]"
        )
        truncated = True

    all_imports = _extract_imports(file_path, top_level_only=False)
    # Keep only lazy imports whose line is inside this symbol's body.
    symbol_start = symbol.range_start[0]
    symbol_end = symbol.range_end[0]
    all_imports["lazy"] = [
        imp for imp in all_imports["lazy"]
        if symbol_start <= imp["line"] <= symbol_end
    ]

    return {
        "symbol": symbol.name,
        "kind": symbol.kind,
        "body": body,
        "truncated": truncated,
        "range_line_char": {
            "start": list(symbol.range_start),
            "end": list(symbol.range_end),
        },
        "imports": all_imports,
    }
