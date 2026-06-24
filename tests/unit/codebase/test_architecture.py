"""Unit tests for _compute_architecture — dir grouping, transitive counts, filtering."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebase._arch import _compute_architecture
from codebase._import_graph import ImportGraph


def _make_graph(edges: dict[str, set[str]]) -> ImportGraph:
    """Build an ImportGraph with manually-populated forward/reverse edges.

    Re-used from test_import_graph — same pattern.
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


# ══════════════════════════════════════════════════════════════════════════════
# structure
# ══════════════════════════════════════════════════════════════════════════════


class TestStructure:
    def test_groups_files_by_dir(self):
        g = _make_graph({
            "lsp/a.py": set(),
            "lsp/b.py": {"codebase/c.py"},
            "codebase/c.py": set(),
        })
        result = _compute_architecture(g, hotspots=20)
        s = result["structure"]
        assert set(s.keys()) == {"lsp", "codebase"}
        assert s["lsp"]["files"] == 2
        assert s["codebase"]["files"] == 1

    def test_dir_level_imports(self):
        """lsp/a imports codebase/c → lsp.imports includes codebase."""
        g = _make_graph({
            "lsp/a.py": {"codebase/c.py"},
            "codebase/c.py": set(),
        })
        result = _compute_architecture(g, hotspots=20)
        s = result["structure"]
        assert s["lsp"]["imports"] == ["codebase"]
        assert s["codebase"]["imported_by"] == ["lsp"]

    def test_internal_dir_imports_not_recorded(self):
        """lsp/a imports lsp/b → not a dir-level edge."""
        g = _make_graph({
            "lsp/a.py": {"lsp/b.py"},
            "lsp/b.py": set(),
        })
        result = _compute_architecture(g, hotspots=20)
        s = result["structure"]
        assert s["lsp"]["imports"] == []
        assert s["lsp"]["imported_by"] == []

    def test_root_level_files(self):
        """Files at workspace root → excluded from structure."""
        g = _make_graph({
            "root.py": {"lsp/a.py"},
            "lsp/a.py": set(),
        })
        result = _compute_architecture(g, hotspots=20)
        assert result["structure"] == {"lsp": {"files": 1, "imports": [], "imported_by": []}}


# ══════════════════════════════════════════════════════════════════════════════
# transitive counting
# ══════════════════════════════════════════════════════════════════════════════


class TestTransitive:
    def test_chain(self):
        """a←b←c → a has transitive=2, b has transitive=1, c has transitive=0."""
        g = _make_graph({
            "src/a.py": set(),
            "src/b.py": {"src/a.py"},
            "src/c.py": {"src/b.py"},
        })
        result = _compute_architecture(g, hotspots=20)
        hmap = {h["file"]: h for h in result["hotspots"]}
        assert hmap["src/a.py"]["imported_by"] == 1           # b
        assert hmap["src/a.py"]["imported_by_transitive"] == 2  # b + c
        # b has transitive=1 — excluded from hotspots (< 2)
        assert "src/b.py" not in hmap

    def test_diamond(self):
        """a←b, a←c, b←d, c←d → a has transitive=3."""
        g = _make_graph({
            "a.py": set(),
            "b.py": {"a.py"},
            "c.py": {"a.py"},
            "d.py": {"b.py", "c.py"},
        })
        result = _compute_architecture(g, hotspots=20)
        hmap = {h["file"]: h for h in result["hotspots"]}
        assert hmap["a.py"]["imported_by"] == 2              # b + c
        assert hmap["a.py"]["imported_by_transitive"] == 3   # b + c + d

    def test_no_double_counting(self):
        """Same file reached via two paths — counted once."""
        g = _make_graph({
            "a.py": set(),
            "b.py": {"a.py"},
            "c.py": {"a.py"},
            "d.py": {"b.py", "c.py"},
        })
        result = _compute_architecture(g, hotspots=20)
        hmap = {h["file"]: h for h in result["hotspots"]}
        assert hmap["a.py"]["imported_by_transitive"] == 3  # b, c, d (d counted once)


