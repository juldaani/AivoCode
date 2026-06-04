"""REST route handlers — thin wrappers around the ``codebase`` library.

Every route delegates directly to the corresponding public ``codebase.*``
function.  No business logic lives here — this module has the same role
as ``api_server/routes/lsp.py``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from codebase import (
    explain_symbol,
    file_overview,
    find_references,
    get_repo_root_dirs,
    get_repo_tree,
    incoming_calls,
    outgoing_calls,
    read_symbol,
)
from codebase._resolve import AmbiguousSymbolError, SymbolNotFoundError
from lsp import detect_workspace

router = APIRouter(prefix="/codebase", tags=["codebase"])


# ── Request models ────────────────────────────────────────────────────────────


class RootBody(BaseModel):
    workspace: str | None = None


class TreeBody(BaseModel):
    suffix: str | None = None
    workspace: str | None = None


class SymbolBody(BaseModel):
    """Shared model for symbol-name-based commands."""

    file: str
    symbol_name: str
    line: int | None = None
    workspace: str | None = None


class OverviewBody(BaseModel):
    file: str
    depth: int = 0
    workspace: str | None = None


# ── Error helpers ──────────────────────────────────────────────────────────────


def _symbol_error_response(exc: AmbiguousSymbolError | SymbolNotFoundError, file_path: str):
    """Build a structured error response from a resolve error."""
    payload: dict = {"error": str(exc), "file": file_path}
    if isinstance(exc, AmbiguousSymbolError):
        payload["candidates"] = exc.candidates
    return payload


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/root")
async def root(body: RootBody):
    ws = detect_workspace(Path(body.workspace)) if body.workspace else Path.cwd()
    return {"dirs": get_repo_root_dirs(ws), "workspace": str(ws)}


@router.post("/tree")
async def tree(body: TreeBody):
    ws = detect_workspace(Path(body.workspace)) if body.workspace else Path.cwd()
    return {"tree": get_repo_tree(ws, suffix=body.suffix), "workspace": str(ws)}


@router.post("/read")
async def read(body: SymbolBody):
    try:
        return await read_symbol(
            body.file, body.symbol_name,
            line=body.line,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/incoming-calls")
async def incoming(body: SymbolBody):
    try:
        return await incoming_calls(
            body.file, body.symbol_name,
            line=body.line,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/outgoing-calls")
async def outgoing(body: SymbolBody):
    try:
        return await outgoing_calls(
            body.file, body.symbol_name,
            line=body.line,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/references")
async def references(body: SymbolBody):
    try:
        return await find_references(
            body.file, body.symbol_name,
            line=body.line,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/overview")
async def overview(body: OverviewBody):
    return await file_overview(
        body.file,
        depth=body.depth,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/explain")
async def explain(body: SymbolBody):
    try:
        return await explain_symbol(
            body.file, body.symbol_name,
            line=body.line,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)
