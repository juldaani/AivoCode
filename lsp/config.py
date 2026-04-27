"""LSP client configuration.

What this module provides
- LanguageEntry: dataclass for one language server configuration.
- load_config: reads lsp_config.toml and returns list[LanguageEntry].

Config file format
    See specs/lsp_v1.md for full documentation.
    Brief: lsp_config.toml at repo root, one [[language]] entry per server.

Usage
    from lsp.config import LanguageEntry, load_config

    configs = load_config(Path("lsp_config.toml"))
    for cfg in configs:
        print(f"{cfg.name}: {cfg.server}")
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LanguageEntry:
    """One language server configuration from lsp_config.toml.

    Attributes
    ----------
    name : str
        Language name, e.g. "python" (maps to LSP LanguageId).
    suffixes : tuple[str, ...]
        File extensions this server handles, e.g. (".py", ".pyi").
    server : str
        Server binary on PATH, e.g. "basedpyright-langserver".
    server_args : tuple[str, ...]
        Arguments passed to the server, e.g. ("--stdio",).
    """

    name: str
    suffixes: tuple[str, ...]
    server: str
    server_args: tuple[str, ...]


def load_config(path: Path) -> list[LanguageEntry]:
    """Read lsp_config.toml and return list of LanguageEntry.

    Parameters
    ----------
    path
        Path to lsp_config.toml file.

    Returns
    -------
    list[LanguageEntry]
        One entry per [[language]] table in the TOML file.

    Raises
    ------
    FileNotFoundError
        If the config file does not exist.
    ValueError
        If a required field is missing in a [[language]] entry.
    """
    with path.open("rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    entries: list[LanguageEntry] = []
    languages = raw.get("language", [])
    if not isinstance(languages, list):
        raise ValueError("Config file must have [[language]] entries")

    for item in languages:
        if not isinstance(item, dict):
            raise ValueError("Each [[language]] entry must be a table")

        name = item.get("name")
        if not name:
            raise ValueError("Each [[language]] entry must have a 'name' field")

        suffixes = item.get("suffixes", [])
        if not isinstance(suffixes, list):
            raise ValueError(f"'suffixes' must be a list for language '{name}'")

        server = item.get("server")
        if not server:
            raise ValueError(f"Each [[language]] entry must have a 'server' field")

        server_args = item.get("server_args", [])
        if not isinstance(server_args, list):
            raise ValueError(f"'server_args' must be a list for language '{name}'")

        entries.append(
            LanguageEntry(
                name=str(name),
                suffixes=tuple(str(s) for s in suffixes),
                server=str(server),
                server_args=tuple(str(a) for a in server_args),
            )
        )

    return entries
