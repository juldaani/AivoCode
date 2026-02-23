"""Tests for file_watcher/watcher.py.

What this file tests
- _normalize_roots: validation, deduplication, labeling, nested detection.
- _classify_path: path attribution to roots.
- _coalesce_events: event deduplication logic.
- _apply_gitignore_filter: gitignore-based filtering.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from watchfiles import Change

from file_watcher.gitignore import GitignoreStatus
from file_watcher.types import WatchConfig, WatchEvent
from file_watcher.watcher import (
    _apply_gitignore_filter,
    _classify_path,
    _coalesce_events,
    _normalize_roots,
)


class TestNormalizeRoots:
    """Tests for _normalize_roots function."""

    def test_normalize_roots_valid(self, tmp_path: Path) -> None:
        """Valid roots return RootInfo with correct labels."""
        dir1 = tmp_path / "repo1"
        dir2 = tmp_path / "repo2"
        dir1.mkdir()
        dir2.mkdir()

        result = _normalize_roots([dir1, dir2])

        assert len(result.roots) == 2
        assert dir1 in result.roots
        assert dir2 in result.roots
        assert result.labels[dir1] == "repo1"
        assert result.labels[dir2] == "repo2"

    def test_normalize_roots_invalid_path(self) -> None:
        """Non-existent root raises ValueError."""
        fake_path = Path("/nonexistent/path/that/does/not/exist")
        with pytest.raises(ValueError, match="Invalid root"):
            _normalize_roots([fake_path])

    def test_normalize_roots_not_directory(self, tmp_path: Path) -> None:
        """File path as root raises ValueError."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        with pytest.raises(ValueError, match="Invalid root"):
            _normalize_roots([file_path])

    def test_normalize_roots_deduplicate(self, tmp_path: Path) -> None:
        """Duplicate roots are deduplicated preserving order."""
        dir1 = tmp_path / "repo1"
        dir1.mkdir()

        result = _normalize_roots([dir1, dir1, dir1])

        assert len(result.roots) == 1
        assert result.roots[0] == dir1

    def test_normalize_roots_label_disambiguation(self, tmp_path: Path) -> None:
        """Same basename roots get disambiguated labels."""
        parent = tmp_path / "parent"
        parent.mkdir()
        dir1 = parent / "foo"
        dir2 = parent / "bar"
        dir3 = tmp_path / "foo"
        dir1.mkdir()
        dir2.mkdir()
        dir3.mkdir()

        result = _normalize_roots([dir1, dir2, dir3])

        assert len(result.roots) == 3
        foo_labels = [result.labels[r] for r in result.roots if r.name == "foo"]
        assert len(foo_labels) == 2
        assert "foo#1" in foo_labels
        assert "foo#2" in foo_labels
        bar_labels = [result.labels[r] for r in result.roots if r.name == "bar"]
        assert bar_labels == ["bar"]

    def test_normalize_roots_nested_pairs(self, tmp_path: Path) -> None:
        """Nested roots are detected."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        outer.mkdir()
        inner.mkdir()

        result = _normalize_roots([outer, inner])

        assert len(result.nested_pairs) == 1
        assert (outer, inner) in result.nested_pairs


class TestClassifyPath:
    """Tests for _classify_path function."""

    def test_classify_path_single_root(self, tmp_path: Path) -> None:
        """Path under single root gets correct attribution."""
        root = tmp_path / "repo"
        root.mkdir()
        file_path = root / "src" / "main.py"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test")

        labels = {root: "repo"}
        result = _classify_path(str(file_path), roots=[root], labels=labels)

        assert result.repo_root == root
        assert result.repo_label == "repo"
        assert result.rel_path == "src/main.py"

    def test_classify_path_nested_roots(self, tmp_path: Path) -> None:
        """Path under nested roots attributes to deepest root."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        outer.mkdir()
        inner.mkdir()
        file_path = inner / "file.py"
        file_path.write_text("test")

        labels = {outer: "outer", inner: "inner"}
        result = _classify_path(str(file_path), roots=[outer, inner], labels=labels)

        assert result.repo_root == inner
        assert result.repo_label == "inner"

    def test_classify_path_outside_roots(self, tmp_path: Path) -> None:
        """Path outside all roots gets repo_root=None."""
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        file_path = outside / "file.py"
        file_path.write_text("test")

        labels = {root: "repo"}
        result = _classify_path(str(file_path), roots=[root], labels=labels)

        assert result.repo_root is None
        assert result.repo_label == "?"


