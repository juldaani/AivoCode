"""Config structures and validation helpers for basedpyright.

What this file provides
- BasedPyrightConfig dataclass for basedpyright configuration.
- resolve_and_validate_config_file() for locating and validating config files.

Why this exists
- Centralizes validation rules so the provider stays clean and predictable.
- Migrated from lsp_server/basedpyright/config.py — identical logic.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BasedPyrightConfig:
    """Configuration required to start basedpyright.

    Attributes
    ----------
    config_file : Path | None
        Path to a pyrightconfig.json or pyproject.toml. Accepts absolute
        or workspace-relative paths. None means no config file.
    """

    config_file: Path | None = None


def resolve_and_validate_config_file(
    *, workspace_root: Path, config_file: Path | None
) -> Path | None:
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
