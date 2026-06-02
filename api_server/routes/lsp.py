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
    # New LSP methods.
    query_definition,
    query_type_definition,
    query_references,
    query_hover,
    query_call_hierarchy_incoming,
    query_call_hierarchy_outgoing,
    query_rename_edits,
    query_workspace_symbol,
    query_diagnostics,
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


class PositionBody(BaseModel):
    """Request body for position-based queries.

    Used by /lsp/definition, /lsp/type-definition, /lsp/references,
    /lsp/hover, /lsp/call-hierarchy-incoming, /lsp/call-hierarchy-outgoing.
    """

    file: str
    line: int
    character: int
    workspace: str | None = None


class WorkspaceSymbolBody(BaseModel):
    """Request body for POST /lsp/workspace-symbol."""

    query: str
    workspace: str | None = None


class RenameBody(BaseModel):
    """Request body for POST /lsp/rename-edits (preview)."""

    file: str
    line: int
    character: int
    new_name: str
    workspace: str | None = None


class DiagnosticsBody(BaseModel):
    """Request body for POST /lsp/diagnostics."""

    file: str
    workspace: str | None = None


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


# ── New LSP method routes ──────────────────────────────────────────────────────


@router.post("/workspace-symbol")
async def workspace_symbol(body: WorkspaceSymbolBody):
    """Search for symbols across the workspace matching a query string."""
    return await query_workspace_symbol(
        body.query,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/definition")
async def definition(body: PositionBody):
    """Go-to-definition for a position in a file."""
    return await query_definition(
        Path(body.file),
        line=body.line,
        character=body.character,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/type-definition")
async def type_definition(body: PositionBody):
    """Go-to-type-definition for a position in a file."""
    return await query_type_definition(
        Path(body.file),
        line=body.line,
        character=body.character,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/references")
async def references(body: PositionBody):
    """Find all references to the symbol at a position in a file."""
    return await query_references(
        Path(body.file),
        line=body.line,
        character=body.character,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/hover")
async def hover(body: PositionBody):
    """Hover information (signature, docstring) for a position in a file."""
    return await query_hover(
        Path(body.file),
        line=body.line,
        character=body.character,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/call-hierarchy-incoming")
async def call_hierarchy_incoming(body: PositionBody):
    """Find incoming calls — who calls the function at a position."""
    return await query_call_hierarchy_incoming(
        Path(body.file),
        line=body.line,
        character=body.character,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/call-hierarchy-outgoing")
async def call_hierarchy_outgoing(body: PositionBody):
    """Find outgoing calls — what the function at a position calls."""
    return await query_call_hierarchy_outgoing(
        Path(body.file),
        line=body.line,
        character=body.character,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/rename-edits")
async def rename_edits(body: RenameBody):
    """Preview rename edits without applying them.

    Returns the WorkspaceEdit showing what would change.
    """
    return await query_rename_edits(
        Path(body.file),
        line=body.line,
        character=body.character,
        new_name=body.new_name,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/diagnostics")
async def diagnostics(body: DiagnosticsBody):
    """Query diagnostics (errors, warnings) for a file."""
    return await query_diagnostics(
        Path(body.file),
        workspace=Path(body.workspace) if body.workspace else None,
    )