class TestCoalesceEvents:
    """Tests for _coalesce_events function."""

    def test_coalesce_single_added(self, tmp_path: Path) -> None:
        """Single ADDED event passes through."""
        file_path = tmp_path / "added.txt"
        file_path.write_text("test")

        events = [
            WatchEvent(
                change=Change.added,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="added.txt",
            )
        ]

        result = _coalesce_events(events)

        assert len(result) == 1
        assert result[0].change == Change.added

    def test_coalesce_single_deleted(self, tmp_path: Path) -> None:
        """Single DELETED event passes through."""
        file_path = tmp_path / "deleted.txt"

        events = [
            WatchEvent(
                change=Change.deleted,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="deleted.txt",
            )
        ]

        result = _coalesce_events(events)

        assert len(result) == 1
        assert result[0].change == Change.deleted

    def test_coalesce_added_deleted_exists(self, tmp_path: Path) -> None:
        """ADDED + DELETED with file existing becomes MODIFIED."""
        file_path = tmp_path / "replaced.txt"
        file_path.write_text("test")

        events = [
            WatchEvent(
                change=Change.added,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="replaced.txt",
            ),
            WatchEvent(
                change=Change.deleted,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="replaced.txt",
            ),
        ]

        result = _coalesce_events(events)

        assert len(result) == 1
        assert result[0].change == Change.modified

    def test_coalesce_added_deleted_missing(self, tmp_path: Path) -> None:
        """ADDED + DELETED with file missing stays DELETED."""
        file_path = tmp_path / "deleted.txt"

        events = [
            WatchEvent(
                change=Change.added,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="deleted.txt",
            ),
            WatchEvent(
                change=Change.deleted,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="deleted.txt",
            ),
        ]

        result = _coalesce_events(events)

        assert len(result) == 1
        assert result[0].change == Change.deleted

    def test_coalesce_multiple_paths(self, tmp_path: Path) -> None:
        """Events for different paths are preserved."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("test1")
        file2.write_text("test2")

        events = [
            WatchEvent(
                change=Change.added,
                abs_path=file1,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="file1.txt",
            ),
            WatchEvent(
                change=Change.modified,
                abs_path=file2,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="file2.txt",
            ),
        ]

        result = _coalesce_events(events)

        assert len(result) == 2
        paths = {e.rel_path for e in result}
        assert paths == {"file1.txt", "file2.txt"}


class TestApplyGitignoreFilter:
    """Tests for _apply_gitignore_filter function."""

    def test_apply_gitignore_disabled(self, tmp_path: Path) -> None:
        """Gitignore disabled returns events unchanged."""
        file_path = tmp_path / "test.log"
        file_path.write_text("test")

        events = [
            WatchEvent(
                change=Change.added,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="test.log",
            )
        ]

        status = GitignoreStatus(
            enabled=False,
            git_available=False,
            root_ok={tmp_path: False},
        )
        cfg = WatchConfig()

        result, warnings = _apply_gitignore_filter(events, status=status, cfg=cfg)

        assert len(result) == 1
        assert len(warnings) == 0

    def test_apply_gitignore_filters_paths(self, mock_python_repo: Path) -> None:
        """Paths in .gitignore are filtered out."""
        gitignore_path = mock_python_repo / ".gitignore"
        test_file_log = mock_python_repo / "filtered.log"
        test_file_py = mock_python_repo / "kept.py"

        try:
            gitignore_path.write_text("*.log\n")
            test_file_log.write_text("log content")
            test_file_py.write_text("# python content")

            events = [
                WatchEvent(
                    change=Change.added,
                    abs_path=test_file_log,
                    repo_root=mock_python_repo,
                    repo_label="python",
                    rel_path="filtered.log",
                ),
                WatchEvent(
                    change=Change.added,
                    abs_path=test_file_py,
                    repo_root=mock_python_repo,
                    repo_label="python",
                    rel_path="kept.py",
                ),
            ]

            status = GitignoreStatus(
                enabled=True,
                git_available=True,
                root_ok={mock_python_repo: True},
            )
            cfg = WatchConfig()

            result, warnings = _apply_gitignore_filter(events, status=status, cfg=cfg)

            assert len(result) == 1
            assert result[0].rel_path == "kept.py"
            assert len(warnings) == 0
        finally:
            gitignore_path.unlink(missing_ok=True)
            test_file_log.unlink(missing_ok=True)
            test_file_py.unlink(missing_ok=True)

    def test_apply_gitignore_root_not_ok(self, tmp_path: Path) -> None:
        """Events from roots not marked as ok are kept (fail-open)."""
        file_path = tmp_path / "test.log"
        file_path.write_text("test")

        events = [
            WatchEvent(
                change=Change.added,
                abs_path=file_path,
                repo_root=tmp_path,
                repo_label="test",
                rel_path="test.log",
            )
        ]

        status = GitignoreStatus(
            enabled=True,
            git_available=True,
            root_ok={tmp_path: False},
        )
        cfg = WatchConfig()

        result, warnings = _apply_gitignore_filter(events, status=status, cfg=cfg)

        assert len(result) == 1

    def test_apply_gitignore_no_repo_root(self, tmp_path: Path) -> None:
        """Events without repo_root are kept unchanged."""
        file_path = tmp_path / "outside.txt"
        file_path.write_text("test")

        events = [
            WatchEvent(
                change=Change.added,
                abs_path=file_path,
                repo_root=None,
                repo_label="?",
                rel_path="outside.txt",
            )
        ]

        status = GitignoreStatus(
            enabled=True,
            git_available=True,
            root_ok={},
        )
        cfg = WatchConfig()

        result, warnings = _apply_gitignore_filter(events, status=status, cfg=cfg)

        assert len(result) == 1