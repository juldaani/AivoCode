from __future__ import annotations

"""TOML configuration loader for the AivoEngine.

What this file provides
- Functionality to parse aivocode.toml into EngineConfig objects.
"""

import tomllib
from pathlib import Path
from typing import Any

from .types import EngineConfig, LspLaunchConfig, RepoConfig


def load_config(path: Path | str) -> EngineConfig:
    """Load and validate an AivoEngine configuration from a TOML file.

    Parameters
    ----------
    path : Path | str
        Path to the aivocode.toml file.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as f:
        data = tomllib.load(f)

    repos_data = data.get("repos", {})
    if not isinstance(repos_data, dict):
        raise ValueError("'repos' section must be a table")

    repos: dict[str, RepoConfig] = {}
    for name, repo_data in repos_data.items():
        repos[name] = _parse_repo(repo_data)

    return EngineConfig(repos=repos)


def _parse_repo(data: dict[str, Any]) -> RepoConfig:
    """Parse a single repository block."""
    path_str = data.get("path")
    if not path_str:
        raise ValueError("Repo entry missing 'path'")
    
    path = Path(path_str).resolve()
    
    lsp_data = data.get("lsp")
    if not lsp_data or not isinstance(lsp_data, dict):
        raise ValueError("Repo entry missing 'lsp' table")

    provider_class = lsp_data.get("provider_class")
    config_class = lsp_data.get("config_class")
    
    if not provider_class or not config_class:
        raise ValueError("LSP entry must specify 'provider_class' and 'config_class'")

    # Extract all other keys as options for the config class
    options = {
        k: v for k, v in lsp_data.items() 
        if k not in ("provider_class", "config_class")
    }

    return RepoConfig(
        path=path,
        lsp=LspLaunchConfig(
            provider_class=provider_class,
            config_class=config_class,
            options=options
        )
    )
