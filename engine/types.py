from __future__ import annotations

"""Configuration types for the AivoEngine.

What this file provides
- Dataclasses mapping to the aivocode.toml structure.
- Structures for dynamic LSP provider loading.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LspLaunchConfig:
    """Configuration for launching an LSP server via a dynamic provider.

    Attributes
    ----------
    provider_class : str
        Dotted path to the provider class (e.g. "lsp_server.basedpyright.BasedPyrightProvider").
    config_class : str
        Dotted path to the config dataclass (e.g. "lsp_server.basedpyright.BasedPyrightConfig").
    options : dict[str, Any]
        Keyword arguments passed to the config_class constructor.
    """

    provider_class: str
    config_class: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RepoConfig:
    """Configuration for a single repository and its associated LSP server.

    Attributes
    ----------
    path : Path
        Absolute path to the repository root.
    lsp : LspLaunchConfig
        LSP server configuration for this repository.
    """

    path: Path
    lsp: LspLaunchConfig


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Top-level configuration for the AivoEngine.

    Attributes
    ----------
    repos : dict[str, RepoConfig]
        Mapping of repository labels to their configurations.
    """

    repos: dict[str, RepoConfig]
