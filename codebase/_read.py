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


def _read_symbol(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict:
    """Read the full body of *symbol* from *file_path*.

    Returns a dict with ``symbol``, ``body``, ``range_line_char``, and ``file``.
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
    }
