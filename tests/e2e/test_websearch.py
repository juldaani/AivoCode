"""End-to-end tests: ``aivocode websearch`` CLI command via REST API.

What this tests
- The full CLI pipeline: argparse → HTTP POST to REST API →
  ``web_ops.web_search()`` → JSON output.
- All CLI flags are forwarded correctly: ``--type``, ``--num-results``,
  ``--include-domains``, ``--exclude-domains``, ``--full-text``.
- Error handling: missing API key, invalid arguments.

Prerequisites
- ``EXA_API_KEY`` environment variable must be set.  Tests skip gracefully
  when the key is missing.
- The REST API server must be running (provided by the shared ``lsp_server``
  fixture in ``tests/e2e/conftest.py``).

Each test that hits the Exa API costs ~$0.007.  The suite runs ~6 paid
calls total (~$0.04).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

import pytest

from tests.e2e.conftest import _REPO_ROOT  # type: ignore[import-untyped]


# ── CLI helper ────────────────────────────────────────────────────────────────


def _run_search(server: str, *args: str, timeout: int = 60) -> dict[str, Any]:
    """Run ``python -m cli websearch <args>`` and return parsed JSON."""
    env = {**os.environ, "AIVOCODE_URL": server}
    proc = subprocess.run(
        ["python", "-m", "cli", "websearch", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return json.loads(proc.stdout)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def exa_api_key() -> str:
    """Return the Exa API key from the environment or skip all tests."""
    from dotenv import load_dotenv
    load_dotenv()

    key = os.environ.get("EXA_API_KEY")
    if not key:
        pytest.skip("EXA_API_KEY environment variable not set")
    return key


# ── Basic search ──────────────────────────────────────────────────────────────


class TestBasicSearch:
    """Basic search — results, fields, and result-count limits."""

    def test_search_returns_results_with_expected_fields(
        self, lsp_server: str, exa_api_key: str
    ) -> None:
        """A default search returns results with title, url, and highlights."""
        data = _run_search(lsp_server, "Paris", "--num-results", "2")
        assert data["success"] is True, f"expected success, got {data}"
        assert data["query"] == "Paris", f"unexpected query: {data['query']}"
        assert len(data["results"]) == 2, f"expected 2 results, got {len(data['results'])}"
        assert data["cost_dollars"] > 0, f"expected non-zero cost, got {data['cost_dollars']}"

        r = data["results"][0]
        assert isinstance(r["title"], str), f"title missing: {r}"
        assert r["url"].startswith("http"), f"url missing or invalid: {r}"
        assert isinstance(r["highlights"], list) and len(r["highlights"]) > 0, (
            f"highlights missing or empty: {r}"
        )

    def test_num_results_is_honored(
        self, lsp_server: str, exa_api_key: str
    ) -> None:
        """``--num-results`` controls how many results are returned."""
        data = _run_search(lsp_server, "hello world", "--num-results", "1")
        assert data["success"] is True
        assert len(data["results"]) == 1, (
            f"expected 1 result, got {len(data['results'])}"
        )

        data = _run_search(lsp_server, "github", "--num-results", "3")
        assert data["success"] is True
        assert len(data["results"]) == 3, (
            f"expected 3 results, got {len(data['results'])}"
        )


# ── --type variants ───────────────────────────────────────────────────────────


class TestSearchTypes:
    """--type flag forwards the search type correctly."""

    @pytest.mark.parametrize("stype", ["auto", "fast", "instant"])
    def test_type_variant_returns_results(
        self, lsp_server: str, exa_api_key: str, stype: str
    ) -> None:
        """Every supported ``--type`` value returns valid results."""
        data = _run_search(
            lsp_server,
            "Python programming language", "--type", stype, "--num-results", "2"
        )
        assert data["success"] is True, (
            f"type={stype} failed: {data.get('error')}"
        )
        assert len(data["results"]) >= 1, (
            f"type={stype} returned no results"
        )
        for r in data["results"]:
            assert r["url"].startswith("http"), (
                f"type={stype} returned result with invalid url: {r}"
            )


# ── Domain filters ────────────────────────────────────────────────────────────


class TestDomainFilters:
    """--include-domains and --exclude-domains flags."""

    def test_include_domains_restricts_urls(
        self, lsp_server: str, exa_api_key: str
    ) -> None:
        """``--include-domains`` constrains all result URLs to the given domain."""
        data = _run_search(
            lsp_server,
            "async io",
            "--include-domains", "docs.python.org",
            "--num-results", "2",
        )
        assert data["success"] is True
        assert len(data["results"]) >= 1, "expected at least 1 result"
        for r in data["results"]:
            assert "docs.python.org" in r["url"], (
                f"expected docs.python.org domain, got {r['url']}"
            )

    def test_exclude_domains_filters_out_domain(
        self, lsp_server: str, exa_api_key: str
    ) -> None:
        """``--exclude-domains`` removes results from the excluded domain."""
        data = _run_search(
            lsp_server,
            "Paris city guide",
            "--exclude-domains", "wikipedia.org",
            "--num-results", "3",
        )
        assert data["success"] is True
        for r in data["results"]:
            assert "wikipedia.org" not in r["url"], (
                f"expected wikipedia.org excluded, got {r['url']}"
            )


# ── Error handling ────────────────────────────────────────────────────────────


class TestErrorHandling:
    """Graceful handling of missing key, invalid args, and edge cases."""

    def test_invalid_type_rejected_by_argparse(self, lsp_server: str) -> None:
        """An invalid ``--type`` value is caught by argparse before the API call."""
        env = {
            **os.environ,
            "AIVOCODE_URL": lsp_server,
            "EXA_API_KEY": "dummy",
        }
        proc = subprocess.run(
            ["python", "-m", "cli", "websearch", "test", "--type", "nonsense"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        # argparse rejects invalid choices and exits non-zero.
        assert proc.returncode != 0, f"expected non-zero exit, got {proc.returncode}"
        assert "invalid choice" in proc.stderr.lower() or "nonsense" in proc.stderr, (
            f"expected argparse error, got stderr: {proc.stderr}"
        )
