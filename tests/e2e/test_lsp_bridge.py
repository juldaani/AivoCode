"""End-to-end test: file_watcher + LspClient bridge.

What this tests
- The full flow: file system change → WatchBatch →
  LspClient.notify_file_changes() → LSP server update.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import anyio
import pytest
from watchfiles import Change

from file_watcher.types import WatchBatch, WatchEvent
from lsp import LspClient, LanguageEntry


class TestLspBridge:
    """E2E test for file_watcher → LspClient integration."""

    @pytest.mark.anyio
    async def test_file_change_propagates_to_lsp(
        self, tmp_path: Path
    ) -> None:
        """A WatchBatch sent to LspClient updates the server state.

        Instead of relying on the real file watcher (timing-sensitive),
        we construct a WatchBatch manually and send it through the bridge.
        Then verify the server knows about the new file.
        """
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        pkg_dir = workspace / "mock_pkg"
        pkg_dir.mkdir()

        (workspace / "pyproject.toml").write_text(
            "[tool.pyright]\ninclude = ['mock_pkg']\npythonVersion = '3.12'\n",
            encoding="utf-8",
        )

        # Create file BEFORE starting client so server indexes it
        new_file = pkg_dir / "new_module.py"
        new_file.write_text(
            "def bridge_func():\n    return 42\n", encoding="utf-8"
        )

        entry = LanguageEntry(
            name="python",
            suffixes=(".py", ".pyi"),
            server="basedpyright-langserver",
            server_args=("--stdio",),
        )

        client = LspClient(lang_entry=entry, workspace=workspace)
        await client.__aenter__()

        try:
            # Construct WatchBatch manually (as if from file_watcher)
            batch = WatchBatch(
                ts=datetime.now(),
                raw=1,
                filtered=1,
                events=[
                    WatchEvent(
                        change=Change.added,
                        abs_path=new_file,
                        repo_root=workspace,
                        repo_label="workspace",
                        rel_path="mock_pkg/new_module.py",
                    )
                ],
            )

            # Send through the bridge
            await client.notify_file_changes(batch)
            await anyio.sleep(0.3)

            # Verify server knows about the new file
            symbols = await client.request_document_symbol_list(new_file)

            assert symbols is not None, "Expected symbols for new_module.py"
            names = {sym.name for sym in symbols}
            assert "bridge_func" in names, f"Expected bridge_func in {names}"

        finally:
            await client.shutdown()

    @pytest.mark.anyio
    async def test_suffix_filtering_in_bridge(
        self, tmp_path: Path
    ) -> None:
        """Only .py events reach Python LspClient; .md events are filtered."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        pkg_dir = workspace / "mock_pkg"
        pkg_dir.mkdir()

        (workspace / "pyproject.toml").write_text(
            "[tool.pyright]\ninclude = ['mock_pkg']\npythonVersion = '3.12'\n",
            encoding="utf-8",
        )

        py_file = pkg_dir / "script.py"
        md_file = pkg_dir / "README.md"
        py_file.write_text("def py_func(): pass\n", encoding="utf-8")
        md_file.write_text("# Hello\n", encoding="utf-8")

        entry = LanguageEntry(
            name="python",
            suffixes=(".py",),
            server="basedpyright-langserver",
            server_args=("--stdio",),
        )

        client = LspClient(lang_entry=entry, workspace=workspace)
        await client.__aenter__()

        try:
            # Batch with both .py and .md events
            batch = WatchBatch(
                ts=datetime.now(),
                raw=2,
                filtered=2,
                events=[
                    WatchEvent(
                        change=Change.added,
                        abs_path=py_file,
                        repo_root=workspace,
                        repo_label="workspace",
                        rel_path="mock_pkg/script.py",
                    ),
                    WatchEvent(
                        change=Change.added,
                        abs_path=md_file,
                        repo_root=workspace,
                        repo_label="workspace",
                        rel_path="mock_pkg/README.md",
                    ),
                ],
            )

            await client.notify_file_changes(batch)
            await anyio.sleep(0.3)

            # Python file should be known
            symbols = await client.request_document_symbol_list(py_file)
            assert symbols is not None, "Expected symbols for script.py"
            assert "py_func" in {sym.name for sym in symbols}

        finally:
            await client.shutdown()
