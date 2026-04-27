"""Pytest configuration for LSP integration tests.

What this file provides
- Module-scoped fixtures for LspClient (one server process per module).
- Module-scoped workspace copies for isolated file operations.
- Auto-skips tests if the configured language server is not on PATH.

Why module-scoped
- Starting basedpyright-langserver takes ~2-3s (subprocess spawn + init handshake).
- With 13 integration tests, function-scoped would cost ~30-40s just on startup.
- Module-scoped reuses one server process across all tests in the module.
- Tests use unique file names so they don't interfere with each other.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest

from lsp import LspClient, LanguageEntry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def python_language_entry() -> LanguageEntry:
    """Return a LanguageEntry for Python (basedpyright)."""
    return LanguageEntry(
        name="python",
        suffixes=(".py", ".pyi"),
        server="basedpyright-langserver",
        server_args=("--stdio",),
    )


@pytest.fixture(scope="module")
def typescript_language_entry() -> LanguageEntry:
    """Return a LanguageEntry for TypeScript."""
    return LanguageEntry(
        name="typescript",
        suffixes=(".ts", ".tsx"),
        server="typescript-language-server",
        server_args=("--stdio",),
    )


@pytest.fixture(scope="module")
def python_workspace() -> Path:
    """Copy Python mock repo to a module-scoped temp workspace."""
    src = _repo_root() / "tests" / "data" / "mock_repos" / "python"
    dst = Path(tempfile.mkdtemp(prefix="lsp_python_"))
    shutil.copytree(src, dst / "python")
    return dst / "python"


@pytest.fixture(scope="module")
def typescript_workspace() -> Path:
    """Copy TypeScript mock repo to a module-scoped temp workspace."""
    src = _repo_root() / "tests" / "data" / "mock_repos" / "typescript"
    dst = Path(tempfile.mkdtemp(prefix="lsp_typescript_"))
    shutil.copytree(src, dst / "typescript")
    return dst / "typescript"


@pytest.fixture(scope="module")
async def python_client(
    python_language_entry: LanguageEntry, python_workspace: Path
) -> AsyncGenerator[LspClient, None]:
    """Yield a started LspClient for Python (module-scoped).

    Skips if basedpyright-langserver is not installed.
    The client is started once per test module and shut down after
    all tests in the module complete.
    """
    try:
        client = LspClient(
            lang_entry=python_language_entry, workspace=python_workspace
        )
        await client.__aenter__()
    except Exception as exc:
        pytest.skip(f"basedpyright-langserver not available: {exc}")
    yield client
    await client.shutdown()


@pytest.fixture(scope="module")
async def typescript_client(
    typescript_language_entry: LanguageEntry, typescript_workspace: Path
) -> AsyncGenerator[LspClient, None]:
    """Yield a started LspClient for TypeScript (module-scoped).

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
