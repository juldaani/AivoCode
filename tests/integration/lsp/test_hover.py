"""Integration tests for textDocument/hover.

What this tests
- Hover on a class definition returns content containing the class name (GT).
- Hover on a function call returns content containing the function name (GT).
- Hover on a function definition returns content containing the function name (GT).
"""

from __future__ import annotations

import pytest

from lsp_client import Position
from lsp_client.utils.types import lsp_type
from tests.integration.lsp.conftest import LanguageTestData


def _extract_text(result: lsp_type.MarkupContent | None) -> str:
    """Extract plain text from hover MarkupContent."""
    if result is None:
        return ""
    if hasattr(result, "value"):
        return result.value
    return str(result)


class TestHover:
    """Test hover (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt.json`` ground truth data.
    Hover GT entries specify ``must_contain`` substrings that must appear
    in the hover text.
    """

    @pytest.mark.anyio
    async def test_hover_on_class(
        self, lang: LanguageTestData
    ) -> None:
        """Hover on class definition — content must contain GT-specified name."""
        gt = lang.load_gt(lang.types_file)
        must_contain = gt["hover"]["class_def"]["must_contain"]

        types_path = lang.file(lang.types_file)
        async with lang.client.open_files(types_path):
            result = await lang.client.request_hover(
                types_path, Position(*lang.pos("class_def"))
            )

        text = _extract_text(result)
        assert len(text) > 0, "Hover on class_def returned empty text"
        for expected in must_contain:
            assert expected in text, (
                f"Expected '{expected}' in hover text, got: {text[:200]}"
            )

    @pytest.mark.anyio
    async def test_hover_on_method_call(
        self, lang: LanguageTestData
    ) -> None:
        """Hover on .greet() call — content must contain GT-specified name."""
        gt = lang.load_gt(lang.src_file)
        must_contain = gt["hover"]["greet_call"]["must_contain"]

        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_hover(
                file_path, Position(*lang.find_after("greet_call", "greet"))
            )

        assert result is not None, "Hover on greet_call returned None"
        text = _extract_text(result)
        assert len(text) > 0, "Hover on greet_call returned empty text"
        for expected in must_contain:
            assert expected in text, (
                f"Expected '{expected}' in hover text, got: {text[:200]}"
            )

    @pytest.mark.anyio
    async def test_hover_on_function_definition(
        self, lang: LanguageTestData
    ) -> None:
        """Hover on function definition — content must contain GT-specified name."""
        gt = lang.load_gt(lang.src_file)
        must_contain = gt["hover"]["create_def"]["must_contain"]

        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_hover(
                file_path, Position(*lang.pos("create_def"))
            )

        assert result is not None, (
            f"Hover returned None for function definition in {lang.name}"
        )
        text = _extract_text(result)
        assert len(text) > 0, "Hover on create_def returned empty text"
        for expected in must_contain:
            assert expected in text, (
                f"Expected '{expected}' in hover text, got: {text[:200]}"
            )
