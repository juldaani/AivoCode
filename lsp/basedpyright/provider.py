"""Basedpyright provider that creates LspClient instances.

What this file provides
- BasedPyrightProvider: implements LspServerProvider for basedpyright,
  using the lsp-client library's BasedpyrightClient under the hood.

Why this exists
- Keeps basedpyright-specific details out of the generic runtime code.
- Migrated from lsp_server/basedpyright/provider.py — create_client()
  replaces spec(), but get_workspace_ignores() logic is identical.
"""

import logging
from pathlib import Path

from lsp_client import BasedpyrightClient, LocalServer

from ..adapter import LspClientAdapter
from ..protocol import LspClient
from .config import BasedPyrightConfig, resolve_and_validate_config_file

log = logging.getLogger(__name__)


class _WorkspaceBasedpyrightClient(BasedpyrightClient):
    """BasedpyrightClient with workspace-wide analysis enabled.

    Overrides the default config to set diagnosticMode to "workspace"
    so basedpyright indexes all files, not just opened ones.
    This matches the behavior of the old lsp_server/ implementation.

    Without this, basedpyright defaults to diagnosticMode "openFilesOnly"
    and won't return symbols for files that haven't been opened via
    textDocument/didOpen.
    """

    def create_default_config(self) -> dict:
        config = super().create_default_config()
        if config is None:
            config = {}
        # Set diagnosticMode to "workspace" so the server indexes all files
        # without requiring explicit textDocument/didOpen.
        for key in ("python", "basedpyright"):
            if key in config and config[key] is not None:
                analysis = config[key].setdefault("analysis", {})
                analysis["diagnosticMode"] = "workspace"
        return config


class BasedPyrightProvider:
    """Creates LspClient instances for basedpyright.

    Uses a subclass of lsp-client's BasedpyrightClient that enables
    workspace-wide analysis (diagnosticMode="workspace"), wrapped in
    LspClientAdapter. Without this override, basedpyright defaults to
    "openFilesOnly" and won't index files unless they are explicitly
    opened via textDocument/didOpen.
    """

    id: str = "basedpyright"

    def create_client(self, workspace_root: Path, config: BasedPyrightConfig) -> LspClient:
        """Build a BasedpyrightClient + LocalServer, wrap in LspClientAdapter.

        Parameters
        ----------
        workspace_root : Path
            Absolute path to the workspace root.
        config : BasedPyrightConfig
            Basedpyright configuration (config_file path).

        Returns
        -------
        LspClient
            A ready-to-start LspClientAdapter wrapping BasedpyrightClient.
        """
        workspace_root = workspace_root.resolve()

        # Resolve the config file (validates existence, resolves relative paths)
        cfg_file = resolve_and_validate_config_file(
            workspace_root=workspace_root,
            config_file=config.config_file,
        )

        # Build initialization options — configFilePath if specified.
        # diagnosticMode is handled by _WorkspaceBasedpyrightClient below.
        init_options: dict = {}
        if cfg_file:
            init_options["basedpyright"] = {
                "analysis": {
                    "configFilePath": str(cfg_file),
                }
            }

        # Create the lsp-client BasedpyrightClient with explicit server config.
        # Note: basedpyright uses 'basedpyright-langserver' for LSP mode,
        # not 'basedpyright'.
        client = _WorkspaceBasedpyrightClient(
            server=LocalServer(
                program="basedpyright-langserver",
                args=["--stdio"],
            ),
            workspace=workspace_root,
            request_timeout=30.0,
            initialization_options=init_options,
        )

        return LspClientAdapter(client)

    def get_workspace_ignores(
        self, workspace_root: Path, config: BasedPyrightConfig
    ) -> list[str]:
        """Parse exclude patterns from pyproject.toml or pyrightconfig.json.

        This is a config-file parsing concern, not an LSP concern.
        The excludes are passed to the file watcher so it doesn't trigger
        on files the LSP itself ignores.

        Migrated from lsp_server/basedpyright/provider.py — identical logic.
        """
        if config.config_file is None:
            return []

        try:
            cfg_file = resolve_and_validate_config_file(
                workspace_root=workspace_root,
                config_file=config.config_file,
            )
        except Exception:
            # Desired: Crash if file specified but doesn't exist
            raise

        if cfg_file is None:
            return []

        excludes: list[str] = []
        section_found = False
        if cfg_file.suffix == ".toml":
            try:
                import tomllib

                with open(cfg_file, "rb") as f:
                    data = tomllib.load(f)
                tool = data.get("tool", {})
                pyright = tool.get("pyright")
                if pyright is None:
                    pyright = tool.get("basedpyright")

                if pyright is not None:
                    section_found = True
                    excludes = pyright.get("exclude", [])
            except Exception as e:
                log.warning(
                    "Failed to parse basedpyright ignores from %s: %s", cfg_file, e
                )
        elif cfg_file.suffix == ".json":
            try:
                import json

                with open(cfg_file, "r") as f:
                    data = json.load(f)
                # For JSON, any root-level key or even empty is technically
                # valid, but we usually expect 'exclude'.
                section_found = True
                excludes = data.get("exclude", [])
            except Exception as e:
                log.warning(
                    "Failed to parse basedpyright ignores from %s: %s", cfg_file, e
                )

        if cfg_file.suffix == ".toml" and not section_found:
            log.warning(
                "Config file '%s' has no [tool.pyright] or [tool.basedpyright] "
                "section. LSP will use defaults.",
                cfg_file,
            )

        if not isinstance(excludes, list):
            return []
        return [str(e) for e in excludes]
