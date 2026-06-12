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
    """Tests for ``affected_tests``: filtering + depth correctness.

    Uses ``tmp_path`` with a real ``build_full()`` so the PythonHandler
    can resolve imports and identify test files properly.
    """

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _setup_chain(tmp_path: Path) -> ImportGraph:
        """Create a flat package with a transitive chain and build the graph.

        Returns the built ``ImportGraph`` ready for queries.

        Structure::

            target.py         ←  query target
            middle.py         ←  imports target
            leaf.py           ←  imports middle (NOT target)
            test_direct.py        ←  imports target  (test by prefix)
            test_transitive.py    ←  imports middle  (test by prefix, NOT target)
            test_other.py         ←  standalone  (test by prefix)
            helper.py             ←  source file importing target
        """
        (tmp_path / "target.py").write_text("def f(): pass\n")
        (tmp_path / "middle.py").write_text(
            "from target import f\ndef g(): return f()\n"
        )
        (tmp_path / "leaf.py").write_text(
            "from middle import g\ndef h(): return g()\n"
        )
        (tmp_path / "test_direct.py").write_text(
            "from target import f\ndef test_f(): pass\n"
        )
        (tmp_path / "test_transitive.py").write_text(
            "from middle import g\ndef test_g(): assert g()\n"
        )
        (tmp_path / "test_other.py").write_text("def test_nothing(): pass\n")
        (tmp_path / "helper.py").write_text(
            "from target import f\ndef helper(): return f()\n"
        )

        g = ImportGraph(tmp_path)
        g.build_full()
        return g

    # ── tests ────────────────────────────────────────────────────────────

    def test_direct_dependent_found(self, tmp_path):
        """A test file directly importing the target is in affected_tests."""
        g = self._setup_chain(tmp_path)
        result = g.affected_tests("target.py", depth=4)
        files = {t["file"] for t in result}
        assert "test_direct.py" in files

    def test_non_test_files_excluded(self, tmp_path):
        """Source files that depend on the target are NOT in affected_tests."""
        g = self._setup_chain(tmp_path)
        result = g.affected_tests("target.py", depth=4)
        files = {t["file"] for t in result}
        # These are dependents but NOT test files → must be absent.
        assert "middle.py" not in files
        assert "leaf.py" not in files
        assert "helper.py" not in files

    def test_depth_values(self, tmp_path):
        """Each affected-test entry has the correct depth."""
        g = self._setup_chain(tmp_path)
        result = g.affected_tests("target.py", depth=4)
        depths = {t["file"]: t["depth"] for t in result}
        assert depths["test_direct.py"] == 1  # direct importer

    def test_transitive_depth_2(self, tmp_path):
        """A test file at depth 2 (via ``middle``) that never imports the target."""
        g = self._setup_chain(tmp_path)
        result = g.affected_tests("target.py", depth=4)
        files = {t["file"] for t in result}
        depths = {t["file"]: t["depth"] for t in result}
        assert "test_transitive.py" in files
        assert depths["test_transitive.py"] == 2

    def test_unrelated_test_not_included(self, tmp_path):
        """A test file that never imports the target (directly or transitively)."""
        g = self._setup_chain(tmp_path)
        result = g.affected_tests("target.py", depth=4)
        files = {t["file"] for t in result}
        assert "test_other.py" not in files

    def test_no_dependents(self):
        """Empty graph returns empty list."""
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

    def test_empty_update_noop(self, tmp_path):
        """``update([])`` is a no-op — counters and state unchanged."""
        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("")

        g = ImportGraph(tmp_path)
        g.build_full()

        info_before = g.info()
        g.update([])
        info_after = g.info()

        assert info_before["files_indexed"] == info_after["files_indexed"]
        assert info_before["files_skipped"] == info_after["files_skipped"]

    def test_mixed_batch_add_modify_delete(self, tmp_path):
        """Single ``update()`` call with a mix of add / modify / delete."""
        (tmp_path / "target.py").write_text("def f(): pass\n")
        (tmp_path / "mod.py").write_text("from target import f\n")

        g = ImportGraph(tmp_path)
        g.build_full()

        # Prepare: files for add, modify, delete.
        add_file = tmp_path / "added.py"
        add_file.write_text("from target import f\n")
        (tmp_path / "mod.py").write_text("import os\n")  # swap import
        (tmp_path / "target.py").unlink()                # delete

        g.update([add_file, tmp_path / "mod.py", tmp_path / "target.py"])

        assert "added.py" in g.files()                       # added
        assert "os" not in g.dependencies("mod.py")          # modify (external)
        assert "target.py" not in g.files()                  # deleted
        assert g.dependencies("target.py") == []              # deleted
        assert "target.py" not in g.direct_dependents(
            [d for d in g.files() if d != "target.py"][0]
        )

    def test_non_python_file_no_drift(self, tmp_path):
        """``update()`` on a non-code file does NOT change ``_files_indexed``."""
        (tmp_path / "a.py").write_text("def f(): pass\n")

        g = ImportGraph(tmp_path)
        g.build_full()
        count_before = g.info()["files_indexed"]

        # Non-Python file — no handler, no graph entry, should be a no-op.
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n")
        g.update([readme])

        assert g.info()["files_indexed"] == count_before, \
            "_files_indexed drifted for non-Python file"


# ═══════════════════════════════════════════════════════════════════════════════
# error accumulation
# ═══════════════════════════════════════════════════════════════════════════════


class TestErrorAccumulation:
    """Verify ``_errors`` / ``_files_skipped`` when ``extract_imports`` raises."""

    def test_extract_imports_error(self, tmp_path):
        """Handler that raises populates ``_errors`` and ``_files_skipped``."""
        from codebase._lang_handlers._python import PythonHandler
        from codebase._lang_handlers import register_handler
        from codebase._lang_handlers import _SUFFIX_REGISTRY as _reg

        # Register a handler for a custom suffix that always raises.
        # NOTE: must set *both* ``suffixes`` (used by the registry) and
        # behave like a working handler for module_path / resolve_import.
        class RaisingHandler(PythonHandler):
            suffixes = (".raise",)

            def extract_imports(self, file_path):
                raise ValueError("simulated parse failure")

        register_handler(RaisingHandler())
        try:
            bad_file = tmp_path / "bad.raise"
            bad_file.write_text("not relevant")

            g = ImportGraph(tmp_path)
            g.build_full()

            info = g.info()
            assert info["files_skipped"] >= 1, \
                f"Expected >= 1 skipped, got {info['files_skipped']}"
            assert len(info["errors"]) >= 1, \
                f"Expected >= 1 errors, got {info['errors']}"
            assert "simulated parse failure" in info["errors"][0]["reason"]
        finally:
            # Unregister so other tests are not polluted.
            _reg.pop(".raise", None)


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

    def test_build_idempotent(self, tmp_path):
        """Calling ``build_full()`` twice produces the same graph."""
        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("")

        g = ImportGraph(tmp_path)
        g.build_full()

        info1 = g.info()
        files1 = g.files()
        deps1 = g.dependencies("a.py")

        # Second build should clear and rebuild to the same state.
        g.build_full()

        info2 = g.info()
        files2 = g.files()
        deps2 = g.dependencies("a.py")

        assert info1["files_indexed"] == info2["files_indexed"]
        assert info2["files_skipped"] == 0
        assert files1 == files2
        assert deps1 == deps2


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
