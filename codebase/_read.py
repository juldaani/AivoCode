"""Read the full body text of a named symbol.

Why this exists
- Agents need to read the source code of a specific function or class
  without pulling in the entire file.  ``read_symbol`` resolves the name,
  reads the body range, and returns just that text.
"""

from __future__ import annotations

import ast
from pathlib import Path

from codebase._resolve import ResolvedSymbol, relativize
from codebase._snippet import read_range


# ── Import extraction (Python-only for now, extensible via *language*) ───────


def _extract_imports(file_path: str | Path, language: str = "python") -> list[dict]:
    """Extract import statements from a source file.

    Parameters
    ----------
    file_path : str or Path
        Path to the source file.
    language : str
        Language identifier for future extension (TypeScript, Rust, etc.).
        Currently only ``"python"`` is supported.

    Returns
    -------
    list[dict]
        Each entry has ``line`` (1-indexed) and ``statement`` (raw source text).
    """
    if language == "python":
        return _extract_imports_python(file_path)
    return []


def _extract_imports_python(file_path: str | Path) -> list[dict]:
    """Extract Python import statements using ``ast.parse()``."""
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports: list[dict] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                imports.append({"line": node.lineno, "statement": segment})

    return imports


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
        "file": relativize(file_path, ws),
        "imports": _extract_imports(file_path),
    }
