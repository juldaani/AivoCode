"""Main FastAPI application — includes all route modules.

How to run
- ``fastapi dev api_server/app.py``  (development, auto-reload)
- ``fastapi run api_server/app.py``  (production)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_server.routes.lsp import router as lsp_router

app = FastAPI(title="aivocode", version="0.1.0")

# Allow cross-origin requests from devcontainer or browser consumers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(lsp_router)


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Liveness check — returns 200 if the server is running."""
    return {"ok": True}
