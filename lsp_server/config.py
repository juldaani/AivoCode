import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BasedPyrightConfig:
    config_root: Path


def resolve_and_validate_config_root(*, workspace_root: Path, config_root: Path) -> Path:
    workspace_root = workspace_root.resolve()
    if config_root.is_absolute():
        resolved = config_root
    else:
        resolved = workspace_root / config_root
    resolved = resolved.resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"config_root does not exist: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"config_root is not a directory: {resolved}")

    has_pyproject = (resolved / "pyproject.toml").is_file()
    has_pyrightconfig = (resolved / "pyrightconfig.json").is_file()
    if not (has_pyproject or has_pyrightconfig):
        raise ValueError(
            "config_root must contain pyproject.toml or pyrightconfig.json: "
            f"{resolved}"
        )

    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        log.warning(
            "config_root is outside workspace_root: %s (workspace=%s)",
            resolved,
            workspace_root,
        )

    return resolved
