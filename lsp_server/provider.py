"""Protocol for language-specific LSP server providers.

What this file provides
- A simple interface that turns config + workspace into a server spec.

Why this exists
- Keeps language-specific details out of the generic runtime code.
"""

from pathlib import Path
from typing import Protocol, TypeVar

from .spec import LspServerSpec

ConfigT = TypeVar("ConfigT")


class LspServerProvider(Protocol[ConfigT]):
    """Interface to build an LspServerSpec for a language server."""

    id: str

    def spec(self, workspace_root: Path, config: ConfigT) -> LspServerSpec:
        """Return a launch spec for a server in the given workspace."""
        ...
