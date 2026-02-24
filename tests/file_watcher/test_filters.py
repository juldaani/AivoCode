"""Tests for file_watcher/filters.py.

What this file tests
- build_watchfiles_filter: filter construction with defaults, custom excludes, and combinations.
"""

from __future__ import annotations

from pathlib import Path

from watchfiles import DefaultFilter

from file_watcher.filters import build_watchfiles_filter


class TestBuildWatchfilesFilter:
    """Tests for build_watchfiles_filter function."""

    def test_build_filter_defaults_only(self) -> None:
        """defaults_filter=True with no custom excludes returns DefaultFilter()."""
        result = build_watchfiles_filter(
            use_defaults_filter=True,
            repo_custom_ignores={},
        )

        assert result is not None
        assert isinstance(result, DefaultFilter)
        assert set(result.ignore_dirs) == set(DefaultFilter().ignore_dirs)
        assert set(result.ignore_entity_patterns) == set(
            DefaultFilter().ignore_entity_patterns
        )
        assert result.ignore_paths == DefaultFilter().ignore_paths

    def test_build_filter_custom_only_returns_none(self) -> None:
        """defaults_filter=False with no custom excludes returns None."""
        result = build_watchfiles_filter(
            use_defaults_filter=False,
            repo_custom_ignores={},
        )

        assert result is None

    def test_build_filter_custom_only(self) -> None:
        """defaults_filter=False with custom excludes returns filter with only custom items."""
        repo_root = Path("/tmp/repo")
        result = build_watchfiles_filter(
            use_defaults_filter=False,
            repo_custom_ignores={
                repo_root: ["node_modules", ".cache", "*.log"]
            },
        )

        assert result is not None
        # In the new implementation, everything goes into ignore_paths or ignore_entity_patterns
        ignore_paths_str = [str(p) for p in result.ignore_paths]
        assert str(repo_root / "node_modules") in ignore_paths_str
        assert str(repo_root / ".cache") in ignore_paths_str
        assert len(result.ignore_entity_patterns) == 1

    def test_build_filter_combined(self) -> None:
        """defaults_filter=True with custom excludes merges both."""
        repo_root = Path("/tmp/repo")
        custom_dir = "my_custom_build_dir"
        result = build_watchfiles_filter(
            use_defaults_filter=True,
            repo_custom_ignores={
                repo_root: [custom_dir, "*.log"]
            },
        )

        assert result is not None
        ignore_paths_str = [str(p) for p in result.ignore_paths]
        assert str(repo_root / custom_dir) in ignore_paths_str
        assert ".git" in result.ignore_dirs # from DefaultFilter

    def test_build_filter_relative_ignore_paths(self, tmp_path: Path) -> None:
        """Relative ignore_paths are expanded per repo root."""
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        repo1.mkdir()
        repo2.mkdir()

        result = build_watchfiles_filter(
            use_defaults_filter=False,
            repo_custom_ignores={
                repo1: ["secrets.txt"],
                repo2: ["secrets.txt"]
            },
        )

        assert result is not None
        ignore_paths_str = [str(p) for p in result.ignore_paths]
        assert str(repo1 / "secrets.txt") in ignore_paths_str
        assert str(repo2 / "secrets.txt") in ignore_paths_str

    def test_build_filter_absolute_ignore_paths(self) -> None:
        """Absolute ignore_paths are used as-is."""
        repo_root = Path("/tmp/repo")
        abs_path = Path("/etc/config.ini")

        result = build_watchfiles_filter(
            use_defaults_filter=False,
            repo_custom_ignores={
                repo_root: [str(abs_path)]
            },
        )

        assert result is not None
        assert abs_path in result.ignore_paths