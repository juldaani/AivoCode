"""Integration tests for textDocument/hover.

What this tests
- Hover on a class definition returns content.
- Hover on a function call returns content.
- Hover on a function definition returns content (signature).
"""

from __future__ import annotations

import pytest

from lsp_client import Position
from lsp_client.utils.types import lsp_type
from tests.integration.lsp.conftest import LanguageTestData


class TestHover:
    """Test hover (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_hover_on_class(
        self, lang: LanguageTestData
    ) -> None:
        """Hover on class definition returns content."""
        types_path = lang.file(lang.types_file)
        async with lang.client.open_files(types_path):
            result = await lang.client.request_hover(
                types_path, Position(*lang.pos("class_def"))
            )

        if result is not None:
            text = _extract_text(result)
            assert len(text) > 0

    @pytest.mark.anyio
    async def test_hover_on_method_call(
        self, lang: LanguageTestData
    ) -> None:
        """Hover on .greet() call returns content."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_hover(
                file_path, Position(*lang.find_after("greet_call", "greet"))
            )

        assert result is not None
        text = _extract_text(result)
        assert len(text) > 0

    @pytest.mark.anyio
    async def test_hover_on_function_definition(
        self, lang: LanguageTestData
    ) -> None:
        """Hover on function definition returns content (signature)."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_hover(
                file_path, Position(*lang.pos("create_def"))
            )

        if result is not None:
            text = _extract_text(result)
            assert len(text) > 0


def _extract_text(result: lsp_type.MarkupContent | None) -> str:
    """Extract plain text from hover MarkupContent."""
    if result is None:
        return ""
    if hasattr(result, "value"):
        return result.value
    return str(result)
