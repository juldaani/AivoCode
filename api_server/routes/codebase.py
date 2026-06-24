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
    affected_test_files,
    analyze_impact,
    explain_symbol,
    file_diagnostics,
    file_overview,
    find_definition,
    find_references,
    get_repo_tree,
    hover_symbol,
    import_dependencies,
    import_dependents,
    incoming_calls,
    outgoing_calls,
    read_symbol,
    search_symbols,
)
from codebase._resolve import AmbiguousSymbolError, SymbolNotFoundError
from lsp import detect_workspace

router = APIRouter(prefix="/codebase", tags=["codebase"])


# ── Request models ────────────────────────────────────────────────────────────


class TreeBody(BaseModel):
    suffix: str | None = None
    workspace: str | None = None


class SymbolBody(BaseModel):
    """Shared model for symbol-name-based commands."""

    file: str
    symbol_name: str
    line: int | None = None
    depth: int | None = None
    max: int | None = None
    workspace: str | None = None


class OutgoingBody(SymbolBody):
    """Extends SymbolBody with workspace_only filtering."""

    workspace_only: bool = True


class OverviewBody(BaseModel):
    file: str
    depth: int = 0
    workspace: str | None = None


class SearchBody(BaseModel):
    query: str
    kind: str | None = None
    limit: int = 40
    path: str | None = None
    workspace: str | None = None


class FileBody(BaseModel):
    """Shared model for file-level import-graph commands (no symbol name needed)."""

    file: str
    depth: int | None = None
    workspace: str | None = None


class DiagnosticsBody(BaseModel):
    """Request model for /codebase/diagnostics."""

    file: str
    max: int = 50
    workspace: str | None = None


# ── Error helpers ──────────────────────────────────────────────────────────────


def _symbol_error_response(exc: AmbiguousSymbolError | SymbolNotFoundError, file_path: str):
    """Build a structured error response from a resolve error."""
    payload: dict = {"error": str(exc), "file": file_path}
    if isinstance(exc, AmbiguousSymbolError):
        payload["candidates"] = exc.candidates
    return payload


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/tree")
async def tree(body: TreeBody):
    ws = detect_workspace(Path(body.workspace)) if body.workspace else Path.cwd()
    return get_repo_tree(ws, suffix=body.suffix)


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
            max_sites=body.max if body.max is not None else 100,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/outgoing-calls")
async def outgoing(body: OutgoingBody):
    try:
        return await outgoing_calls(
            body.file, body.symbol_name,
            line=body.line,
            max_sites=body.max if body.max is not None else 100,
            workspace=Path(body.workspace) if body.workspace else None,
            workspace_only=body.workspace_only,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/references")
async def references(body: SymbolBody):
    try:
        return await find_references(
            body.file, body.symbol_name,
            line=body.line,
            max_sites=body.max if body.max is not None else 100,
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


@router.post("/search")
async def search(body: SearchBody):
    return await search_symbols(
        body.query,
        kind=body.kind,
        limit=body.limit,
        path_filter=body.path,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/impact")
async def impact(body: SymbolBody):
    try:
        return await analyze_impact(
            body.file, body.symbol_name,
            line=body.line,
            depth=body.depth if body.depth is not None else 10,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/definition")
async def definition(body: SymbolBody):
    try:
        return await find_definition(
            body.file, body.symbol_name,
            line=body.line,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/hover")
async def hover(body: SymbolBody):
    try:
        return await hover_symbol(
            body.file, body.symbol_name,
            line=body.line,
            workspace=Path(body.workspace) if body.workspace else None,
        )
    except (AmbiguousSymbolError, SymbolNotFoundError) as exc:
        return _symbol_error_response(exc, body.file)


@router.post("/diagnostics")
async def diagnostics(body: DiagnosticsBody):
    return await file_diagnostics(
        body.file,
        max_results=body.max,
        workspace=Path(body.workspace) if body.workspace else None,
    )


# ── Import-graph routes ────────────────────────────────────────────────────────


@router.post("/import-dependents")
async def import_dependents_route(body: FileBody):
    kwargs: dict = {
        "file_path": body.file,
        "workspace": Path(body.workspace) if body.workspace else None,
    }
    if body.depth is not None:
        kwargs["depth"] = body.depth
    return await import_dependents(**kwargs)


@router.post("/import-dependencies")
async def import_dependencies_route(body: FileBody):
    return await import_dependencies(
        body.file,
        workspace=Path(body.workspace) if body.workspace else None,
    )


@router.post("/affected-tests")
async def affected_tests_route(body: FileBody):
    kwargs: dict = {
        "file_path": body.file,
        "workspace": Path(body.workspace) if body.workspace else None,
    }
    if body.depth is not None:
        kwargs["depth"] = body.depth
    return await affected_test_files(**kwargs)
