"""Read source file snippets at specific lines or ranges.

Why this exists
- Multiple ``codebase`` commands need to read source text at LSP-reported
  positions without pulling in the entire file.  This module centralises
  that logic so every command uses the same 1-indexed, newline-joined
  contract.

How to use
    from codebase._snippet import read_snippet, read_range
    line = read_snippet(file_path, 291)
    body = read_range(file_path, 100, 500)
"""

from __future__ import annotations

from pathlib import Path


def read_snippet(file_path: str | Path, line: int) -> str:
    """Read a single line of source code (1-indexed).

    Returns the line with trailing whitespace stripped.  If *line* is
    out of range an empty string is returned.
    """
    path = Path(file_path)
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    idx = line - 1  # 1-indexed → 0-indexed
    if 0 <= idx < len(lines):
        return lines[idx].rstrip()
    return ""


def read_range(file_path: str | Path, start_line: int, end_line: int) -> str:
    """Read a range of lines from a file (1-indexed, inclusive).

    Returns the selected lines joined by newlines.  Lines are trimmed of
    trailing whitespace.  Out-of-range lines are silently omitted.
    """
    path = Path(file_path)
    if not path.is_file() or start_line > end_line:
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)
    if start_idx >= end_idx:
        return ""
    return "\n".join(line.rstrip() for line in lines[start_idx:end_idx])
