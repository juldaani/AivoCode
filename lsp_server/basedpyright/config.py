"""Config structures and validation helpers for LSP providers.

What this file provides
- Small config dataclasses and validation routines.

Why this exists
- Centralizes validation rules so providers stay clean and predictable.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BasedPyrightConfig:
    """Configuration required to start basedpyright."""

    config_file: Path | None = None


def resolve_and_validate_config_file(*, workspace_root: Path, config_file: Path | None) -> Path | None:
    """Resolve and validate the config file for basedpyright.

    Rules:
    - If None, return None (skip config).
    - Accept absolute or workspace-relative paths.
    - Require the file to exist.
    - Warn (but do not fail) if the config file is outside the workspace.
    """
    if config_file is None:
        return None

    workspace_root = workspace_root.resolve()
    if config_file.is_absolute():
        resolved = config_file
    else:
        resolved = workspace_root / config_file
    resolved = resolved.resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"config_file does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"config_file is not a file: {resolved}")

    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        log.warning(
            "config_file is outside workspace_root: %s (workspace=%s)",
            resolved,
            workspace_root,
        )

    return resolved
