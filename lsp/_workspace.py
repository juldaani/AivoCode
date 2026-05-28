"""Git-based workspace (repo root) detection.

What this module provides
- detect_workspace: resolve the git repo root for a given file path.

Why this exists
- LSP servers need a workspace root for project-wide context (indexing,
  configuration). The CLI (and future MCP/REST endpoints) needs a consistent way
  to find it. Git is the expected VCS for aivocode users.

How it works
- Walks up from the file's parent directory, running
  ``git rev-parse --show-toplevel`` at each level until it finds a git
  worktree. The file itself must exist within some ancestor that is a git
  repository.

See Also
- file_watcher.gitignore: uses the same ``git`` subprocess pattern for
  gitignore checks.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def detect_workspace(file_or_dir: Path) -> Path:
    """Find the git repository root for *file_or_dir*.

    Walks up from the given path (or its parent, if the path points to a file)
    calling ``git rev-parse --show-toplevel`` at each candidate directory
    until a git worktree is found.  Accepts both files and directories,
    so callers can pass ``Path.cwd()`` directly.

    Parameters
    ----------
    file_or_dir : Path
        A file or directory path (relative or absolute). Relative paths are
        resolved against the current working directory before walking.

    Returns
    -------
    Path
        Absolute path to the git repository root.

    Raises
    ------
    RuntimeError
        If git is not installed, or no git repository is found in any
        ancestor of *file_or_dir*.
    """
    if not shutil.which("git"):
        raise RuntimeError(
            "git is not installed or not on PATH. "
            "aivocode lsp requires git to detect the workspace root. "
            "Use --workspace to specify the workspace manually."
        )

    # Resolve to absolute.
    resolved = (
        file_or_dir.resolve()
        if file_or_dir.is_absolute()
        else Path.cwd() / file_or_dir
    )
    target_abs = resolved.resolve()

    # git -C expects a directory.  If the path is a file (or doesn't exist),
    # start walking from its parent.  If it's a directory, start there.
    if target_abs.is_dir():
        current = target_abs
    else:
        current = target_abs.parent
    while True:
        try:
            proc = subprocess.run(
                ["git", "-C", str(current), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                root = Path(proc.stdout.strip())
                if root.is_absolute():
                    return root
                # --show-toplevel should always be absolute, but guard.
                return (current / root).resolve()
        except (OSError, subprocess.SubprocessError):
            pass  # current dir may not be a valid git dir; walk up.

        parent = current.parent
        if parent == current:
            # Reached filesystem root — no git repo found.
            raise RuntimeError(
                f"File '{file_path}' is not inside a git repository. "
                "Use --workspace to specify the workspace manually."
            )
        current = parent
