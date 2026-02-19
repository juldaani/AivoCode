"""Data model for launching and configuring LSP servers.

What this file provides
- A single spec object that captures how to start a server and configure it.

Why this exists
- Keeps process launch details and LSP configuration in one place.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .types import JsonDict


@dataclass(frozen=True)
class LspServerSpec:
    """Immutable spec describing how to start a server and configure LSP settings."""

    server_id: str
    instance_id: str
    argv: list[str]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)
    root_uri: str = ""
    workspace_folders: list[JsonDict] = field(default_factory=list)
    initialization_options: JsonDict = field(default_factory=dict)
    settings: JsonDict = field(default_factory=dict)
