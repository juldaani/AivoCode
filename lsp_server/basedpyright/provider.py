"""Basedpyright provider that builds a server launch spec.

What this file provides
- A provider that knows how to launch basedpyright and set its config root.

Why this exists
- Keeps basedpyright-specific settings out of generic runtime code.
"""

from pathlib import Path

from .config import BasedPyrightConfig, resolve_and_validate_config_root
from ..spec import LspServerSpec


class BasedPyrightProvider:
    """Create LspServerSpec entries for the basedpyright language server."""

    id = "basedpyright"

    def spec(self, workspace_root: Path, config: BasedPyrightConfig) -> LspServerSpec:
        """Return a validated spec configured for the given workspace/config root."""
        workspace_root = workspace_root.resolve()
        cfg_root = resolve_and_validate_config_root(
            workspace_root=workspace_root,
            config_root=config.config_root,
        )

        root_uri = workspace_root.as_uri()
        instance_id = f"{workspace_root}::{cfg_root}"

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
                        "configFilePath": str(cfg_root),
                    }
                }
            },
        )
