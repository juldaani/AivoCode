"""Shared pytest fixtures for all tests.

What this file provides
- mock_python_repo: Path to the mock Python repo used for gitignore testing.
- sample_watch_event: Factory to create WatchEvent objects for testing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from watchfiles import Change

from file_watcher.types import WatchEvent


@pytest.fixture
def mock_python_repo() -> Path:
    """Path to the mock Python repo (inside AivoCode git worktree)."""
    return Path(__file__).parent / "data" / "mock_repos" / "python"


@pytest.fixture
def sample_watch_event() -> Callable[[Change, Path, Path | None, str, str], WatchEvent]:
    """Factory to create WatchEvent objects for testing.

    Returns a function that takes:
    - change: Change enum (added, modified, deleted)
    - abs_path: Absolute path to the file
    - repo_root: Root of the repo (or None)
    - repo_label: Label for the repo
    - rel_path: Relative path from repo root
    """

    def _make_event(
        change: Change,
        abs_path: Path,
        repo_root: Path | None,
        repo_label: str,
        rel_path: str,
    ) -> WatchEvent:
        return WatchEvent(
            change=change,
            abs_path=abs_path,
            repo_root=repo_root,
            repo_label=repo_label,
            rel_path=rel_path,
        )

    return _make_event
