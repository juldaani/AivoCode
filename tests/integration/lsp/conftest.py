"""Pytest configuration for LSP integration tests.

What this file provides
- Fixtures for creating LspClient instances with real language servers.
- Auto-skips tests if the configured language server is not on PATH.
- Provides a temporary workspace copy for isolated testing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lsp import LspClient, LanguageEntry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def python_language_entry() -> LanguageEntry:
    """Return a LanguageEntry for Python (basedpyright)."""
    return LanguageEntry(
        name="python",
        suffixes=(".py", ".pyi"),
        server="basedpyright-langserver",
        server_args=("--stdio",),
    )


@pytest.fixture
def typescript_language_entry() -> LanguageEntry:
    """Return a LanguageEntry for TypeScript."""
    return LanguageEntry(
        name="typescript",
        suffixes=(".ts", ".tsx"),
        server="typescript-language-server",
        server_args=("--stdio",),
    )


@pytest.fixture
def python_workspace(tmp_path: Path) -> Path:
    """Copy Python mock repo to a temp workspace."""
    src = _repo_root() / "tests" / "data" / "mock_repos" / "python"
    dst = tmp_path / "python"
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
def typescript_workspace(tmp_path: Path) -> Path:
    """Copy TypeScript mock repo to a temp workspace."""
    src = _repo_root() / "tests" / "data" / "mock_repos" / "typescript"
    dst = tmp_path / "typescript"
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
async def python_client(
    python_language_entry: LanguageEntry, python_workspace: Path
) -> LspClient:
    """Yield a started LspClient for Python.

    Skips if basedpyright-langserver is not installed.
    """
    import anyio

    # Check server availability
    try:
        client = LspClient(lang_entry=python_language_entry, workspace=python_workspace)
        await client.__aenter__()
    except Exception as exc:
        pytest.skip(f"basedpyright-langserver not available: {exc}")
    yield client
    await client.shutdown()


@pytest.fixture
async def typescript_client(
    typescript_language_entry: LanguageEntry, typescript_workspace: Path
) -> LspClient:
    """Yield a started LspClient for TypeScript.

    Skips if typescript-language-server is not installed.
    """
    try:
        client = LspClient(
            lang_entry=typescript_language_entry, workspace=typescript_workspace
        )
        await client.__aenter__()
    except Exception as exc:
        pytest.skip(f"typescript-language-server not available: {exc}")
    yield client
    await client.shutdown()
