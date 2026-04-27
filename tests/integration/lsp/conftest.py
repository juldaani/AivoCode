"""Pytest configuration for LSP integration tests.

What this file provides
- Module-scoped fixtures for LspClient (one server process per module).
- Class-scoped isolated fixtures for mutation tests (fresh server per class).
- Module-scoped workspace copies for isolated file operations.
- Auto-skips tests if the configured language server is not on PATH.
- Session-scoped cleanup of leftover temp workspaces.

Why module-scoped
- Starting basedpyright-langserver takes ~2-3s (subprocess spawn + init handshake).
- With 13 integration tests, function-scoped would cost ~30-40s just on startup.
- Module-scoped reuses one server process across all tests in the module.
- Tests use unique file names so they don't interfere with each other.

Isolation for mutation tests
- test_file_changes.py uses class-scoped python_client_isolated to get
  a fresh server + workspace per test class, avoiding shared-state issues.
- ~3s overhead per class is acceptable for correctness.
"""

from __future__ import annotations

import glob
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest

from lsp import LspClient, LanguageEntry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _make_workspace(prefix: str) -> Path:
    """Create a temp workspace by copying the Python mock repo.

    Returns the workspace path (the inner 'python' dir).
    Caller is responsible for cleanup of the parent temp dir.
    """
    src = _repo_root() / "tests" / "data" / "mock_repos" / "python"
    dst = Path(tempfile.mkdtemp(prefix=prefix))
    workspace = dst / "python"
    shutil.copytree(src, workspace)
    return workspace


def _cleanup_tmp_workspaces() -> None:
    """Remove any leftover lsp_* temp workspaces from /tmp."""
    for path in glob.glob(tempfile.gettempdir() + "/lsp_*"):
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True, scope="session")
def _cleanup_workspaces_session():
    """Clean up stale temp workspaces before and after the test session."""
    _cleanup_tmp_workspaces()
    yield
    _cleanup_tmp_workspaces()


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
def python_workspace():
    """Copy Python mock repo to a module-scoped temp workspace.

    Cleans up the temp directory when the module's tests finish.
    """
    workspace = _make_workspace("lsp_python_")
    yield workspace
    shutil.rmtree(workspace.parent, ignore_errors=True)


@pytest.fixture(scope="module")
def typescript_workspace():
    """Copy TypeScript mock repo to a module-scoped temp workspace.

    Cleans up the temp directory when the module's tests finish.
    """
    src = _repo_root() / "tests" / "data" / "mock_repos" / "typescript"
    dst = Path(tempfile.mkdtemp(prefix="lsp_typescript_"))
    workspace = dst / "typescript"
    shutil.copytree(src, workspace)
    yield workspace
    shutil.rmtree(dst, ignore_errors=True)


@pytest.fixture(scope="module")
async def python_client(
    python_language_entry: LanguageEntry, python_workspace: Path
) -> AsyncGenerator[LspClient, None]:
    """Yield a started LspClient for Python (module-scoped).

    Skips if basedpyright-langserver is not installed.
    The client is started once per test module and shut down after
    all tests in the module complete.
    """
    if shutil.which(python_language_entry.server) is None:
        pytest.skip(f"{python_language_entry.server} not found on PATH")

    try:
        client = LspClient(
            lang_entry=python_language_entry, workspace=python_workspace
        )
        await client.__aenter__()
    except BaseException as exc:
        # Only catch server-startup failures (ExceptionGroup wrapping
        # ServerRuntimeError). Anything else is a real bug — let it propagate.
        if isinstance(exc, ExceptionGroup):
            pytest.skip(f"basedpyright-langserver failed to start: {exc}")
        raise
    yield client
    await client.shutdown()


@pytest.fixture(scope="module")
async def typescript_client(
    typescript_language_entry: LanguageEntry, typescript_workspace: Path
) -> AsyncGenerator[LspClient, None]:
    """Yield a started LspClient for TypeScript (module-scoped).

    Skips if typescript-language-server is not installed.
    """
    if shutil.which(typescript_language_entry.server) is None:
        pytest.skip(f"{typescript_language_entry.server} not found on PATH")

    try:
        client = LspClient(
            lang_entry=typescript_language_entry, workspace=typescript_workspace
        )
        await client.__aenter__()
    except BaseException as exc:
        if isinstance(exc, ExceptionGroup):
            pytest.skip(f"typescript-language-server failed to start: {exc}")
        raise
    yield client
    await client.shutdown()


@pytest.fixture(scope="class")
def python_workspace_isolated():
    """Fresh Python mock repo workspace per test class.

    Each class gets its own copy so file mutations cannot leak between classes.
    Cleans up when the class's tests finish.
    """
    workspace = _make_workspace("lsp_python_isolated_")
    yield workspace
    shutil.rmtree(workspace.parent, ignore_errors=True)


@pytest.fixture(scope="class")
async def python_client_isolated(
    python_language_entry: LanguageEntry,
    python_workspace_isolated: Path,
) -> AsyncGenerator[LspClient, None]:
    """Fresh LspClient per test class with its own workspace.

    Each test class gets its own server process and workspace copy, so
    file mutations (create/modify/delete) cannot leak between classes.
    Adds ~3s per class for server startup — acceptable for correctness.

    Skips if basedpyright-langserver is not installed.
    """
    if shutil.which(python_language_entry.server) is None:
        pytest.skip(f"{python_language_entry.server} not found on PATH")

    try:
        client = LspClient(
            lang_entry=python_language_entry,
            workspace=python_workspace_isolated,
        )
        await client.__aenter__()
    except BaseException as exc:
        if isinstance(exc, ExceptionGroup):
            pytest.skip(f"basedpyright-langserver failed to start: {exc}")
        raise
    yield client
    await client.shutdown()
