"""Unit tests for lsp._symbols module."""

from __future__ import annotations

import pytest

from lsp._symbols import SYMBOL_KIND_NAMES


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
