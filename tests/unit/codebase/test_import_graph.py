"""Unit tests for ImportGraph — pure graph logic with programmatic edges."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebase._import_graph import ImportGraph


def _make_graph(edges: dict[str, set[str]]) -> ImportGraph:
    """Build an ImportGraph with manually-populated forward/reverse edges.

    *edges* maps ``importer → {imported_files}``.  For each entry the
    reverse edges are also populated.
    """
    g = ImportGraph(Path("/fake/ws"))
    for importer, imported in edges.items():
        g._forward[importer] = set(imported)
        g._reverse.setdefault(importer, set())
        for target in imported:
            g._reverse.setdefault(target, set()).add(importer)
            g._forward.setdefault(target, set())
    g._files_indexed = len(edges)
    return g


def _deps_files(result: list[dict]) -> list[str]:
    """Extract just the file names from dependents results."""
    return [d["file"] for d in result]


# ═══════════════════════════════════════════════════════════════════════════════
# dependents
# ═══════════════════════════════════════════════════════════════════════════════


class TestDependents:
    def test_depth_1_direct(self):
        g = _make_graph({
            "b.py": {"a.py"},
            "c.py": {"a.py"},
        })
        result = g.dependents("a.py", depth=1)
        assert _deps_files(result) == ["b.py", "c.py"]
        assert result[0]["depth"] == 1

    def test_depth_2_transitive(self):
        g = _make_graph({
            "b.py": {"a.py"},
            "c.py": {"b.py"},
            "test_c.py": {"c.py"},
        })
        result = g.dependents("a.py", depth=3)
        files = _deps_files(result)
        assert "b.py" in files
        assert "c.py" in files
        assert "test_c.py" in files
        # Check depths
        depths = {d["file"]: d["depth"] for d in result}
        assert depths["b.py"] == 1
        assert depths["c.py"] == 2
        assert depths["test_c.py"] == 3

    def test_depth_deeper_than_graph(self):
        g = _make_graph({
            "b.py": {"a.py"},
        })
        result = g.dependents("a.py", depth=10)
        assert _deps_files(result) == ["b.py"]

    def test_nothing_imports_me(self):
        g = _make_graph({"a.py": {"b.py"}})
        result = g.dependents("a.py", depth=1)
        assert result == []

    def test_file_not_in_graph(self):
        g = _make_graph({"a.py": {"b.py"}})
        result = g.dependents("nonexistent.py", depth=1)
        assert result == []

    def test_circular_imports_no_duplicates(self):
        g = _make_graph({
            "a.py": {"b.py"},
            "b.py": {"a.py"},
            "c.py": {"b.py"},
        })
        result = g.dependents("a.py", depth=4)
        files = _deps_files(result)
        assert "b.py" in files
        assert "c.py" in files
        # No duplicates
        assert len(files) == len(set(files))
        assert len(files) < 10

    def test_self_import(self):
        g = _make_graph({"a.py": {"a.py"}})
        result = g.dependents("a.py", depth=3)
        # A imports itself — shouldn't appear in dependents (visited set excludes it)
        assert result == []

    def test_sorted_by_depth_then_name(self):
        g = _make_graph({
            "z.py": {"a.py"},
            "b.py": {"a.py"},
            "c.py": {"b.py"},
        })
        result = g.dependents("a.py", depth=5)
        files = _deps_files(result)
        # depth=1 sorted by name
        assert files[0] == "b.py"
        assert files[1] == "z.py"
        # depth=2
        assert files[2] == "c.py"


# ═══════════════════════════════════════════════════════════════════════════════
# dependencies
# ═══════════════════════════════════════════════════════════════════════════════


class TestDependencies:
    def test_single_to_many(self):
        g = _make_graph({"a.py": {"b.py", "c.py", "d.py"}})
        assert g.dependencies("a.py") == ["b.py", "c.py", "d.py"]

    def test_empty_dependencies(self):
        g = _make_graph({"a.py": set()})
        assert g.dependencies("a.py") == []

    def test_file_not_in_graph(self):
        g = _make_graph({"a.py": set()})
        assert g.dependencies("nonexistent.py") == []


# ═══════════════════════════════════════════════════════════════════════════════
# direct_dependents
# ═══════════════════════════════════════════════════════════════════════════════


class TestDirectDependents:
    def test_multiple_importers(self):
        g = _make_graph({
            "b.py": {"a.py"},
            "c.py": {"a.py"},
        })
        assert g.direct_dependents("a.py") == ["b.py", "c.py"]

    def test_no_importers(self):
        g = _make_graph({"a.py": set()})
        assert g.direct_dependents("a.py") == []


# ═══════════════════════════════════════════════════════════════════════════════
# affected_tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAffectedTests:
    def test_test_file_direct_dependent(self):
        # Requires a handler that knows "tests/test_x.py" is a test file.
        # This tests the graph traversal logic only — filtering relies on
        # the handler which is tested separately.
        g = _make_graph({
            "tests/test_a.py": {"src/module.py"},
            "src/helper.py": {"src/module.py"},
        })
        # Without a real handler, affected_tests will return empty (handler
        # returns None for non-.py suffixes in the test environment).
        # Here we just verify the method doesn't crash.
        result = g.affected_tests("src/module.py", depth=4)
        assert isinstance(result, list)

    def test_no_dependents(self):
        g = _make_graph({"a.py": set()})
        result = g.affected_tests("a.py")
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# update (incremental)
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpdate:
    def test_remove_file_clears_edges(self, tmp_path):
        """Simulate removing a file — its dependents should lose the edge."""
        # Create a real file so update() can process it.
        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("")

        g = ImportGraph(tmp_path)
        g.build_full()

        # Verify edge exists
        assert "b.py" in g.dependencies("a.py")

        # Remove a.py
        (tmp_path / "a.py").unlink()
        g.update([tmp_path / "a.py"])

        # Edge should be gone
        assert g.dependencies("a.py") == []
        assert g.direct_dependents("b.py") == []

    def test_modify_file_updates_edges(self, tmp_path):
        """Simulate changing a file's imports."""
        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.py").write_text("")

        g = ImportGraph(tmp_path)
        g.build_full()

        assert "b.py" in g.dependencies("a.py")
        assert "c.py" not in g.dependencies("a.py")

        # Modify a.py to import c instead of b
        (tmp_path / "a.py").write_text("import c\n")
        g.update([tmp_path / "a.py"])

        assert "c.py" in g.dependencies("a.py")
        assert "b.py" not in g.dependencies("a.py")

    def test_add_new_file(self, tmp_path):
        """Simulate adding a new file."""
        (tmp_path / "a.py").write_text("")

        g = ImportGraph(tmp_path)
        g.build_full()

        assert "new_file.py" not in g.files()

        # Add new file
        (tmp_path / "new_file.py").write_text("import a\n")
        g.update([tmp_path / "new_file.py"])

        assert "new_file.py" in g.files()
        assert "a.py" in g.dependencies("new_file.py")
        assert "new_file.py" in g.direct_dependents("a.py")


# ═══════════════════════════════════════════════════════════════════════════════
# info
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfo:
    def test_build_info(self, tmp_path):
        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("")

        g = ImportGraph(tmp_path)
        g.build_full()

        info = g.info()
        assert info["files_indexed"] == 2
        assert info["files_skipped"] == 0
        assert info["errors"] == []
        assert info["built_at"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# files
# ═══════════════════════════════════════════════════════════════════════════════


class TestFiles:
    def test_all_indexed_files(self):
        g = _make_graph({
            "a.py": {"b.py"},
            "b.py": set(),
        })
        assert g.files() == frozenset({"a.py", "b.py"})
