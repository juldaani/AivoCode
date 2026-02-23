"""Basedpyright provider that builds a server launch spec.

What this file provides
- A provider that knows how to launch basedpyright and set its config root.

Why this exists
- Keeps basedpyright-specific settings out of generic runtime code.
"""

from pathlib import Path

from .config import BasedPyrightConfig, resolve_and_validate_config_file
from ..spec import LspServerSpec


class BasedPyrightProvider:
    """Create LspServerSpec entries for the basedpyright language server."""

    id = "basedpyright"

    def spec(self, workspace_root: Path, config: BasedPyrightConfig) -> LspServerSpec:
        """Return a validated spec configured for the given workspace/config file."""
        workspace_root = workspace_root.resolve()
        cfg_file = resolve_and_validate_config_file(
            workspace_root=workspace_root,
            config_file=config.config_file,
        )

        root_uri = workspace_root.as_uri()
        instance_id = f"{workspace_root}::{cfg_file}"

        return LspServerSpec(
            server_id=self.id,
            instance_id=instance_id,
            argv=["basedpyright-langserver", "--stdio"],
            cwd=workspace_root,
            root_uri=root_uri,
            workspace_folders=[{"uri": root_uri, "name": workspace_root.name}],
            settings={
                "basedpyright": {
                    "analysis": {
                        "diagnosticMode": "workspace",
                        "configFilePath": str(cfg_file),
                    }
                }
            },
        )

    def get_workspace_ignores(self, workspace_root: Path, config: BasedPyrightConfig) -> list[str]:
        import logging
        log = logging.getLogger(__name__)

        try:
            cfg_file = resolve_and_validate_config_file(
                workspace_root=workspace_root,
                config_file=config.config_file,
            )
        except Exception:
            return []

        excludes = []
        if cfg_file.suffix == ".toml":
            try:
                import tomllib
                with open(cfg_file, "rb") as f:
                    data = tomllib.load(f)
                tool = data.get("tool", {})
                pyright = tool.get("pyright", tool.get("basedpyright", {}))
                excludes = pyright.get("exclude", [])
            except Exception as e:
                log.warning("Failed to parse basedpyright ignores from %s: %s", cfg_file, e)
        elif cfg_file.suffix == ".json":
            try:
                import json
                with open(cfg_file, "r") as f:
                    data = json.load(f)
                excludes = data.get("exclude", [])
            except Exception as e:
                log.warning("Failed to parse basedpyright ignores from %s: %s", cfg_file, e)

        if not isinstance(excludes, list):
            return []
        return [str(e) for e in excludes]
