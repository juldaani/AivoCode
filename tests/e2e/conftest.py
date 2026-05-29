"""Shared fixtures for E2E tests that need a running REST API server.

Uses free-port discovery (``socket.bind(("127.0.0.1", 0))``) to avoid
port conflicts, and cleans up daemon subprocesses after each test module.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

# Load .env at the repo root so that EXA_API_KEY (and any future secrets)
# are available to all E2E tests and the uvicorn server subprocess.
load_dotenv()

# Repository root — needed to run the CLI via ``python -m cli`` and to
# start the uvicorn server from the correct working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _find_free_port() -> int:
    """Bind to port 0, return the OS-assigned port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 45.0) -> None:
    """Poll ``GET /health`` until the server responds or *timeout* expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/health", timeout=2.0)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"Server did not become ready within {timeout}s")


@pytest.fixture(scope="module")
def lsp_server() -> str:
    """Start the REST API server on a free port, yield the URL, then stop it.

    Cleans up any LSP daemon subprocess (spawned with ``start_new_session=True``)
    before killing uvicorn, so daemons don't leak across test modules.
    """
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    # Use uvicorn directly (not fastapi dev) for deterministic lifecycle.
    proc = subprocess.Popen(
        [
            "uvicorn",
            "api_server.app:app",
            "--host", "127.0.0.1",
            "--port", str(port),
        ],
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ},
    )

    try:
        _wait_for_server(url, timeout=45.0)
        yield url
    finally:
        # ── Stop any running daemon first ──────────────────────────────
        # The daemon is spawned with start_new_session=True, so it won't
        # be killed when we terminate the uvicorn process.  Send a stop
        # request to shut it down cleanly.  Use the repo root as the
        # workspace hint (the server will call detect_workspace() on it).
        try:
            httpx.post(
                f"{url}/lsp/stop",
                json={"workspace": str(_REPO_ROOT)},
                timeout=10.0,
            )
        except Exception:
            pass

        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
