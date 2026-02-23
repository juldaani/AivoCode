from __future__ import annotations

"""Core orchestration engine for AivoCode.

What this file provides
- The AivoEngine class that binds file watching and LSP services.
- Automatic routing of filesystem events to relevant language servers.
- Symbol querying API.
"""

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, Sequence, get_type_hints

from file_watcher import WatchConfig, awatch_repos
from lsp_server import WorkspaceLspManager, AsyncLspClient, FileEvent, FileChangeType
from .config import EngineConfig
from .utils import import_from_string

log = logging.getLogger(__name__)


class AivoEngine:
    """Central orchestrator for repository intelligence."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.lsp_manager = WorkspaceLspManager()
        
        # Maps repo_root Path to the active LSP client for that repo
        self._path_to_client: dict[Path, AsyncLspClient] = {}
        # Maps repo_label string to repo_root Path
        self._label_to_path: dict[str, Path] = {}
        
        self._watcher_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start all configured LSP servers and the background file watcher."""
        for name, repo in self.config.repos.items():
            print("")
            log.info("REPOSITORY: %s, %s", name, repo.path)
            
            # Dynamic loading of provider and config classes
            ProviderClass = import_from_string(repo.lsp.provider_class)
            ConfigClass = import_from_string(repo.lsp.config_class)
            
            log.info("LSP Provider: %s", repo.lsp.provider_class)
            
            provider = ProviderClass()
            
            # Simple type conversion for dataclass fields (esp. Path)
            type_hints = get_type_hints(ConfigClass)
            final_options = {}
            for key, value in repo.lsp.options.items():
                target_type = type_hints.get(key)
                if target_type is Path and isinstance(value, str):
                    path_obj = Path(value)
                    if not path_obj.is_absolute():
                        path_obj = (repo.path / path_obj).resolve()
                    final_options[key] = path_obj
                else:
                    final_options[key] = value

            lsp_config = ConfigClass(**final_options)
            
            # Extract config file/root for cleaner logging if available
            cfg_info = ", ".join(f"{k}={v}" for k, v in final_options.items())
            log.info("LSP Server Config: %s", cfg_info)
            
            # Start/Retrieve the LSP client
            client = await self.lsp_manager.get_or_start(
                provider=provider,
                workspace_root=repo.path,
                config=lsp_config,
            )
            log.info("LSP Client started.")
            
            self._path_to_client[repo.path.resolve()] = client
            self._label_to_path[name] = repo.path.resolve()

        # Start background file watcher
        roots = [repo.path for repo in self.config.repos.values()]
        if roots:
            print("")
            cfg = WatchConfig(coalesce_events=True)
            log.info("File Watcher Roots: %s", [str(r) for r in roots])
            log.info(
                "File Watcher Config: debounce=%dms, step=%dms, recursive=%s, defaults_filter=%s, gitignore_filter=%s, coalesce=%s",
                cfg.debounce_ms,
                cfg.step_ms,
                cfg.recursive,
                cfg.defaults_filter,
                cfg.gitignore_filter,
                cfg.coalesce_events,
            )
            
            if cfg.defaults_filter:
                from watchfiles import DefaultFilter
                log.info("File Watcher Default ignored dirs: %s", DefaultFilter.ignore_dirs)
                log.info("File Watcher Default ignored patterns: %s", DefaultFilter.ignore_entity_patterns)

            log.info(
                "File Watcher Custom filters: ignore_dirs=%s, ignore_entity_globs=%s, ignore_paths=%s",
                cfg.ignore_dirs,
                cfg.ignore_entity_globs,
                cfg.ignore_paths,
            )
            self._watcher_task = asyncio.create_task(self._watch_loop(roots, cfg))


    async def stop(self) -> None:
        """Gracefully stop the engine and all services."""
        if self._watcher_task:
            log.info("Stopping file watcher...")
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass
        
        log.info("Shutting down all LSP servers...")
        await self.lsp_manager.shutdown_all()
        self._path_to_client.clear()
        self._label_to_path.clear()
        log.info("Engine stopped.")

    async def query_symbols(self, repo_name: str, file_rel_path: str) -> Any:
        """Query symbols for a file in a specific repository.

        Returns the raw JSON response from the LSP server.
        """
        path = self._label_to_path.get(repo_name)
        if not path:
            raise ValueError(f"Unknown repository: {repo_name}")
        
        client = self._path_to_client.get(path)
        if not client:
            raise RuntimeError(f"LSP client not running for repo: {repo_name}")

        abs_path = (path / file_rel_path).resolve()
        uri = abs_path.as_uri()

        return await client.request(
            "textDocument/documentSymbol",
            params={"textDocument": {"uri": uri}}
        )

    async def _watch_loop(self, roots: Sequence[Path], cfg: WatchConfig) -> None:
        """Background loop that routes file changes to LSP servers."""
        # Reverse mapping for logging repo names
        path_to_label = {p: name for name, p in self._label_to_path.items()}
        
        try:
            async for batch in awatch_repos(roots, cfg):
                # Group events by their repo_root for targeted notifications
                by_root: dict[Path, list[FileEvent]] = {}
                
                for ev in batch.events:
                    if not ev.repo_root:
                        continue
                        
                    root = ev.repo_root.resolve()
                    if root not in by_root:
                        by_root[root] = []
                    
                    # Map watchfiles Change to LSP FileChangeType
                    # watchfiles: added=1, modified=2, deleted=3
                    # LSP: created=1, changed=2, deleted=3
                    # They happen to align perfectly.
                    lsp_ev = FileEvent(
                        uri=ev.abs_path.as_uri(),
                        type=FileChangeType(int(ev.change))
                    )
                    by_root[root].append(lsp_ev)

                # Send notifications to respective clients
                for root, lsp_events in by_root.items():
                    repo_label = path_to_label.get(root, str(root))
                    log.info(
                        "Routing %d event(s) to repo: %s", 
                        len(lsp_events), 
                        repo_label
                    )
                    
                    client = self._path_to_client.get(root)
                    if client and client.is_running():
                        await client.notify_did_change_watched_files(lsp_events)

        except asyncio.CancelledError:
            log.info("File watcher task cancelled")
        except Exception:
            log.exception("Error in engine watch loop")
            raise