# ══════════════════════════════════════════════════════════════════════════════
# entry points
# ══════════════════════════════════════════════════════════════════════════════


class TestEntryPoints:
    def test_non_imported_files(self):
        """main.py imports others → only main.py is entry point."""
        g = _make_graph({
            "main.py": {"lib/a.py", "lib/b.py"},
            "lib/a.py": set(),
            "lib/b.py": set(),
        })
        result = _compute_architecture(g, hotspots=20)
        assert set(result["entry_points"]) == {"main.py"}

    def test_all_standalone(self):
        """No imports between any files → all non-test are entry points."""
        g = _make_graph({"a.py": set(), "b.py": set(), "c.py": set()})
        result = _compute_architecture(g, hotspots=20)
        assert len(result["entry_points"]) == 3

    def test_sorted_alphabetically(self):
        g = _make_graph({"zzz.py": set(), "aaa.py": set()})
        result = _compute_architecture(g, hotspots=20)
        assert result["entry_points"] == ["aaa.py", "zzz.py"]

    def test_test_files_filtered_out(self):
        """Files matching test convention are excluded from entry points."""
        g = _make_graph({
            "main.py": {"lib/a.py"},
            "lib/a.py": set(),
            "test/test_main.py": set(),          # test file, no dependents
            "tests/unit/test_lib.py": set(),     # test file, no dependents
        })
        result = _compute_architecture(g, hotspots=20)
        assert set(result["entry_points"]) == {"main.py"}


# ══════════════════════════════════════════════════════════════════════════════
# hotspots
# ══════════════════════════════════════════════════════════════════════════════


class TestHotspots:
    def test_filter_below_2(self):
        """transitive < 2 excluded."""
        g = _make_graph({
            "core.py": set(),
            "util.py": {"core.py"},  # core has transitive=1 (util)
        })
        result = _compute_architecture(g, hotspots=20)
        assert result["hotspots"] == []

    def test_transitive_2_included(self):
        """transitive = 2 included."""
        g = _make_graph({
            "a.py": set(),
            "b.py": {"a.py"},
            "c.py": {"b.py"},
        })
        result = _compute_architecture(g, hotspots=20)
        hfiles = {h["file"] for h in result["hotspots"]}
        assert "a.py" in hfiles  # transitive=2

    def test_cap(self):
        """3 eligible, --hotspots 2 → only 2 returned."""
        edges = {}
        for i in range(1, 5):
            edges[f"pkg/f{i}.py"] = {f"pkg/f{i-1}.py"}
        edges["pkg/f0.py"] = set()
        g = _make_graph(edges)
        result = _compute_architecture(g, hotspots=2)
        assert len(result["hotspots"]) == 2

    def test_sorted_by_transitive_desc(self):
        """Highest transitive count first."""
        g = _make_graph({
            "top.py": set(),          # transitive=3
            "mid.py": {"top.py"},     # transitive=2
            "bot.py": {"mid.py"},     # transitive=0
            "bot2.py": {"mid.py"},    # transitive=0
        })
        result = _compute_architecture(g, hotspots=20)
        assert result["hotspots"][0]["file"] == "top.py"


# ══════════════════════════════════════════════════════════════════════════════
# summary
# ══════════════════════════════════════════════════════════════════════════════


class TestSummary:
    def test_counts(self):
        g = _make_graph({
            "lsp/a.py": set(),
            "lsp/b.py": {"codebase/c.py"},
            "codebase/c.py": set(),
        })
        result = _compute_architecture(g, hotspots=20)
        assert result["summary"]["total_files"] == 3
        assert result["summary"]["total_dirs"] == 2

    def test_empty_graph(self):
        g = _make_graph({})
        result = _compute_architecture(g, hotspots=20)
        assert result["summary"]["total_files"] == 0
        assert result["summary"]["total_dirs"] == 0
        assert result["structure"] == {}
        assert result["entry_points"] == []
        assert result["hotspots"] == []
