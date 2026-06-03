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
- get_repo_root_dirs : list top-level directories in a workspace.

See Also
- lsp/  — raw LSP protocol layer (hover, definition, references, etc.)
"""

from __future__ import annotations

from pathlib import Path

from codebase._root import _root_dirs


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
