"""Shared types for LSP client interactions.

What this file provides
- FileChangeType and FileEvent for workspace/didChangeWatchedFiles notifications.

Why this exists
- These types are LSP-spec values, not tied to any specific LSP client library.
- Kept in the public interface so consumers can construct events without
  importing implementation details.
"""

from dataclasses import dataclass
from enum import IntEnum


class FileChangeType(IntEnum):
    """LSP file change types for workspace/didChangeWatchedFiles.

    Values match the LSP specification:
    - Created (1): The file was created.
    - Changed (2): The file was modified.
    - Deleted (3): The file was deleted.
    """

    created = 1
    changed = 2
    deleted = 3


@dataclass(frozen=True, slots=True)
class FileEvent:
    """A file event for workspace/didChangeWatchedFiles notification.

    Attributes
    ----------
    uri : str
        The file URI (e.g., "file:///path/to/file.py").
    type : FileChangeType
        The type of change that occurred.
    """

    uri: str
    type: FileChangeType
