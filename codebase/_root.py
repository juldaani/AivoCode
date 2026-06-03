"""List top-level directories in a workspace.

Why this exists
- The ``codebase root`` command is the simplest entry-point for the
  ``codebase`` package — it proves the CLI → REST → package pipeline
  works end-to-end without depending on LSP.
"""

from __future__ import annotations

import os
from pathlib import Path


def _root_dirs(workspace: Path | None = None) -> list[str]:
    """Return sorted names of non-hidden directories at the workspace root.

    Parameters
    ----------
    workspace : Path or None
        Workspace root directory.  Defaults to ``Path.cwd()``.

    Returns
    -------
    list[str]
        Sorted directory basenames, excluding hidden directories
        (names starting with ``.``).
    """
    ws = workspace or Path.cwd()
    if not ws.is_dir():
        raise NotADirectoryError(f"Not a directory: {ws}")
    return sorted(
        name
        for name in os.listdir(ws)
        if (ws / name).is_dir() and not name.startswith(".")
    )
