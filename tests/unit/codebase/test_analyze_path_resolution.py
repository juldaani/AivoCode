"""Unit tests for path resolution in codebase/_analyze.py.

Bug #1: Relative paths in LSP commands were resolved against the server's
CWD instead of the workspace root, causing "not a valid workspace file path"
errors when using relative paths.

These tests verify that relative paths are correctly resolved against the
workspace root, not the current working directory.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codebase._analyze import (
    _definition,
    _diagnostics,
    _explain,
    _hover,
    _impact,
    _incoming_calls,
    _outgoing_calls,
    _overview,
    _references,
)
from codebase._resolve import ResolvedSymbol


def _make_symbol() -> ResolvedSymbol:
    """Create a minimal ResolvedSymbol for testing."""
    return ResolvedSymbol(
        name="test_func",
        kind="Function",
        line=10,
        character=0,
        range_start=(10, 0),
        range_end=(15, 0),
        children=[],
        lsp_server="test-server",
        language="python",
    )


class TestRelativePathResolution:
    """Verify relative paths are resolved against workspace, not CWD.

    Bug #1: All _analyze.py functions used ``Path(file_path).resolve()``
    which resolves relative to the Python process CWD. When the server
    runs in a container with CWD=/aivocode, a relative path like
    ``cli/commands/codebase.py`` becomes ``/aivocode/cli/commands/codebase.py``
    instead of ``/workspaces/AivoCode/cli/commands/codebase.py``.

    The fix: resolve relative paths against the workspace root.
    """

    @pytest.mark.anyio
    async def test_overview_resolves_relative_path(self, tmp_path):
        """``_overview`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()

        # Mock the LSP query to capture what path it receives
        captured_path = None

        async def mock_query(fp, *, workspace=None):
            nonlocal captured_path
            captured_path = fp
            return {"symbols": [], "server": "test", "language": "python"}

        with patch("lsp.query_document_symbols", side_effect=mock_query):
            with patch("lsp.detect_workspace", return_value=ws):
                # Change CWD to a different directory to simulate the bug
                original_cwd = Path.cwd()
                try:
                    import os
                    os.chdir("/tmp")
                    await _overview("src/module.py", workspace=ws)
                finally:
                    os.chdir(original_cwd)

        # The path should be resolved against workspace, not CWD
        assert captured_path is not None
        assert captured_path == source_file.resolve()
        assert str(captured_path).startswith(str(ws.resolve()))

    @pytest.mark.anyio
    async def test_incoming_calls_resolves_relative_path(self, tmp_path):
        """``_incoming_calls`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()
        captured_path = None

        async def mock_query(fp, *, line, character, workspace):
            nonlocal captured_path
            captured_path = fp
            return {"result": [], "server": "test", "language": "python"}

        with patch("lsp.query_call_hierarchy_incoming", side_effect=mock_query):
            with patch("lsp.detect_workspace", return_value=ws):
                original_cwd = Path.cwd()
                try:
                    import os
                    os.chdir("/tmp")
                    await _incoming_calls(symbol, "src/module.py", workspace=ws)
                finally:
                    os.chdir(original_cwd)

        assert captured_path is not None
        assert captured_path == source_file.resolve()

    @pytest.mark.anyio
    async def test_outgoing_calls_resolves_relative_path(self, tmp_path):
        """``_outgoing_calls`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()
        captured_path = None

        async def mock_query(fp, *, line, character, workspace):
            nonlocal captured_path
            captured_path = fp
            return {"result": [], "server": "test", "language": "python"}

        with patch("lsp.query_call_hierarchy_outgoing", side_effect=mock_query):
            with patch("lsp.detect_workspace", return_value=ws):
                original_cwd = Path.cwd()
                try:
                    import os
                    os.chdir("/tmp")
                    await _outgoing_calls(symbol, "src/module.py", workspace=ws)
                finally:
                    os.chdir(original_cwd)

        assert captured_path is not None
        assert captured_path == source_file.resolve()

    @pytest.mark.anyio
    async def test_references_resolves_relative_path(self, tmp_path):
        """``_references`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()
        captured_path = None

        async def mock_query(fp, *, line, character, workspace):
            nonlocal captured_path
            captured_path = fp
            return {"result": [], "server": "test", "language": "python"}

        with patch("lsp.query_references", side_effect=mock_query):
            with patch("lsp.detect_workspace", return_value=ws):
                original_cwd = Path.cwd()
                try:
                    import os
                    os.chdir("/tmp")
                    await _references(symbol, "src/module.py", workspace=ws)
                finally:
                    os.chdir(original_cwd)

        assert captured_path is not None
        assert captured_path == source_file.resolve()

    @pytest.mark.anyio
    async def test_explain_resolves_relative_path(self, tmp_path):
        """``_explain`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()
        captured_paths = []

        def mock_read_range(fp, start, end):
            captured_paths.append(("read_range", fp))
            return "def foo(): pass"

        async def mock_definition(sym, fp, workspace):
            captured_paths.append(("definition", fp))
            return {"definers": [], "type_definition": []}

        async def mock_incoming(sym, fp, workspace):
            captured_paths.append(("incoming", fp))
            return []

        async def mock_outgoing(sym, fp, workspace):
            captured_paths.append(("outgoing", fp))
            return []

        async def mock_refs(sym, fp, workspace):
            captured_paths.append(("refs", fp))
            return []

        with patch("codebase._analyze.read_range", side_effect=mock_read_range):
            with patch("codebase._analyze._definition", side_effect=mock_definition):
                with patch("codebase._analyze._incoming_calls", side_effect=mock_incoming):
                    with patch("codebase._analyze._outgoing_calls", side_effect=mock_outgoing):
                        with patch("codebase._analyze._references", side_effect=mock_refs):
                            with patch("lsp.detect_workspace", return_value=ws):
                                original_cwd = Path.cwd()
                                try:
                                    import os
                                    os.chdir("/tmp")
                                    await _explain(symbol, "src/module.py", workspace=ws)
                                finally:
                                    os.chdir(original_cwd)

        # All internal calls should receive the workspace-resolved path
        for call_name, fp in captured_paths:
            assert fp == source_file.resolve(), f"{call_name} got {fp}, expected {source_file.resolve()}"

    @pytest.mark.anyio
    async def test_impact_resolves_relative_path(self, tmp_path):
        """``_impact`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()
        captured_paths = []

        async def mock_incoming(sym, fp, workspace):
            captured_paths.append(("incoming", fp))
            return []

        async def mock_outgoing(sym, fp, workspace):
            captured_paths.append(("outgoing", fp))
            return []

        async def mock_refs(sym, fp, workspace):
            captured_paths.append(("refs", fp))
            return []

        async def mock_query_dependents(fp, *, depth, workspace):
            captured_paths.append(("dependents", fp))
            return {"dependents": []}

        with patch("codebase._analyze._incoming_calls", side_effect=mock_incoming):
            with patch("codebase._analyze._outgoing_calls", side_effect=mock_outgoing):
                with patch("codebase._analyze._references", side_effect=mock_refs):
                    with patch("lsp.query_import_dependents", side_effect=mock_query_dependents):
                        with patch("lsp.detect_workspace", return_value=ws):
                            original_cwd = Path.cwd()
                            try:
                                import os
                                os.chdir("/tmp")
                                await _impact(symbol, "src/module.py", workspace=ws)
                            finally:
                                os.chdir(original_cwd)

        for call_name, fp in captured_paths:
            assert fp == source_file.resolve(), f"{call_name} got {fp}, expected {source_file.resolve()}"

    @pytest.mark.anyio
    async def test_definition_resolves_relative_path(self, tmp_path):
        """``_definition`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()
        captured_path = None

        async def mock_query_def(fp, *, line, character, workspace):
            nonlocal captured_path
            captured_path = fp
            return {"result": None}

        async def mock_query_type_def(fp, *, line, character, workspace):
            return {"result": None}

        with patch("lsp.query_definition", side_effect=mock_query_def):
            with patch("lsp.query_type_definition", side_effect=mock_query_type_def):
                with patch("lsp.detect_workspace", return_value=ws):
                    original_cwd = Path.cwd()
                    try:
                        import os
                        os.chdir("/tmp")
                        await _definition(symbol, "src/module.py", workspace=ws)
                    finally:
                        os.chdir(original_cwd)

        assert captured_path is not None
        assert captured_path == source_file.resolve()

    @pytest.mark.anyio
    async def test_hover_resolves_relative_path(self, tmp_path):
        """``_hover`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        symbol = _make_symbol()
        captured_path = None

        async def mock_query(fp, *, line, character, workspace):
            nonlocal captured_path
            captured_path = fp
            return {"result": None}

        with patch("lsp.query_hover", side_effect=mock_query):
            with patch("lsp.detect_workspace", return_value=ws):
                original_cwd = Path.cwd()
                try:
                    import os
                    os.chdir("/tmp")
                    await _hover(symbol, "src/module.py", workspace=ws)
                finally:
                    os.chdir(original_cwd)

        assert captured_path is not None
        assert captured_path == source_file.resolve()

    @pytest.mark.anyio
    async def test_diagnostics_resolves_relative_path(self, tmp_path):
        """``_diagnostics`` with relative path resolves against workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        source_file = ws / "src" / "module.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("def foo(): pass\n")

        captured_path = None

        async def mock_query(fp, *, workspace):
            nonlocal captured_path
            captured_path = fp
            return {"diagnostics": [], "server": "test", "language": "python"}

        with patch("lsp.query_diagnostics", side_effect=mock_query):
            with patch("lsp.detect_workspace", return_value=ws):
                original_cwd = Path.cwd()
                try:
                    import os
                    os.chdir("/tmp")
                    await _diagnostics("src/module.py", workspace=ws)
                finally:
                    os.chdir(original_cwd)

        assert captured_path is not None
        assert captured_path == source_file.resolve()

    @pytest.mark.anyio
    async def test_absolute_path_unchanged(self, tmp_path):
        """Absolute paths should be used as-is (not re-resolved)."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        abs_path = ws / "src" / "module.py"
        abs_path.parent.mkdir(parents=True)
        abs_path.write_text("def foo(): pass\n")

        captured_path = None

        async def mock_query(fp, *, workspace):
            nonlocal captured_path
            captured_path = fp
            return {"diagnostics": [], "server": "test", "language": "python"}

        with patch("lsp.query_diagnostics", side_effect=mock_query):
            with patch("lsp.detect_workspace", return_value=ws):
                await _diagnostics(str(abs_path), workspace=ws)

        assert captured_path == abs_path.resolve()
