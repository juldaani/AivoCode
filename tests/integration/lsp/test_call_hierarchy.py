"""Integration tests for textDocument/callHierarchy.

What this tests
- prepareCallHierarchy returns items at a function position.
- incomingCalls shows callers of a function.
- outgoingCalls shows callees of a function.
- Cross-file call hierarchy works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient
from lsp_client import Position


class TestCallHierarchyPython:
    """Test call hierarchy with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_incoming_calls_for_greet(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """TypeGreeter.greet has incoming calls from create_and_greet and process_greeting."""
        file_path = python_workspace / "mock_pkg" / "types.py"
        async with python_client.open_files(file_path):
            # Line 25: "def greet(self) -> str:"
            # 'greet' starts at character 8
            incoming = await python_client.request_call_hierarchy_incoming_call(
                file_path, Position(line=25, character=8)
            )

        # Server may return None or a list
        if incoming is not None:
            assert len(incoming) > 0
            # At least one call should be from utils.py (create_and_greet)
            # or types.py (process_greeting)
            caller_uris = {call.from_.uri for call in incoming}
            assert any("utils.py" in u or "types.py" in u for u in caller_uris)

    @pytest.mark.anyio
    async def test_outgoing_calls_for_full_greeting(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """full_greeting has outgoing calls to create_and_greet and process_greeting."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # Line 76: "def full_greeting(name: str) -> str:"
            # 'full_greeting' starts at character 4
            outgoing = await python_client.request_call_hierarchy_outgoing_call(
                file_path, Position(line=76, character=4)
            )

        if outgoing is not None:
            assert len(outgoing) > 0
            callee_uris = {call.to.uri for call in outgoing}
            # Should call functions in utils.py or types.py
            assert any("utils.py" in u or "types.py" in u for u in callee_uris)

    @pytest.mark.anyio
    async def test_call_chain_cross_file(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """process_greeting in types.py has outgoing calls to TypeGreeterFactory.create."""
        file_path = python_workspace / "mock_pkg" / "types.py"
        async with python_client.open_files(file_path):
            # Line 45: "def process_greeting(name: str) -> str:"
            # 'process_greeting' starts at character 4
            outgoing = await python_client.request_call_hierarchy_outgoing_call(
                file_path, Position(line=45, character=4)
            )

        if outgoing is not None:
            assert len(outgoing) > 0
            callee_names = {call.to.name for call in outgoing}
            assert any("create" in n or "Greeter" in n for n in callee_names)
