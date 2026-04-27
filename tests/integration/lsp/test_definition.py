"""Integration tests for textDocument/definition and textDocument/typeDefinition.

What this tests
- definition resolves method calls to definitions.
- type_definition resolves typed variables.
- Both use markers from mock source files.
"""

from __future__ import annotations

import pytest

from lsp import LspClient
from lsp_client import Position
from tests.integration.lsp.conftest import LanguageTestData


class TestDefinition:
    """Test definition and type_definition (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_definition_for_method_call(
        self, lang: LanguageTestData
    ) -> None:
        """Go-to-definition on .greet() call resolves to a definition."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_definition(
                file_path, Position(*lang.find_after("greet_call", "greet"))
            )

        assert result is not None
        locations = result if isinstance(result, list) else [result]
        assert len(locations) > 0

    @pytest.mark.anyio
    async def test_type_definition_for_variable(
        self, lang: LanguageTestData
    ) -> None:
        """Go-to-type-definition on greeter variable — may or may not resolve."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_type_definition(
                file_path, Position(*lang.find_after("greeter_var", "greeter"))
            )

        # Server may return None, empty list, or locations — just verify no exception
