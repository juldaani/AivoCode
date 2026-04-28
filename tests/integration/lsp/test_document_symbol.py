"""Integration tests for textDocument/documentSymbol.

What this tests
- documentSymbol returns symbols matching GT structure.
- Class symbols have children matching GT.
- All kind values map to valid SYMBOL_KIND_NAMES categories.
- Server capabilities are stored after init.
- Types file has expected GT symbols.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from lsp import SYMBOL_KIND_NAMES
from tests.integration.lsp.conftest import LanguageTestData


def _collect_names(symbols: Sequence[object], names: set[str] | None = None) -> set[str]:
    """Recursively collect all symbol names from a symbol tree."""
    if names is None:
        names = set()
    for sym in symbols:
        names.add(sym.name)  # type: ignore[union-attr]
        children = getattr(sym, "children", None) or []
        if children:
            _collect_names(children, names)
    return names


def _validate_symbol_kinds(
    symbols: Sequence[object], valid_names: set[str], path: str = ""
) -> list[str]:
    """Recursively validate that kind values map to valid SYMBOL_KIND_NAMES."""
    errors: list[str] = []
    for sym in symbols:
        kind = getattr(sym, "kind", 0)
        name = getattr(sym, "name", "<unknown>")
        if kind < 1 or kind > 26:
            errors.append(f"{path}{name} has invalid kind {kind}")
        else:
            kind_name = SYMBOL_KIND_NAMES.get(kind, "Unknown")
            if kind_name not in valid_names:
                errors.append(
                    f"{path}{name} has kind {kind} ({kind_name})"
                    f" which is not a known SYMBOL_KIND_NAMES value"
                )
        children = getattr(sym, "children", None) or []
        if children:
            errors.extend(
                _validate_symbol_kinds(children, valid_names, f"{path}{name}/")
            )
    return errors


class TestDocumentSymbol:
    """Test documentSymbol (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt.json`` ground truth data.
    """

    @pytest.mark.anyio
    async def test_returns_symbols(
        self, lang: LanguageTestData
    ) -> None:
        """documentSymbol returns GT-specified top-level symbols for the source file."""
        gt = lang.load_gt(lang.src_file)
        gt_top_names = {sym["name"] for sym in gt["symbols"]}

        file_path = lang.file(lang.src_file)
        symbols = await lang.client.request_document_symbol_list(file_path)

        assert symbols is not None
        assert len(symbols) > 0

        # Find each GT class symbol and verify its children.
        for gt_sym in gt["symbols"]:
            if gt_sym["kind_category"] not in ("Class", "Interface"):
                continue
            if not gt_sym.get("children"):
                continue

            server_sym = next(
                (s for s in symbols if s.name == gt_sym["name"]), None
            )
            assert server_sym is not None, (
                f"GT symbol '{gt_sym['name']}' not found in server response. "
                f"Server returned: {sorted(s.name for s in symbols)}"
            )

            server_child_names = {
                c.name for c in (server_sym.children or [])
            }
            gt_child_names = {c["name"] for c in gt_sym["children"]}
            assert gt_child_names.issubset(server_child_names), (
                f"GT children {gt_child_names - server_child_names} not found "
                f"in {gt_sym['name']}'s children. "
                f"Got: {server_child_names}"
            )

    @pytest.mark.anyio
    async def test_kind_values_are_spec_compliant(
        self, lang: LanguageTestData
    ) -> None:
        """All kind values map to valid SYMBOL_KIND_NAMES entries."""
        file_path = lang.file(lang.src_file)
        symbols = await lang.client.request_document_symbol_list(file_path)

        assert symbols is not None
        valid_kind_names = set(SYMBOL_KIND_NAMES.values())
        kind_errors = _validate_symbol_kinds(symbols, valid_kind_names)
        assert not kind_errors, "\n".join(kind_errors)

    @pytest.mark.anyio
    async def test_server_capabilities_stored(
        self, lang: LanguageTestData
    ) -> None:
        """Server capabilities are stored after initialization."""
        assert lang.client.server_capabilities is not None

    @pytest.mark.anyio
    async def test_types_file_has_symbols(
        self, lang: LanguageTestData
    ) -> None:
        """Types file has GT-specified top-level symbols."""
        gt = lang.load_gt(lang.types_file)
        gt_top_names = {sym["name"] for sym in gt["symbols"]}

        types_path = lang.file(lang.types_file)
        symbols = await lang.client.request_document_symbol_list(types_path)

        assert symbols is not None
        assert len(symbols) > 0
        result_names = _collect_names(symbols)
        assert gt_top_names.issubset(result_names), (
            f"GT symbols {gt_top_names - result_names} not found in types "
            f"file symbols. Got: {sorted(result_names)}"
        )