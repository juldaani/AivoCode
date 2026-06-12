"""Integration tests for ImportGraph — real mock_pkg, full daemon round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def mock_repo_ws() -> Path:
    """Workspace root for the mock_pkg test data."""
    return (Path(__file__).parent.parent / "data" / "mock_repos" / "python").resolve()


# ═══════════════════════════════════════════════════════════════════════════════
# Graph build from real files
# ═══════════════════════════════════════════════════════════════════════════════


class TestGraphBuild:
    def test_build_full_indexes_all_files(self, mock_repo_ws):
        from codebase._import_graph import ImportGraph

        g = ImportGraph(mock_repo_ws)
        g.build_full()

        info = g.info()
        assert info["files_indexed"] >= 10, f"Expected >=10 files, got {info['files_indexed']}"
        assert info["files_skipped"] == 0
        assert info["errors"] == []

    def test_dependencies_fixtures_imports(self, mock_repo_ws):
        from codebase._import_graph import ImportGraph

        g = ImportGraph(mock_repo_ws)
        g.build_full()

        deps = g.dependencies("mock_pkg/fixtures_imports.py")
        assert any("fixtures_classes" in d for d in deps)
        assert any("fixtures_functions" in d for d in deps)
        assert any("fixtures_callchain" in d for d in deps)

    def test_dependents_fixtures_classes(self, mock_repo_ws):
        from codebase._import_graph import ImportGraph

        g = ImportGraph(mock_repo_ws)
        g.build_full()

        deps = g.dependents("mock_pkg/fixtures_classes.py", depth=2)
        dep_files = {d["file"] for d in deps}
        assert "mock_pkg/fixtures_imports.py" in dep_files
        assert "mock_pkg/fixtures_functions.py" in dep_files
        assert "mock_pkg/fixtures_callchain.py" in dep_files

    def test_relative_imports_resolved(self, mock_repo_ws):
        from codebase._import_graph import ImportGraph

        g = ImportGraph(mock_repo_ws)
        g.build_full()

        deps = g.dependencies("mock_pkg/subpkg/deep_relative.py")
        assert any("fixtures_classes" in d for d in deps), \
            f"Relative dot-dot import not resolved: {deps}"
        assert any("fixtures_functions" in d for d in deps)
        assert any("fixtures_relative" in d for d in deps)

    def test_affected_tests_finds_test_mock(self, mock_repo_ws):
        from codebase._import_graph import ImportGraph

        g = ImportGraph(mock_repo_ws)
        g.build_full()

        tests = g.affected_tests("mock_pkg/fixtures_classes.py", depth=4)
        test_files = {t["file"] for t in tests}
        assert any("test_mock" in f for f in test_files), \
            f"test_mock.py not found in affected tests: {test_files}"

    def test_circular_no_infinite_loop(self, mock_repo_ws):
        from codebase._import_graph import ImportGraph

        g = ImportGraph(mock_repo_ws)
        g.build_full()

        deps = g.dependents("mock_pkg/fixtures_circular_a.py", depth=10)
        assert len(deps) < 5, f"Circular imports caused explosion: {len(deps)}"


# ═══════════════════════════════════════════════════════════════════════════════
# Daemon round-trip (requires running daemon)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDaemonRoundTrip:
    def test_import_dependents_via_daemon(self, mock_repo_ws):
        """End-to-end: send query to daemon, verify response."""
        from lsp import detect_workspace
        from lsp._daemon import send_query

        ws = detect_workspace(mock_repo_ws)
        fp = str(mock_repo_ws / "mock_pkg" / "fixtures_classes.py")
        result = send_query(ws, "import_dependents", {
            "file": fp,
            "depth": "2",
        })

        assert "dependents" in result
        assert "info" in result
        deps = result["dependents"]
        dep_files = {d["file"] for d in deps}
        assert any("fixtures_imports" in f for f in dep_files)

    def test_import_dependencies_via_daemon(self, mock_repo_ws):
        from lsp import detect_workspace
        from lsp._daemon import send_query

        ws = detect_workspace(mock_repo_ws)
        fp = str(mock_repo_ws / "mock_pkg" / "fixtures_imports.py")
        result = send_query(ws, "import_dependencies", {
            "file": fp,
        })

        assert "dependencies" in result
        deps = result["dependencies"]
        assert any("fixtures_classes" in d for d in deps)

    def test_affected_tests_via_daemon(self, mock_repo_ws):
        from lsp import detect_workspace
        from lsp._daemon import send_query

        ws = detect_workspace(mock_repo_ws)
        fp = str(mock_repo_ws / "mock_pkg" / "fixtures_classes.py")
        result = send_query(ws, "import_affected_tests", {
            "file": fp,
            "depth": "4",
        })

        assert "affected_test_files" in result
        tests = [t["file"] for t in result["affected_test_files"]]
        assert any("test_mock" in t for t in tests)
