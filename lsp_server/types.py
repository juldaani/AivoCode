"""Shared JSON type aliases for LSP payloads.

What this file provides
- Small, centralized aliases for JSON-like dictionaries and values.
- Types for workspace/didChangeWatchedFiles notifications.

Why this exists
- Keeps typing consistent across modules that pass JSON-RPC payloads.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

JsonValue = Any
JsonDict = dict[str, JsonValue]


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
