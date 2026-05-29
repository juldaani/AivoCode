"""LSP route handlers — thin wrappers around the ``lsp`` library.

Every route delegates directly to the corresponding public ``lsp.*``
function.  No business logic lives here — this module has the same role
as ``cli/commands/lsp.py`` before the HTTP refactor.

Workspace detection
- The CLI sends an absolute path (cwd, file path, or explicit ``--workspace``).
- Route handlers call ``detect_workspace()`` server-side to find the actual
  git repo root before passing it to the daemon functions.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from lsp import (
    daemon_status,
    daemon_stop,
    detect_workspace,
    query_document_symbols,
)
from lsp._daemon import ensure_daemon

router = APIRouter(prefix="/lsp", tags=["lsp"])


# ── Request models ────────────────────────────────────────────────────────────


class SymbolsBody(BaseModel):
    """Request body for POST /lsp/symbols."""

    file: str
    workspace: str | None = None


class WorkspaceBody(BaseModel):
    """Request body for POST /lsp/start and POST /lsp/stop.

    The ``workspace`` field is a *hint* — any path within the desired git
    workspace (e.g. cwd, a file, or the root itself).  The server uses
    ``detect_workspace()`` to find the actual git repo root.
    """

    workspace: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/symbols")
async def symbols(body: SymbolsBody):
    """Query document symbols for a file.

    Auto-detects the workspace server-side from the file path if no
    explicit ``workspace`` override is provided.
    """
    result = await query_document_symbols(
        Path(body.file),
        workspace=Path(body.workspace) if body.workspace else None,
    )
    return result


@router.post("/start")
async def start(body: WorkspaceBody):
    """Ensure the LSP daemon is running for a workspace (idempotent).

    Accepts any path within the workspace — the server detects the git
    root via ``detect_workspace()``.
    """
    ws = detect_workspace(Path(body.workspace))
    socket_path = ensure_daemon(ws)
    return {"workspace": str(ws), "running": True, "socket": str(socket_path)}


@router.post("/stop")
async def stop(body: WorkspaceBody):
    """Gracefully shut down the LSP daemon for a workspace (idempotent).

    Accepts any path within the workspace — the server detects the git
    root via ``detect_workspace()``.
    """
    ws = detect_workspace(Path(body.workspace))
    daemon_stop(ws)
    return {"workspace": str(ws), "running": False}


@router.get("/status")
async def status(workspace: str):
    """Check the running status of the LSP daemon for a workspace.

    Accepts any path within the workspace — the server detects the git
    root via ``detect_workspace()``.
    """
    ws = detect_workspace(Path(workspace))
    return daemon_status(ws)
