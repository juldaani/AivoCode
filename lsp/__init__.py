"""Public exports for the LSP client interface package.

What this file provides
- A curated import surface for the lsp package.
- Only library-agnostic types and protocols — no implementation details.

Why this exists
- Consumers import from `lsp` and depend on the protocol, not the adapter.
- Implementation-specific imports (LspClientAdapter, lsp-client classes) live
  inside provider modules, not here.
"""

from .manager import WorkspaceLspManager
from .protocol import LspClient, LspServerProvider
from .file_events import FileChangeType, FileEvent

__all__ = [
    "FileChangeType",
    "FileEvent",
    "LspClient",
    "LspServerProvider",
    "WorkspaceLspManager",
]
