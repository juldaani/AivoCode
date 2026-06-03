"""REST route handlers — thin wrappers around the ``codebase`` library.

Every route delegates directly to the corresponding public ``codebase.*``
function.  No business logic lives here — this module has the same role
as ``api_server/routes/lsp.py``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from codebase import get_repo_root_dirs
from lsp import detect_workspace

router = APIRouter(prefix="/codebase", tags=["codebase"])


# ── Request models ────────────────────────────────────────────────────────────


class RootBody(BaseModel):
    """Request body for POST /codebase/root."""

    workspace: str | None = None


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/root")
async def root(body: RootBody):
    """List top-level directories in the workspace.

    Auto-detects the workspace server-side from the *workspace* hint if
    provided, otherwise falls back to the server's current working
    directory.
    """
    ws = detect_workspace(Path(body.workspace)) if body.workspace else Path.cwd()
    return {"dirs": get_repo_root_dirs(ws), "workspace": str(ws)}
