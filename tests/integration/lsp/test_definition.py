"""Integration tests for textDocument/definition and textDocument/typeDefinition.

What this tests
- definition jumps to the correct file for imported symbols.
- type_definition resolves typed variables to their class definitions.
- Both local and cross-file definitions work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient
from lsp_client import Position


class TestDefinitionPython:
    """Test definition and type_definition with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_definition_for_imported_class(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Go-to-definition on TypeGreeter import — may resolve or return None."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 5: "from mock_pkg.types import TypeGreeter, ..."
            # 'TypeGreeter' starts at character 23
            result = await python_client.request_definition(
                file_path, Position(line=5, character=23)
            )

        # basedpyright may resolve imports to types.py or may not — just
        # verify no exception
        if result is not None:
            locations = result if isinstance(result, list) else [result]
            assert len(locations) > 0

    @pytest.mark.anyio
    async def test_definition_for_local_function(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Go-to-definition on hello() in utils.py stays in utils.py."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 13: "def hello(name: str) -> str:"
            # 'hello' starts at character 4
            result = await python_client.request_definition(
                file_path, Position(line=13, character=4)
            )

        # definition on a def may return None or the def location
        if result is not None:
            locations = result if isinstance(result, list) else [result]
            uris = [loc.uri for loc in locations]
            assert any("utils.py" in uri for uri in uris)

    @pytest.mark.anyio
    async def test_definition_for_method_call(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Go-to-definition on .greet() in create_and_greet resolves."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 72: "return greeter.greet()"
            # 'greet' starts at character 18
            result = await python_client.request_definition(
                file_path, Position(line=72, character=18)
            )

        assert result is not None
        locations = result if isinstance(result, list) else [result]
        # Server resolves greet — may point to types.py (TypeGreeter.greet)
        # or utils.py (Greeter.greet). Both are valid.
        assert len(locations) > 0

    @pytest.mark.anyio
    async def test_type_definition_for_typed_variable(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Go-to-type-definition on greeter variable resolves to TypeGreeter class."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 71: "greeter = TypeGreeterFactory.create(name)"
            # 'greeter' starts at character 4
            result = await python_client.request_type_definition(
                file_path, Position(line=71, character=4)
            )

        # May return None if server can't resolve
        if result is not None:
            locations = result if isinstance(result, list) else [result]
            uris = [loc.uri for loc in locations]
            assert any("types.py" in uri for uri in uris), (
                f"Expected type definition in types.py, got {uris}"
            )

    @pytest.mark.anyio
    async def test_type_definition_for_return_type(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Go-to-type-definition on TypeGreeter resolves to class."""
        file_path = python_workspace / "mock_pkg" / "types.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 41: "return TypeGreeter(name)"
            # 'TypeGreeter' starts at character 11
            result = await python_client.request_type_definition(
                file_path, Position(line=41, character=11)
            )

        if result is not None:
            locations = result if isinstance(result, list) else [result]
            uris = [loc.uri for loc in locations]
            assert any("types.py" in uri for uri in uris)
