"""Tests for file_watcher/gitignore.py.

What this file tests
- git_available: detection of git on PATH.
- git_is_worktree: detection of git worktree.
- git_check_ignore: filtering paths via git check-ignore (uses mock repo).
- build_gitignore_status: status construction for gitignore filtering.
"""

from __future__ import annotations

from pathlib import Path

from file_watcher.gitignore import (
    build_gitignore_status,
    git_available,
    git_check_ignore,
    git_is_worktree,
)


class TestGitAvailable:
    """Tests for git_available function."""

    def test_git_available(self) -> None:
        """Git should be available in the test environment."""
        result = git_available()
        assert result is True


class TestGitIsWorktree:
    """Tests for git_is_worktree function."""

    def test_git_is_worktree_true(self, mock_python_repo: Path) -> None:
        """Mock repo is inside AivoCode git worktree."""
        result = git_is_worktree(mock_python_repo)
        assert result is True

    def test_git_is_worktree_false(self, tmp_path: Path) -> None:
        """Temp directory is not a git worktree."""
        result = git_is_worktree(tmp_path)
        assert result is False


class TestGitCheckIgnore:
    """Tests for git_check_ignore function using real git."""

    def test_git_check_ignore_empty(self, mock_python_repo: Path) -> None:
        """Empty input returns empty set."""
        result = git_check_ignore(mock_python_repo, [], timeout_s=5.0)
        assert result == set()

    def test_git_check_ignore_all_ignored(self, mock_python_repo: Path) -> None:
        """All paths matching .gitignore patterns are returned."""
        gitignore_path = mock_python_repo / ".gitignore"
        test_file1 = mock_python_repo / "test_ignored1.log"
        test_file2 = mock_python_repo / "test_ignored2.log"

        try:
            gitignore_path.write_text("*.log\n")
            test_file1.write_text("test1")
            test_file2.write_text("test2")

            result = git_check_ignore(
                mock_python_repo,
                ["test_ignored1.log", "test_ignored2.log"],
                timeout_s=5.0,
            )
            assert "test_ignored1.log" in result
            assert "test_ignored2.log" in result
        finally:
            gitignore_path.unlink(missing_ok=True)
            test_file1.unlink(missing_ok=True)
            test_file2.unlink(missing_ok=True)

    def test_git_check_ignore_partial(self, mock_python_repo: Path) -> None:
        """Only paths matching .gitignore patterns are returned."""
        gitignore_path = mock_python_repo / ".gitignore"
        test_file_log = mock_python_repo / "test_partial.log"
        test_file_py = mock_python_repo / "test_partial.py"

        try:
            gitignore_path.write_text("*.log\n")
            test_file_log.write_text("log content")
            test_file_py.write_text("# python content")

            result = git_check_ignore(
                mock_python_repo,
                ["test_partial.log", "test_partial.py"],
                timeout_s=5.0,
            )
            assert "test_partial.log" in result
            assert "test_partial.py" not in result
        finally:
            gitignore_path.unlink(missing_ok=True)
            test_file_log.unlink(missing_ok=True)
            test_file_py.unlink(missing_ok=True)

    def test_git_check_ignore_none_ignored(self, mock_python_repo: Path) -> None:
        """No paths returned when none match .gitignore patterns."""
        gitignore_path = mock_python_repo / ".gitignore"
        test_file1 = mock_python_repo / "test_not_ignored1.py"
        test_file2 = mock_python_repo / "test_not_ignored2.py"

        try:
            gitignore_path.write_text("*.log\n")
            test_file1.write_text("# python1")
            test_file2.write_text("# python2")

            result = git_check_ignore(
                mock_python_repo,
                ["test_not_ignored1.py", "test_not_ignored2.py"],
                timeout_s=5.0,
            )
            assert result == set()
        finally:
            gitignore_path.unlink(missing_ok=True)
            test_file1.unlink(missing_ok=True)
            test_file2.unlink(missing_ok=True)

    def test_git_check_ignore_directory_pattern(self, mock_python_repo: Path) -> None:
        """Directory patterns like 'temp/' work correctly."""
        gitignore_path = mock_python_repo / ".gitignore"
        temp_dir = mock_python_repo / "temp_test_dir"
        temp_file = temp_dir / "file.txt"

        try:
            gitignore_path.write_text("temp_test_dir/\n")
            temp_dir.mkdir()
            temp_file.write_text("content")

            result = git_check_ignore(
                mock_python_repo,
                ["temp_test_dir/file.txt"],
                timeout_s=5.0,
            )
            assert "temp_test_dir/file.txt" in result
        finally:
            gitignore_path.unlink(missing_ok=True)
            temp_file.unlink(missing_ok=True)
            temp_dir.rmdir()


class TestBuildGitignoreStatus:
    """Tests for build_gitignore_status function."""

    def test_build_gitignore_status_disabled(self, mock_python_repo: Path) -> None:
        """When disabled, returns status with enabled=False."""
        result = build_gitignore_status(roots=[mock_python_repo], enabled=False)

        assert result.enabled is False
        assert result.git_available is False
        assert result.root_ok == {mock_python_repo: False}

    def test_build_gitignore_status_enabled(self, mock_python_repo: Path) -> None:
        """When enabled with git available, checks each root."""
        result = build_gitignore_status(roots=[mock_python_repo], enabled=True)

        assert result.enabled is True
        assert result.git_available is True
        assert result.root_ok.get(mock_python_repo) is True

    def test_build_gitignore_status_multiple_roots(
        self, mock_python_repo: Path, tmp_path: Path
    ) -> None:
        """Status includes per-root worktree check."""
        non_git_root = tmp_path / "non_git"
        non_git_root.mkdir()

        result = build_gitignore_status(
            roots=[mock_python_repo, non_git_root], enabled=True
        )

        assert result.enabled is True
        assert result.git_available is True
        assert result.root_ok.get(mock_python_repo) is True
        assert result.root_ok.get(non_git_root) is False