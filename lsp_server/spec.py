from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .types import JsonDict


@dataclass(frozen=True)
class LspServerSpec:
    server_id: str
    instance_id: str
    argv: list[str]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)
    root_uri: str = ""
    workspace_folders: list[JsonDict] = field(default_factory=list)
    initialization_options: JsonDict = field(default_factory=dict)
    settings: JsonDict = field(default_factory=dict)
