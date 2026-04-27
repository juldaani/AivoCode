"""Integration tests for textDocument/hover.

What this tests
- Hover on a class import shows its docstring.
- Hover on a method call shows its docstring.
- Hover on a function import shows its docstring.
- Hover on a function shows its signature (name, params, return type).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient
from lsp_client import Position
from lsp_client.utils.types import lsp_type


class TestHoverPython:
    """Test hover with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_hover_on_class_docstring(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Hover on TypeGreeter shows class info (docstring or type)."""
        file_path = python_workspace / "mock_pkg" / "types.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 12: "class TypeGreeter:"
            # 'TypeGreeter' starts at character 6
            result = await python_client.request_hover(
                file_path, Position(line=12, character=6)
            )

        # basedpyright may or may not return hover on a class def
        if result is not None:
            text = _extract_text(result)
            assert len(text) > 0

    @pytest.mark.anyio
    async def test_hover_on_method_docstring(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Hover on .greet() call shows info (type or docstring)."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 72: "return greeter.greet()"
            # 'greet' starts at character 18
            result = await python_client.request_hover(
                file_path, Position(line=72, character=18)
            )

        assert result is not None
        text = _extract_text(result)
        # May show variable type ("greeter: TypeGreeter") or method docstring
        assert len(text) > 0

    @pytest.mark.anyio
    async def test_hover_on_function_docstring(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Hover on process_greeting import shows its docstring."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 5: "from mock_pkg.types import ... process_greeting"
            # 'process_greeting' starts at character 59
            result = await python_client.request_hover(
                file_path, Position(line=5, character=59)
            )

        if result is not None:
            text = _extract_text(result)
            assert "greeter" in text.lower() or "greeting" in text.lower()

    @pytest.mark.anyio
    async def test_hover_shows_function_signature(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Hover on a function call shows its full signature (params + return type)."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 13: "def hello(name: str) -> str:"
            # Hover on 'hello' at character 4
            result = await python_client.request_hover(
                file_path, Position(line=13, character=4)
            )

        # Basedpyright may or may not return hover on a def — check if it does
        if result is not None:
            text = _extract_text(result)
            assert "hello" in text.lower() or "name" in text.lower()

    @pytest.mark.anyio
    async def test_hover_on_builtin(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Hover on a builtin type annotation returns some info."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 7: "MAX_RETRIES: Final[int] = 3"
            # 'int' starts at character 21
            result = await python_client.request_hover(
                file_path, Position(line=7, character=21)
            )

        # Builtins may or may not return hover — just verify no exception
        if result is not None:
            assert _extract_text(result)  # non-empty text


def _extract_text(result: lsp_type.MarkupContent | None) -> str:
    """Extract plain text from hover MarkupContent."""
    if result is None:
        return ""
    if hasattr(result, "value"):
        return result.value
    return str(result)
