"""File watcher utilities built on top of `watchfiles`.

This package provides an importable API for watching one or more repository roots
and producing structured change events. It is used by the standalone CLI in
`file_watcher/watch_repo.py`, and can be imported by production code.
"""

from file_watcher.types import WatchBatch, WatchConfig, WatchEvent
from file_watcher.watcher import awatch_repos, watch_repos

__all__ = [
    "WatchBatch",
    "WatchConfig",
    "WatchEvent",
    "awatch_repos",
    "watch_repos",
]
