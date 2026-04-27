"""Internal: translate file_watcher events to LSP file events.

What this module provides
- translate: pure function converting WatchBatch → list of LSP FileEvent.
- filter_by_suffix: helper to keep only events matching given suffixes.

Why internal
- This is used by LspClient.notify_file_changes() and is not part of the
  public package API. Upstream code never calls translate() directly.

How it works
1. Maps watchfiles Change enum → LSP FileChangeType (Created/Changed/Deleted).
2. Converts Path → file:// URI using pathlib.Path.as_uri().
3. Filters events by file suffix (e.g. only .py files for a Python client).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from lsp_client.utils.types import lsp_type
from watchfiles import Change

from file_watcher.types import WatchBatch, WatchEvent


def _change_type(change: Change) -> lsp_type.FileChangeType:
    """Map watchfiles Change enum to LSP FileChangeType.

    Parameters
    ----------
    change : watchfiles.Change
        The change type from watchfiles.

    Returns
    -------
    lsp_type.FileChangeType
        Corresponding LSP file change type.

    Raises
    ------
    ValueError
        If an unknown Change value is encountered.
    """
    match change:
        case Change.added:
            return lsp_type.FileChangeType.Created
        case Change.modified:
            return lsp_type.FileChangeType.Changed
        case Change.deleted:
            return lsp_type.FileChangeType.Deleted
        case _:
            raise ValueError(f"Unknown watchfiles Change value: {change!r}")


def filter_by_suffix(
    events: Sequence[WatchEvent], suffixes: Sequence[str]
) -> list[WatchEvent]:
    """Keep only events whose file path ends with one of the given suffixes.

    Parameters
    ----------
    events
        Sequence of WatchEvent to filter.
    suffixes
        Sequence of suffixes to match, e.g. [".py", ".pyi"].

    Returns
    -------
    list[WatchEvent]
        Events whose abs_path ends with one of the given suffixes.
        Empty list if no events match.
    """
    if not suffixes:
        return list(events)
    return [e for e in events if any(str(e.abs_path).endswith(s) for s in suffixes)]


def translate(
    batch: WatchBatch, suffixes: Sequence[str]
) -> list[lsp_type.FileEvent]:
    """Translate a WatchBatch into LSP FileEvent list.

    Parameters
    ----------
    batch
        A WatchBatch from the file watcher.
    suffixes
        Sequence of file suffixes to include, e.g. [".py", ".pyi"].
        If empty, all events are included.

    Returns
    -------
    list[lsp_type.FileEvent]
        LSP FileEvent objects ready for didChangeWatchedFiles notification.
        Empty list if no events match the suffixes.
    """
    filtered = filter_by_suffix(batch.events, suffixes)
    return [
        lsp_type.FileEvent(
            uri=Path(event.abs_path).as_uri(),
            type=_change_type(event.change),
        )
        for event in filtered
    ]
