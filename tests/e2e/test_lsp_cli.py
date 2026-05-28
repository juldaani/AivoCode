"""End-to-end tests: ``python -m cli lsp symbols`` via the REST API server.

What this tests
- Start the REST API server on a free port.
- Run the CLI (as a subprocess) against the server.
- Assert document symbols are returned correctly.
- Shut down the server.

How to run
    pytest tests/e2e/test_lsp_cli.py -v
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

# Repository root — needed to run the CLI with ``python -m cli``.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TEST_FILE = "tests/data/mock_repos/python/mock_pkg/utils.py"


# ──────────────────────────────────────────────────────────────────────────────
# Port / server helpers
# ──────────────────────────────────────────────────────────────────────────────


def _find_free_port() -> int:
    """Bind to port 0, return the OS-assigned port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
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


# ──────────────────────────────────────────────────────────────────────────────
# Module-scoped server fixture
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def lsp_server():
    """Start the REST API server on a free port, yield the URL, then stop it."""
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
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _run_cli(lsp_server: str, *args: str) -> dict:
    """Run ``python -m cli lsp <args>`` against *lsp_server* and return parsed JSON."""
    env = {**os.environ, "AIVOCODE_URL": lsp_server}
    proc = subprocess.run(
        ["python", "-m", "cli", "lsp", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return json.loads(proc.stdout)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestLspSymbols:
    """End-to-end: ``lsp symbols`` via REST API + daemon."""

    def test_symbols_returns_expected_top_level_names(
        self, lsp_server: str
    ) -> None:
        """Querying a known file returns symbols with the expected names."""
        data = _run_cli(lsp_server, "symbols", _TEST_FILE)

        assert "error" not in data, f"unexpected error: {data.get('error')}"
        symbols = data["symbols"]
        assert isinstance(symbols, list), f"expected list, got {type(symbols)}"
        assert len(symbols) >= 1, "expected at least one symbol"

        names = {s["name"] for s in symbols}
        expected = {"Greeter", "LoudGreeter", "hello", "goodbye", "MAX_RETRIES"}
        missing = expected - names
        assert not missing, f"expected symbols not found: {missing}"

    def test_symbols_include_kind_and_range(
        self, lsp_server: str
    ) -> None:
        """Every symbol dict includes kind, kind_number, and range."""
        data = _run_cli(lsp_server, "symbols", _TEST_FILE)
        assert "error" not in data

        for sym in data["symbols"]:
            assert isinstance(sym["name"], str), f"name missing in {sym}"
            assert isinstance(sym["kind"], str), f"kind missing in {sym}"
            assert isinstance(sym["kind_number"], int), f"kind_number missing in {sym}"
            rng = sym["range"]
            assert "start" in rng and "end" in rng, f"range missing in {sym}"
            assert "line" in rng["start"], f"range.start.line missing in {sym}"

    def test_symbols_include_nested_children(
        self, lsp_server: str
    ) -> None:
        """Class symbols include their methods as children."""
        data = _run_cli(lsp_server, "symbols", _TEST_FILE)
        assert "error" not in data

        greeter = next((s for s in data["symbols"] if s["name"] == "Greeter"), None)
        assert greeter is not None, "Greeter class not found"
        assert greeter["children"] is not None, "Greeter should have children"
        child_names = {c["name"] for c in greeter["children"]}
        assert "greet" in child_names, f"greet method not found in Greeter children: {child_names}"


class TestLspStatus:
    """End-to-end: ``lsp status``."""

    def test_status_running_after_symbols_query(
        self, lsp_server: str
    ) -> None:
        """After a symbols query auto-starts the daemon, status reports running."""
        # Auto-start by querying symbols first.
        _run_cli(lsp_server, "symbols", _TEST_FILE)

        data = _run_cli(lsp_server, "status")
        assert data.get("running") is True, f"expected running, got {data}"


class TestLspStartStop:
    """End-to-end: ``lsp start`` and ``lsp stop`` lifecycle."""

    def test_stop_then_status_reports_not_running(
        self, lsp_server: str
    ) -> None:
        """After a stop, status reports not running."""
        # Ensure daemon is running first.
        _run_cli(lsp_server, "start")

        stop_data = _run_cli(lsp_server, "stop")
        assert stop_data.get("running") is False, f"stop: {stop_data}"

        status_data = _run_cli(lsp_server, "status")
        assert status_data.get("running") is False, f"status after stop: {status_data}"

    def test_start_makes_status_running(
        self, lsp_server: str
    ) -> None:
        """After a start, status reports running."""
        start_data = _run_cli(lsp_server, "start")
        assert start_data.get("running") is True, f"start: {start_data}"

        status_data = _run_cli(lsp_server, "status")
        assert status_data.get("running") is True, f"status after start: {status_data}"
