"""Integration tests for ImportGraph — real mock_pkg, full daemon round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def mock_repo_ws() -> Path:
    """Workspace root for the mock_pkg test data."""
    return (Path(__file__).parent.parent / "data" / "mock_repos" / "python").resolve()


@pytest.fixture
def built_graph(mock_repo_ws: Path):
    """Return an ImportGraph already built on the mock_pkg workspace."""
    from codebase._import_graph import ImportGraph

    g = ImportGraph(mock_repo_ws)
    g.build_full()
    return g


# ═══════════════════════════════════════════════════════════════════════════════
# Graph build from real files
# ═══════════════════════════════════════════════════════════════════════════════


class TestGraphBuild:
    def test_build_full_indexes_all_files(self, built_graph):
        info = built_graph.info()
        assert info["files_indexed"] >= 10, \
            f"Expected >=10 files, got {info['files_indexed']}"
        assert info["files_skipped"] == 0
        assert info["errors"] == []

    def test_dependencies_fixtures_imports(self, built_graph):
        deps = built_graph.dependencies("mock_pkg/fixtures_imports.py")
        assert any("fixtures_classes" in d for d in deps)
        assert any("fixtures_functions" in d for d in deps)
        assert any("fixtures_callchain" in d for d in deps)

    def test_dependents_fixtures_classes(self, built_graph):
        deps = built_graph.dependents("mock_pkg/fixtures_classes.py", depth=2)
        dep_files = {d["file"] for d in deps}
        assert "mock_pkg/fixtures_imports.py" in dep_files
        assert "mock_pkg/fixtures_functions.py" in dep_files
        assert "mock_pkg/fixtures_callchain.py" in dep_files
        # All direct importers are at depth 1.
        depths = {d["file"]: d["depth"] for d in deps}
        assert depths["mock_pkg/fixtures_imports.py"] == 1

    def test_relative_imports_resolved(self, built_graph):
        deps = built_graph.dependencies("mock_pkg/subpkg/deep_relative.py")
        assert any("fixtures_classes" in d for d in deps), \
            f"Relative dot-dot import not resolved: {deps}"
        assert any("fixtures_functions" in d for d in deps)
        assert any("fixtures_relative" in d for d in deps)

    def test_affected_tests_finds_test_mock(self, built_graph):
        """``test_mock.py`` is found; non-test dependents are excluded."""
        tests = built_graph.affected_tests("mock_pkg/fixtures_classes.py", depth=4)
        test_files = {t["file"] for t in tests}
        depths = {t["file"]: t["depth"] for t in tests}

        # Must include the test file.
        assert any("test_mock" in f for f in test_files), \
            f"test_mock.py not found in affected tests: {test_files}"
        assert depths["tests/test_mock.py"] == 1  # direct importer

        # Non-test dependents must be excluded.
        assert "mock_pkg/fixtures_imports.py" not in test_files
        assert "mock_pkg/fixtures_functions.py" not in test_files
        assert "mock_pkg/fixtures_callchain.py" not in test_files
        assert "mock_pkg/fixtures_relative.py" not in test_files

    def test_circular_no_infinite_loop(self, built_graph):
        deps = built_graph.dependents("mock_pkg/fixtures_circular_a.py", depth=10)
        assert len(deps) < 5, f"Circular imports caused explosion: {len(deps)}"

    # ── Transitive depth tests (chain fixtures) ────────────────────────────

    def test_dependents_transitive_depth(self, built_graph):
        """``chain_target`` dependents include depth-2 via ``chain_middle``."""
        deps = built_graph.dependents("mock_pkg/chain_target.py", depth=3)
        dep_files = {d["file"] for d in deps}
        depths = {d["file"]: d["depth"] for d in deps}

        # Direct importer — depth 1.
        assert "mock_pkg/chain_middle.py" in dep_files
        assert depths["mock_pkg/chain_middle.py"] == 1

        # Transitive via middle, does NOT directly import target — depth 2.
        assert "mock_pkg/chain_leaf.py" in dep_files
        assert depths["mock_pkg/chain_leaf.py"] == 2

        # Depth-2 test file (via middle, NOT direct).
        assert "tests/test_transitive_impact.py" in dep_files
        assert depths["tests/test_transitive_impact.py"] == 2

    def test_affected_tests_transitive(self, built_graph):
        """``affected_tests`` returns the depth-2 test file; excludes non-tests."""
        result = built_graph.affected_tests("mock_pkg/chain_target.py", depth=4)
        files = {t["file"] for t in result}
        depths = {t["file"]: t["depth"] for t in result}

        # Depth-2 test file — reached transitively, not directly.
        assert "tests/test_transitive_impact.py" in files
        assert depths["tests/test_transitive_impact.py"] == 2

        # Non-test dependents must be excluded (even at depth 1 or 2).
        assert "mock_pkg/chain_middle.py" not in files
        assert "mock_pkg/chain_leaf.py" not in files

    # ── Incremental update (watcher pattern) ───────────────────────────────

    def test_update_adds_file_and_edges(self, mock_repo_ws, built_graph):
        """Simulating a watcher add event: new file → edges to existing files."""
        new_file = mock_repo_ws / "mock_pkg" / "new_importer.py"
        try:
            new_file.write_text(
                "from mock_pkg.fixtures_classes import GreeterBase\n"
            )
            built_graph.update([new_file])

            # New file now indexed.
            assert "mock_pkg/new_importer.py" in built_graph.files()

            # Forward edge: new_importer → fixtures_classes.
            assert "mock_pkg/fixtures_classes.py" in \
                built_graph.dependencies("mock_pkg/new_importer.py")

            # Reverse edge: fixtures_classes ← new_importer.
            assert "mock_pkg/new_importer.py" in \
                built_graph.direct_dependents("mock_pkg/fixtures_classes.py")
        finally:
            new_file.unlink(missing_ok=True)

    def test_update_remove_file_clears_edges(self, mock_repo_ws, built_graph):
        """Simulating a watcher delete event: edges are cleaned up."""
        # Create a temporary file that imports chain_target.
        tmp_file = mock_repo_ws / "mock_pkg" / "tmp_importer.py"
        try:
            tmp_file.write_text(
                "from mock_pkg.chain_target import target_function\n"
            )
            built_graph.update([tmp_file])

            assert "mock_pkg/tmp_importer.py" in built_graph.files()
            assert "mock_pkg/chain_target.py" in \
                built_graph.dependencies("mock_pkg/tmp_importer.py")

            # Now remove it.
            tmp_file.unlink()
            built_graph.update([tmp_file])

            # File removed from graph.
            assert "mock_pkg/tmp_importer.py" not in built_graph.files()
            # Edge cleared.
            assert built_graph.dependencies("mock_pkg/tmp_importer.py") == []
        finally:
            tmp_file.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Daemon round-trip (requires running daemon)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDaemonRoundTrip:
    def test_import_dependents_via_daemon(self, mock_repo_ws):
        """End-to-end: send query to daemon, verify response shape and contents."""
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

        # Verify info dict contents (daemon protocol: info is still a dict).
        info = result["info"]
        assert isinstance(info["files_indexed"], int)
        assert info["files_indexed"] > 0
        assert isinstance(info["errors"], list)

        deps = result["dependents"]
        dep_files = {d["file"] for d in deps}
        assert any("fixtures_imports" in f for f in dep_files)

        # At least one entry should have its depth set.
        for d in deps:
            assert isinstance(d["depth"], int)
            assert d["depth"] >= 1

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

        # Verify info is present in daemon response.
        assert "info" in result
        info = result["info"]
        assert isinstance(info["files_indexed"], int)

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

        # Verify depth values on affected test entries.
        for t in result["affected_test_files"]:
            assert isinstance(t["depth"], int)
            assert t["depth"] >= 1

        # Verify info present in daemon response.
        assert "info" in result
        assert isinstance(result["info"]["files_indexed"], int)


# ═══════════════════════════════════════════════════════════════════════════════
# graph_reindex — daemon-side import-graph update
# ═══════════════════════════════════════════════════════════════════════════════


class TestGraphReindex:
    """Integration tests for the ``graph_reindex`` daemon method.

    Calls ``graph_reindex`` via ``send_query`` and then queries the import
    graph to verify the update was applied.
    """

    def test_modify_swaps_dependencies(self, mock_repo_ws):
        """Modify a file's imports → reindex → forward edges updated."""
        from lsp import detect_workspace
        from lsp._daemon import send_query

        ws = detect_workspace(mock_repo_ws)
        target = mock_repo_ws / "mock_pkg" / "chain_middle.py"
        original = target.read_text()

        try:
            # Change middle.py to import leaf instead of target.
            target.write_text(
                "from mock_pkg.chain_leaf import leaf_function\n"
                "def middle_function(): return leaf_function()\n"
            )
            _reindex_file(ws, target)

            deps = send_query(ws, "import_dependencies", {"file": str(target)})
            dep_files = deps.get("dependencies", [])
            assert any("chain_leaf" in d for d in dep_files), \
                f"chain_leaf not in deps after modify: {dep_files}"
            assert not any("chain_target" in d for d in dep_files), \
                f"chain_target still in deps after modify: {dep_files}"
        finally:
            target.write_text(original)
            _reindex_file(ws, target)

    def test_add_new_file_and_edges(self, mock_repo_ws):
        """Add a new file → reindex → appears in dependents + dependencies."""
        from lsp import detect_workspace
        from lsp._daemon import send_query

        ws = detect_workspace(mock_repo_ws)
        new_file = mock_repo_ws / "mock_pkg" / "_reindex_test_add.py"
        try:
            new_file.write_text(
                "from mock_pkg.chain_target import target_function\n"
            )
            _reindex_file(ws, new_file)

            # Forward edge.
            deps = send_query(ws, "import_dependencies", {
                "file": str(new_file),
            })
            assert any("chain_target" in d for d in deps.get("dependencies", [])), \
                f"chain_target not in deps of new file: {deps}"

            # Reverse edge — chain_target should show new_file as dependent.
            result = send_query(ws, "import_dependents", {
                "file": str(mock_repo_ws / "mock_pkg" / "chain_target.py"),
                "depth": "1",
            })
            dep_files = {d["file"] for d in result.get("dependents", [])}
            assert any("_reindex_test_add" in f for f in dep_files), \
                f"new file not in chain_target dependents: {dep_files}"
        finally:
            new_file.unlink(missing_ok=True)
            _reindex_file(ws, new_file)

    def test_delete_file_clears_edges(self, mock_repo_ws):
        """Delete a file → reindex → edges removed, count decremented."""
        from lsp import detect_workspace
        from lsp._daemon import send_query

        ws = detect_workspace(mock_repo_ws)
        tmp_file = mock_repo_ws / "mock_pkg" / "_reindex_test_del.py"
        try:
            tmp_file.write_text(
                "from mock_pkg.chain_target import target_function\n"
            )
            _reindex_file(ws, tmp_file)

            # Record count before deletion.
            info_before = send_query(ws, "import_dependencies", {
                "file": str(tmp_file),
            }).get("info", {})
            count_before = info_before.get("files_indexed", 0)

            # Delete and reindex.
            tmp_file.unlink()
            _reindex_file(ws, tmp_file)

            # File should be gone.
            deps = send_query(ws, "import_dependencies", {
                "file": str(tmp_file),
            })
            assert deps.get("dependencies") == [], \
                f"dependencies not empty after delete: {deps}"

            # Count should have decreased.
            info_after = deps.get("info", {})
            count_after = info_after.get("files_indexed", 0)
            assert count_after < count_before, \
                f"files_indexed did not decrease after delete: {count_before} → {count_after}"
        finally:
            tmp_file.unlink(missing_ok=True)
            _reindex_file(ws, tmp_file)

    def test_non_python_file_no_drift(self, mock_repo_ws):
        """Reindex a non-code file → ``files_indexed`` stays the same."""
        from lsp import detect_workspace
        from lsp._daemon import send_query

        ws = detect_workspace(mock_repo_ws)

        # Get current count via any query that returns info.
        info_before = send_query(ws, "import_dependencies", {
            "file": str(mock_repo_ws / "mock_pkg" / "chain_target.py"),
        }).get("info", {})
        count_before = info_before.get("files_indexed", 0)

        readme = mock_repo_ws / "README.md"
        try:
            readme.write_text("# Test\n")
            _reindex_file(ws, readme)

            info_after = send_query(ws, "import_dependencies", {
                "file": str(mock_repo_ws / "mock_pkg" / "chain_target.py"),
            }).get("info", {})
            count_after = info_after.get("files_indexed", 0)

            assert count_after == count_before, \
                f"files_indexed drifted for non-code file: {count_before} → {count_after}"
        finally:
            readme.unlink(missing_ok=True)
            _reindex_file(ws, readme)


# ── helper ────────────────────────────────────────────────────────────────────


def _reindex_file(workspace: Path, file_path: Path) -> None:
    """Send a ``graph_reindex`` query to the daemon for a single file."""
    from lsp._daemon import send_query

    files_json = json.dumps([str(file_path)])
    send_query(workspace, "graph_reindex", {"files": files_json})
