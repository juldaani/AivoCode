"""Unit tests for lsp._symbols module and ground-truth consistency."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lsp._symbols import SYMBOL_KIND_NAMES

# Root of the test data directory containing mock repos.
_MOCK_REPOS_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock_repos"


class TestSymbolKindNames:
    """Test SYMBOL_KIND_NAMES mapping."""

    def test_all_spec_values_present(self) -> None:
        """Every LSP 3.17 SymbolKind value (1-26) has a name."""
        for i in range(1, 27):
            assert i in SYMBOL_KIND_NAMES, f"Missing SymbolKind {i}"

    def test_common_kinds(self) -> None:
        """Spot-check common kind values."""
        assert SYMBOL_KIND_NAMES[1] == "File"
        assert SYMBOL_KIND_NAMES[5] == "Class"
        assert SYMBOL_KIND_NAMES[6] == "Method"
        assert SYMBOL_KIND_NAMES[12] == "Function"
        assert SYMBOL_KIND_NAMES[13] == "Variable"
        assert SYMBOL_KIND_NAMES[14] == "Constant"
        assert SYMBOL_KIND_NAMES[26] == "TypeParameter"

    def test_no_zero_or_negative(self) -> None:
        """Zero and negative values are not in the mapping."""
        assert 0 not in SYMBOL_KIND_NAMES
        assert -1 not in SYMBOL_KIND_NAMES

    def test_total_count(self) -> None:
        """Exactly 26 entries (LSP 3.17 SymbolKind range)."""
        assert len(SYMBOL_KIND_NAMES) == 26

    @pytest.mark.parametrize(
        "kind,expected",
        [
            (5, "Class"),
            (6, "Method"),
            (12, "Function"),
            (13, "Variable"),
            (14, "Constant"),
        ],
    )
    def test_parametrized_kinds(self, kind: int, expected: str) -> None:
        """Parametrized kind name verification."""
        assert SYMBOL_KIND_NAMES[kind] == expected


def _collect_gt_files() -> list[Path]:
    """Collect all ground-truth JSON files in mock repos.

    GT files are named ``*_tests_gt_{server}.json`` where server is the
    language server suffix (e.g. "basedpyright", "vtsls").
    """
    return sorted(_MOCK_REPOS_ROOT.rglob("*_tests_gt_*.json"))


class TestGroundTruthConsistency:
    """Validate ground-truth JSON files against SYMBOL_KIND_NAMES."""

    @pytest.mark.parametrize("gt_path", _collect_gt_files(), ids=lambda p: p.name)
    def test_schema_version_is_3(self, gt_path: Path) -> None:
        """All GT files use schema version 3."""
        data = json.loads(gt_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 3, (
            f"{gt_path.name}: expected schema_version 3, "
            f"got {data.get('schema_version')}"
        )

    @pytest.mark.parametrize("gt_path", _collect_gt_files(), ids=lambda p: p.name)
    def test_kind_categories_match_symbol_kind_names(self, gt_path: Path) -> None:
        """Every kind_category in GT symbols maps to a valid SYMBOL_KIND_NAMES value.

        kind_legend was removed in schema v3. Instead, kind_category strings
        (e.g. "Class", "Method") must be present as values in SYMBOL_KIND_NAMES.
        This test validates that every category used in GT data corresponds to an
        actual LSP SymbolKind.
        """
        data = json.loads(gt_path.read_text(encoding="utf-8"))
        valid_names = set(SYMBOL_KIND_NAMES.values())
        errors: list[str] = []

        def _check_symbols(symbols: list[dict], path: str) -> None:
            for sym in symbols:
                cat = sym.get("kind_category", "")
                if cat not in valid_names:
                    errors.append(
                        f"{path}: kind_category '{cat}' is not a valid "
                        f"SYMBOL_KIND_NAMES value"
                    )
                if sym.get("children"):
                    _check_symbols(sym["children"], f"{path}/{sym['name']}")

        _check_symbols(data.get("symbols", []), gt_path.name)
        assert not errors, "\n".join(errors)

    @pytest.mark.parametrize("gt_path", _collect_gt_files(), ids=lambda p: p.name)
    def test_hover_must_contain_is_nonempty(self, gt_path: Path) -> None:
        """Every hover entry in GT must have a non-empty must_contain list."""
        data = json.loads(gt_path.read_text(encoding="utf-8"))
        hover = data.get("hover", {})
        for marker, entry in hover.items():
            must_contain = entry.get("must_contain", [])
            assert len(must_contain) > 0, (
                f"{gt_path.name}: hover marker '{marker}' has empty must_contain"
            )

    @pytest.mark.parametrize("gt_path", _collect_gt_files(), ids=lambda p: p.name)
    def test_call_hierarchy_must_include_callees_nonempty(self, gt_path: Path) -> None:
        """Every call_hierarchy entry must have non-empty must_include_callees."""
        data = json.loads(gt_path.read_text(encoding="utf-8"))
        ch = data.get("call_hierarchy", {})
        for marker, entry in ch.items():
            callees = entry.get("must_include_callees", [])
            assert len(callees) > 0, (
                f"{gt_path.name}: call_hierarchy marker '{marker}' has empty "
                f"must_include_callees"
            )
