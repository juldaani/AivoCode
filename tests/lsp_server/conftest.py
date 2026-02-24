"""Pytest configuration for LSP tests.

What this file provides
- Ensures the repository root is on sys.path for local imports.
- Fixtures for config-driven LSP client testing.
- Automatic parametrization for all configs defined in config.toml.

Why this exists
- Tests import modules from the repo without installing a package.
- Decouples test code from specific LSP provider implementations.
- Adding new LSP configs to TOML automatically includes them in tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lsp_server.client import AsyncLspClient
from lsp_server.manager import WorkspaceLspManager
from .config import load_test_configs, LspTestConfig, repo_root
from .helpers import copy_mock_repo


_TEST_CONFIGS: dict[str, LspTestConfig] | None = None


def _get_test_configs() -> dict[str, LspTestConfig]:
    """Lazy-load test configs (cached after first load)."""
    global _TEST_CONFIGS
    if _TEST_CONFIGS is None:
        _TEST_CONFIGS = load_test_configs()
    return _TEST_CONFIGS


def pytest_configure() -> None:
    """Add repo root to sys.path for local imports."""
    repo_root_path = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root_path))


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Automatically parametrize tests that use lsp_test_config fixture."""
    if "lsp_test_config" in metafunc.fixturenames:
        configs = _get_test_configs()
        languages = list(configs.keys())
        metafunc.parametrize("lsp_test_config", languages, indirect=True)


@pytest.fixture
def lsp_test_config(request: pytest.FixtureRequest) -> LspTestConfig:
    """Get LSP test config for a language (parametrized automatically)."""
    language = request.param
    configs = _get_test_configs()
    if language not in configs:
        available = ", ".join(sorted(configs.keys()))
        raise ValueError(f"No config for language '{language}'. Available: {available}")
    return configs[language]


@pytest.fixture
def lsp_test_workspace(tmp_path: Path, lsp_test_config: LspTestConfig) -> Path:
    """Prepare an isolated workspace for LSP testing.

    Returns
    -------
    Path
        Path to the workspace root (copy of mock repo).
    """
    src_mock_repo = repo_root() / lsp_test_config.mock_repo
    return copy_mock_repo(tmp_path, lsp_test_config.language, src_mock_repo)


async def start_lsp_client(
    lsp_test_config: LspTestConfig, workspace: Path
) -> AsyncLspClient:
    """Start an LSP client for the given config and workspace.

    This is an async helper to be used with asyncio.run() in tests.

    Parameters
    ----------
    lsp_test_config : LspTestConfig
        Test configuration from the lsp_test_config fixture.
    workspace : Path
        Workspace root path from lsp_test_workspace fixture.

    Returns
    -------
    AsyncLspClient
        A started LSP client. Caller is responsible for calling shutdown().
    """
    provider, config_cls = lsp_test_config.get_provider_and_config_cls()
    config_kwargs = _prepare_config_kwargs(
        lsp_test_config.provider_config, workspace
    )
    config = config_cls(**config_kwargs)
    manager = WorkspaceLspManager()
    return await manager.get_or_start(provider, workspace, config)


def _prepare_config_kwargs(
    provider_config: dict, workspace: Path
) -> dict:
    """Prepare config kwargs, converting known path fields to Path objects.

    This handles the common case where config values come from TOML as strings
    but need to be Path objects relative to the workspace.

    Parameters
    ----------
    provider_config : dict
        Raw config from TOML (values may be strings).
    workspace : Path
        Workspace root for resolving relative paths.

    Returns
    -------
    dict
        Config kwargs with Path fields converted.
    """
    result = {}
    for key, value in provider_config.items():
        if key in ("config_root", "root", "workspace_root", "cwd", "config_file") and isinstance(
            value, str
        ):
            path = Path(value)
            if not path.is_absolute():
                path = workspace / path
            result[key] = path
        else:
            result[key] = value
    return result
