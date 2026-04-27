"""Types for the file watcher.

The watcher operates over one or more *roots* (directories). watchfiles yields raw
filesystem change events which we classify to a root and then optionally filter
using gitignore rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from watchfiles import Change


@dataclass(frozen=True, slots=True)
class WatchConfig:
    """Configuration for repo watching.

    Filtering
    - defaults_filter: whether to use watchfiles' DefaultFilter defaults.
    - gitignore_filter: whether to filter events using gitignore rules (via git).
    - repo_custom_ignores: maps repository absolute path -> sequence of raw exclude strings (globs or relative paths).
    """

    # watchfiles watching parameters
    recursive: bool = True
    debounce_ms: int = 1600
    step_ms: int = 50
    force_polling: bool | None = None
    poll_delay_ms: int = 300
    ignore_permission_denied: bool = False

    # filtering toggles
    defaults_filter: bool = True
    gitignore_filter: bool = True

    # custom excludes mapped per repository root
    repo_custom_ignores: dict[Path, Sequence[str]] = field(default_factory=dict)

    # gitignore filtering parameters
    git_timeout_s: float = 10.0
    git_chunk_size: int = 4000

    # output shaping
    # If True, coalesce multiple changes for the same path within a single batch
    # into one "final" event (e.g. ADDED+DELETED becomes MODIFIED if the path exists).
    coalesce_events: bool = True


@dataclass(frozen=True, slots=True)
class WatchEvent:
    change: Change
    abs_path: Path
    repo_root: Path | None
    repo_label: str
    rel_path: str


@dataclass(frozen=True, slots=True)
class WatchBatch:
    ts: datetime
    raw: int
    filtered: int
    events: Sequence[WatchEvent]
    warnings: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class RootInfo:
    roots: Sequence[Path]
    labels: dict[Path, str]
    nested_pairs: Sequence[tuple[Path, Path]]
