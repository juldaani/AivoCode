"""Load test configurations from config.toml.

What this file provides
- LspTestConfig dataclass holding all config for a test scenario.
- Loader that reads config.toml and returns configs by language.
- Dynamic import of provider/config classes from module paths.

Why this exists
- Decouples test code from specific LSP provider implementations.
- Enables adding new LSP servers via config file only (no code changes).
"""

from __future__ import annotations

import importlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LspTestConfig:
    """Configuration for a single LSP test scenario.

    Attributes
    ----------
    language : str
        Language identifier (e.g., "python", "typescript").
    mock_repo : Path
        Path to mock repository, relative to repo root.
    provider_module : str
        Fully qualified module path (e.g., "lsp_server.basedpyright").
    provider_class : str
        Name of the LspServerProvider subclass in the module.
    config_class : str
        Name of the config dataclass in the module.
    provider_config : dict[str, Any]
        Provider-specific config passed to config_class constructor.
    """

    language: str
    mock_repo: Path
    provider_module: str
    provider_class: str
    config_class: str
    provider_config: dict[str, Any]

    def get_provider_and_config_cls(self) -> tuple[Any, type]:
        """Dynamically import and return provider instance and config class.

        Returns
        -------
        tuple[Any, type]
            (provider_instance, config_class) - provider is instantiated,
            config_class is returned for caller to construct with workspace-specific values.
        """
        module = importlib.import_module(self.provider_module)
        provider_cls = getattr(module, self.provider_class)
        config_cls = getattr(module, self.config_class)
        return provider_cls(), config_cls


def load_test_configs(config_path: Path | None = None) -> dict[str, LspTestConfig]:
    """Load test configurations from TOML file.

    Parameters
    ----------
    config_path : Path | None
        Path to config.toml. If None, uses config.toml in same directory.

    Returns
    -------
    dict[str, LspTestConfig]
        Mapping from language name to LspTestConfig.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.toml"

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    configs: dict[str, LspTestConfig] = {}
    for entry in data.get("test_config", []):
        cfg = LspTestConfig(
            language=entry["language"],
            mock_repo=Path(entry["mock_repo"]),
            provider_module=entry["provider_module"],
            provider_class=entry["provider_class"],
            config_class=entry["config_class"],
            provider_config=entry.get("provider_config", {}),
        )
        configs[cfg.language] = cfg

    return configs


def repo_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parents[2]
