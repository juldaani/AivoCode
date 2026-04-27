"""Integration tests for textDocument/documentSymbol.

What this tests
- documentSymbol returns non-empty list for source files.
- Class symbols have children (methods).
- All kind values are in the LSP spec range (1-26).
- Server capabilities are stored after init.
- Types file has expected symbols.
"""

from __future__ import annotations

import pytest

from tests.integration.lsp.conftest import LanguageTestData


class TestDocumentSymbol:
    """Test documentSymbol (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_returns_symbols(
        self, lang: LanguageTestData
    ) -> None:
        """documentSymbol returns non-empty list for the source file."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            symbols = await lang.client.request_document_symbol_list(file_path)

        assert symbols is not None
        assert len(symbols) > 0

    @pytest.mark.anyio
    async def test_class_has_children(
        self, lang: LanguageTestData
    ) -> None:
        """Class/interface symbols have method children."""
        types_path = lang.file(lang.types_file)
        async with lang.client.open_files(types_path):
            symbols = await lang.client.request_document_symbol_list(types_path)

        assert symbols is not None
        assert len(symbols) > 0
        # Find a class/interface symbol specifically. Some servers also report
        # function-local variables as children, so "has children" alone can
        # accidentally select a function symbol instead of the type under test.
        class_sym = next(
            (
                s
                for s in symbols
                if s.kind in {5, 11}
                and s.children is not None
                and len(s.children) > 0
            ),
            None,
        )
        assert class_sym is not None, "No class with children found"
        assert class_sym.children is not None
        child_names = {c.name for c in class_sym.children}
        assert "greet" in child_names

    @pytest.mark.anyio
    async def test_kind_values_are_spec_compliant(
        self, lang: LanguageTestData
    ) -> None:
        """All kind values are in the LSP spec SymbolKind range (1-26)."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            symbols = await lang.client.request_document_symbol_list(file_path)

        assert symbols is not None
        for sym in symbols:
            assert 1 <= sym.kind <= 26, f"{sym.name} has invalid kind {sym.kind}"

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
        """Types file has expected symbols."""
        types_path = lang.file(lang.types_file)
        async with lang.client.open_files(types_path):
            symbols = await lang.client.request_document_symbol_list(types_path)

        assert symbols is not None
        assert len(symbols) > 0
        names = {sym.name for sym in symbols}
        # Both Python (types.py) and TypeScript (types.ts) have a class with greet
        assert len(names) > 0
