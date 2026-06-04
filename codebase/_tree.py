"""Build a recursive file/directory tree for a workspace.

Why this exists
- The first thing an agent needs when entering a repo is a structural
  map.  ``repo_root`` replaces manual ``ls`` / ``find`` / ``glob`` calls
  with a single, compact list-based tree.

How to use
    from codebase._tree import _build_tree
    tree = _build_tree(Path("/workspaces/my-project"))
    # → [["api_server/", [["routes/", ["lsp.py"]]], "cli/", ["main.py"]]
"""

from __future__ import annotations

import os
from pathlib import Path

# Directories and files to skip during tree construction.
_SKIP_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".aivocode",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".eggs",
        "*.egg-info",
        "dist",
        "build",
        ".DS_Store",
    }
)


def _build_tree(
    workspace: Path,
    suffix: str | None = None,
) -> list:
    """Build a recursive repo tree.

    Parameters
    ----------
    workspace : Path
        Absolute path to the workspace root.
    suffix : str or None
        When set (e.g. ``".py"``), only files matching this extension
        are included.  Directories without matching descendants are
        pruned.

    Returns
    -------
    list
        Nested structure::

            ["dirname/", [...]]
            "filename"
    """
    return _walk(workspace, suffix)


def _walk(root: Path, suffix: str | None) -> list:
    entries: list = []
    try:
        names = sorted(
            e.name
            for e in os.scandir(root)
            if not _is_skipped(e.name)
        )
    except (OSError, PermissionError):
        return entries

    for name in names:
        full = root / name
        if full.is_dir():
            children = _walk(full, suffix)
            if suffix is None or children:
                entries.append([name + "/", children])
        elif full.is_file():
            if suffix is None or name.endswith(suffix):
                entries.append(name)

    return entries


def _is_skipped(name: str) -> bool:
    if name.startswith("."):
        return True
    if name in _SKIP_NAMES:
        return True
    # Also skip glob-like patterns from _SKIP_NAMES.
    for pattern in _SKIP_NAMES:
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True
    return False
