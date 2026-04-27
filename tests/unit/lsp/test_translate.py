"""Unit tests for lsp._translate module."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from watchfiles import Change

from file_watcher.types import WatchBatch, WatchEvent
from lsp._translate import filter_by_suffix, translate
from lsp_client.utils.types import lsp_type


class TestFilterBySuffix:
    """Test suffix filtering."""

    def test_filters_by_suffix(self) -> None:
        """Keep only events matching suffixes."""
        events = [
            WatchEvent(
                change=Change.added,
                abs_path=Path("/repo/main.py"),
                repo_root=Path("/repo"),
                repo_label="repo",
                rel_path="main.py",
            ),
            WatchEvent(
                change=Change.added,
                abs_path=Path("/repo/README.md"),
                repo_root=Path("/repo"),
                repo_label="repo",
                rel_path="README.md",
            ),
        ]
        result = filter_by_suffix(events, [".py"])
        assert len(result) == 1
        assert result[0].abs_path.name == "main.py"

    def test_empty_suffixes_returns_all(self) -> None:
        """Empty suffix list returns all events."""
        events = [
            WatchEvent(
                change=Change.added,
                abs_path=Path("/repo/a.py"),
                repo_root=Path("/repo"),
                repo_label="repo",
                rel_path="a.py",
            ),
        ]
        result = filter_by_suffix(events, [])
        assert len(result) == 1

    def test_multiple_suffixes(self) -> None:
        """Match any of the given suffixes."""
        events = [
            _make_event("/repo/a.py"),
            _make_event("/repo/b.pyi"),
            _make_event("/repo/c.ts"),
        ]
        result = filter_by_suffix(events, [".py", ".pyi"])
        assert len(result) == 2
        names = {e.abs_path.name for e in result}
        assert names == {"a.py", "b.pyi"}

    def test_no_matches_returns_empty(self) -> None:
        """No matching suffixes returns empty list."""
        events = [_make_event("/repo/README.md")]
        result = filter_by_suffix(events, [".py"])
        assert result == []


class TestTranslate:
    """Test WatchBatch → FileEvent translation."""

    def test_translate_added(self) -> None:
        """Change.added → FileChangeType.Created."""
        batch = _make_batch([("/repo/main.py", Change.added)])
        events = translate(batch, [".py"])
        assert len(events) == 1
        assert events[0].type == lsp_type.FileChangeType.Created
        assert events[0].uri == "file:///repo/main.py"

    def test_translate_modified(self) -> None:
        """Change.modified → FileChangeType.Changed."""
        batch = _make_batch([("/repo/main.py", Change.modified)])
        events = translate(batch, [".py"])
        assert len(events) == 1
        assert events[0].type == lsp_type.FileChangeType.Changed

    def test_translate_deleted(self) -> None:
        """Change.deleted → FileChangeType.Deleted."""
        batch = _make_batch([("/repo/main.py", Change.deleted)])
        events = translate(batch, [".py"])
        assert len(events) == 1
        assert events[0].type == lsp_type.FileChangeType.Deleted

    def test_filters_by_suffix(self) -> None:
        """Only translates events matching suffixes."""
        batch = _make_batch([
            ("/repo/main.py", Change.added),
            ("/repo/README.md", Change.added),
        ])
        events = translate(batch, [".py"])
        assert len(events) == 1
        assert "main.py" in events[0].uri

    def test_empty_batch(self) -> None:
        """Empty batch returns empty list."""
        batch = _make_batch([])
        events = translate(batch, [".py"])
        assert events == []

    def test_uri_conversion(self) -> None:
        """Paths are converted to file:// URIs."""
        batch = _make_batch([("/home/user/project/src/main.py", Change.added)])
        events = translate(batch, [".py"])
        assert events[0].uri == "file:///home/user/project/src/main.py"

    def test_unknown_change_defensive(self) -> None:
        """Defensive: _change_type with unexpected input raises ValueError."""
        from lsp._translate import _change_type
        # Test with a non-Change value to hit the fallback branch
        with pytest.raises(ValueError, match="Unknown"):
            _change_type("not_a_change")  # type: ignore[arg-type]


def _make_event(abs_path: str) -> WatchEvent:
    """Helper to create a WatchEvent."""
    path = Path(abs_path)
    return WatchEvent(
        change=Change.added,
        abs_path=path,
        repo_root=path.parent,
        repo_label="repo",
        rel_path=path.name,
    )


def _make_batch(items: list[tuple[str, Change]]) -> WatchBatch:
    """Helper to create a WatchBatch."""
    events = []
    for abs_path, change in items:
        path = Path(abs_path)
        events.append(
            WatchEvent(
                change=change,
                abs_path=path,
                repo_root=path.parent,
                repo_label="repo",
                rel_path=path.name,
            )
        )
    return WatchBatch(
        ts=datetime.now(),
        raw=len(events),
        filtered=len(events),
        events=events,
    )
