"""Smoke tests: web_ops REST endpoints and CLI subprocess flow.

What this tests
- The webfetch REST route is wired correctly (200, markdown content).
- The websearch REST route is wired (skips without EXA_API_KEY).
- The CLI subprocess flows work end-to-end (CLI → REST API → web_ops → JSON output).

The shared server fixture lives in ``tests/e2e/conftest.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import httpx
import pytest

# Repository root — needed to run the CLI with ``python -m cli``.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ── CLI helpers ───────────────────────────────────────────────────────────────


def _run_cli_webfetch(server: str, *args: str) -> dict:
    """Run ``python -m cli webfetch <args>`` and return parsed JSON."""
    env = {**os.environ, "AIVOCODE_URL": server}
    proc = subprocess.run(
        ["python", "-m", "cli", "webfetch", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return json.loads(proc.stdout)


def _run_cli_websearch(server: str, *args: str) -> dict:
    """Run ``python -m cli websearch <args>`` and return parsed JSON."""
    env = {**os.environ, "AIVOCODE_URL": server}
    proc = subprocess.run(
        ["python", "-m", "cli", "websearch", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return json.loads(proc.stdout)


# ── Webfetch smoke ────────────────────────────────────────────────────────────


class TestWebfetchRoute:
    """Smoke: webfetch REST route is wired and returns expected shape.

    Tests verify the route structure regardless of internet access — the
    server may return ``success=False`` with a DNS error in offline envs,
    but the JSON shape must be correct.
    """

    def test_fetch_route_returns_expected_structure(self, lsp_server: str) -> None:
        """The /web_ops/webfetch route returns all expected keys even on failure."""
        result = _run_cli_webfetch(lsp_server, "https://example.com")
        # Key fields must be present regardless of success/failure.
        assert "success" in result, f"missing 'success' in {result}"
        assert isinstance(result["success"], bool), f"success not bool: {result}"
        assert "markdown" in result, f"missing 'markdown' in {result}"
        assert "status_code" in result, f"missing 'status_code' in {result}"
        assert "error" in result, f"missing 'error' in {result}"
        assert "total_chars" in result, f"missing 'total_chars' in {result}"
        # If the fetch succeeded, markdown must be non-empty.
        if result["success"]:
            assert len(result["markdown"]) > 0, "expected non-empty markdown on success"

    def test_fetch_route_accessible_direct(self, lsp_server: str) -> None:
        """Direct HTTP POST to /web_ops/webfetch returns 200 with valid JSON."""
        resp = httpx.post(
            f"{lsp_server}/web_ops/webfetch",
            json={"url": "https://example.com", "wait_until": "load"},
            timeout=60.0,
        )
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
        data = resp.json()
        assert "success" in data, f"expected 'success' in {data}"
        assert "markdown" in data, f"expected 'markdown' in {data}"


# ── Websearch smoke ───────────────────────────────────────────────────────────


class TestWebsearchRoute:
    """Smoke: websearch REST route structure.  Skipped without EXA_API_KEY."""

    @pytest.fixture(autouse=True)
    def _require_api_key(self) -> None:
        """Skip all websearch tests if EXA_API_KEY is not set."""
        if not os.environ.get("EXA_API_KEY"):
            pytest.skip("EXA_API_KEY environment variable not set")

    def test_websearch_route_returns_results(self, lsp_server: str) -> None:
        """A basic websearch returns success=True with results."""
        result = _run_cli_websearch(
            lsp_server, "python asyncio", "--num-results", "2"
        )
        assert result.get("success") is True, f"expected success, got {result}"
        assert "results" in result, f"expected results key in {result}"
        assert len(result["results"]) == 2, (
            f"expected 2 results, got {len(result['results'])}"
        )
        for r in result["results"]:
            assert r["url"].startswith("http"), f"invalid url: {r}"

    def test_websearch_route_accessible_direct(self, lsp_server: str) -> None:
        """Direct HTTP POST to /web_ops/websearch returns 200."""
        resp = httpx.post(
            f"{lsp_server}/web_ops/websearch",
            json={"query": "python asyncio", "num_results": 1},
            timeout=60.0,
        )
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("success") is True, f"expected success, got {data}"


# ── Pretty-format smoke ───────────────────────────────────────────────────────


class TestPrettyFormatGlobal:
    """Smoke: --pretty-format flag works on webfetch and websearch too."""

    def test_webfetch_pretty_format_multiline(self, lsp_server: str) -> None:
        """``webfetch --pretty-format`` produces indented JSON."""
        env = {**os.environ, "AIVOCODE_URL": lsp_server}
        proc = subprocess.run(
            ["python", "-m", "cli", "webfetch", "--pretty-format",
             "https://example.com"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        output = proc.stdout
        assert "\n  " in output, (
            f"expected indented JSON, got: {output[:200]}"
        )
