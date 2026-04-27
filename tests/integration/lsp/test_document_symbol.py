"""Integration tests for textDocument/documentSymbol."""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient
from lsp._symbols import SYMBOL_KIND_NAMES


class TestDocumentSymbolPython:
    """Test documentSymbol with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_returns_symbols_for_utils_py(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """documentSymbol returns non-empty list for utils.py."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            symbols = await python_client.request_document_symbol_list(file_path)

        assert symbols is not None
        assert len(symbols) > 0

    @pytest.mark.anyio
    async def test_symbol_names_match_expected(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Symbol names match expected functions/classes/constants."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            symbols = await python_client.request_document_symbol_list(file_path)

        assert symbols is not None
        names = {sym.name for sym in symbols}
        assert "Greeter" in names
        assert "hello" in names
        assert "MAX_RETRIES" in names

    @pytest.mark.anyio
    async def test_class_has_children(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Class symbols have method children."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            symbols = await python_client.request_document_symbol_list(file_path)

        assert symbols is not None
        greeter = next((s for s in symbols if s.name == "Greeter"), None)
        assert greeter is not None, "Greeter class not found"
        assert greeter.children is not None and len(greeter.children) > 0

    @pytest.mark.anyio
    async def test_kind_values_are_spec_compliant(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """All kind values are in the LSP spec SymbolKind range (1-26)."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            symbols = await python_client.request_document_symbol_list(file_path)

        assert symbols is not None
        for sym in symbols:
            assert 1 <= sym.kind <= 26, f"{sym.name} has invalid kind {sym.kind}"

    @pytest.mark.anyio
    async def test_server_capabilities_stored(
        self, python_client: LspClient
    ) -> None:
        """Server capabilities are stored after initialization."""
        assert python_client.server_capabilities is not None

    @pytest.mark.anyio
    async def test_document_symbol_for_init_py(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """documentSymbol works for __init__.py too."""
        file_path = python_workspace / "mock_pkg" / "__init__.py"
        async with python_client.open_files(file_path):
            symbols = await python_client.request_document_symbol_list(file_path)

        # __init__.py may be empty or have re-exports; just check no error
        assert symbols is not None

    @pytest.mark.anyio
    async def test_types_file_has_symbols(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """documentSymbol returns symbols for types.py."""
        file_path = python_workspace / "mock_pkg" / "types.py"
        async with python_client.open_files(file_path):
            symbols = await python_client.request_document_symbol_list(file_path)

        assert symbols is not None
        assert len(symbols) > 0
        names = {sym.name for sym in symbols}
        assert "TypeGreeter" in names
        assert "TypeGreeterFactory" in names
        assert "process_greeting" in names

    @pytest.mark.anyio
    async def test_types_file_class_hierarchy(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """TypeGreeter in types.py has __init__ and greet as children."""
        file_path = python_workspace / "mock_pkg" / "types.py"
        async with python_client.open_files(file_path):
            symbols = await python_client.request_document_symbol_list(file_path)

        assert symbols is not None
        greeter = next((s for s in symbols if s.name == "TypeGreeter"), None)
        assert greeter is not None, "TypeGreeter class not found"
        assert greeter.children is not None and len(greeter.children) > 0
        child_names = {c.name for c in greeter.children}
        assert "greet" in child_names


class TestDocumentSymbolTypeScript:
    """Test documentSymbol with TypeScript (skipped if server unavailable)."""

    @pytest.mark.anyio
    async def test_returns_symbols(
        self, typescript_client: LspClient, typescript_workspace: Path
    ) -> None:
        """documentSymbol returns non-empty list for TypeScript file."""
        file_path = typescript_workspace / "mock_pkg" / "index.ts"
        async with typescript_client.open_files(file_path):
            symbols = await typescript_client.request_document_symbol_list(file_path)

        assert symbols is not None
        assert len(symbols) > 0
        names = {sym.name for sym in symbols}
        assert "Greeter" in names or "createGreeter" in names or "MAX_ITEMS" in names
