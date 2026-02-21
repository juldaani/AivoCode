"""Gitignore-based filtering using the `git` command.

We intentionally avoid extra dependencies and rely on:
- `git -C <root> check-ignore --stdin -z` for batch ignore checks

This module is designed to be used after watchfiles yields a batch.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class GitignoreStatus:
    enabled: bool
    git_available: bool
    root_ok: dict[Path, bool]


def git_available() -> bool:
    return shutil.which("git") is not None


def git_is_worktree(root: Path) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def build_gitignore_status(*, roots: Sequence[Path], enabled: bool) -> GitignoreStatus:
    if not enabled:
        return GitignoreStatus(enabled=False, git_available=False, root_ok={r: False for r in roots})

    available = git_available()
    if not available:
        return GitignoreStatus(enabled=True, git_available=False, root_ok={r: False for r in roots})

    root_ok: dict[Path, bool] = {r: git_is_worktree(r) for r in roots}
    return GitignoreStatus(enabled=True, git_available=True, root_ok=root_ok)


def git_check_ignore(root: Path, rel_paths: Sequence[str], *, timeout_s: float) -> set[str]:
    """Return the subset of rel_paths ignored by gitignore rules."""

    if not rel_paths:
        return set()
    inp = "\0".join(rel_paths) + "\0"
    proc = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--stdin", "-z"],
        input=inp,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_s,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or f"git check-ignore failed (code {proc.returncode})")
    if not proc.stdout:
        return set()
    out = proc.stdout.split("\0")
    return {p.rstrip("/") for p in out if p}
