from pathlib import Path
from typing import Protocol, TypeVar

from .spec import LspServerSpec

ConfigT = TypeVar("ConfigT")


class LspServerProvider(Protocol[ConfigT]):
    id: str

    def spec(self, workspace_root: Path, config: ConfigT) -> LspServerSpec:
        ...
