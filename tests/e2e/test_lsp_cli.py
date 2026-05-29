"""End-to-end tests: ``python -m cli lsp`` via the REST API server.

What this tests
- Start the REST API server on a free port (shared fixture).
- Run the CLI (as a subprocess) against the server.
- Assert document symbols are returned correctly.
- Shut down the server after the module completes.

The shared server fixture lives in ``tests/e2e/conftest.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

# Repository root — needed to run the CLI with ``python -m cli``.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TEST_FILE = "tests/data/mock_repos/python/mock_pkg/utils.py"


# ── CLI helper ────────────────────────────────────────────────────────────────


def _run_cli(lsp_server: str, *args: str) -> dict:
    """Run ``python -m cli lsp <args>`` against *lsp_server* and return parsed JSON.

    The CLI no longer does client-side workspace detection — it sends
    ``Path.cwd()`` as a hint and the server calls ``detect_workspace()``.
    """
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


# ── Tests ─────────────────────────────────────────────────────────────────────


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

    def test_symbols_use_absolute_path_in_response(
        self, lsp_server: str
    ) -> None:
        """The server returns an absolute file path in the response."""
        data = _run_cli(lsp_server, "symbols", _TEST_FILE)
        assert "error" not in data, f"unexpected error: {data.get('error')}"
        assert data["file"].startswith("/"), (
            f"expected absolute path, got {data['file']}"
        )


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


class TestPrettyFormat:
    """End-to-end: ``--pretty-format`` flag."""

    def test_pretty_format_produces_multiline_output(
        self, lsp_server: str
    ) -> None:
        """``--pretty-format`` produces indented (multi-line) JSON."""
        env = {**os.environ, "AIVOCODE_URL": lsp_server}
        proc = subprocess.run(
            ["python", "-m", "cli", "lsp", "status", "--pretty-format"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        output = proc.stdout
        assert "\n  " in output, (
            f"expected indented JSON (multi-line), got: {output[:200]}"
        )
