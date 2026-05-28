"""End-to-end tests: ``aivocode websearch`` CLI command.

What this tests
- The full CLI pipeline: argparse → ``web_ops.web_search()`` → JSON output.
- All CLI flags are forwarded correctly: ``--type``, ``--num-results``,
  ``--include-domains``, ``--exclude-domains``, ``--full-text``.
- Error handling: missing API key, invalid arguments.

Prerequisites
- ``EXA_API_KEY`` environment variable must be set.  Tests skip gracefully
  when the key is missing.
- Each test that hits the Exa API costs ~$0.007.  The suite runs 7 paid
  calls total (~$0.05).

How to run
    EXA_API_KEY=your-key pytest tests/e2e/test_websearch.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def exa_api_key() -> str:
    """Return the Exa API key from the environment or skip all tests.

    Loads ``.env`` explicitly because pytest fixtures may run before
    ``web_ops`` is imported (and therefore before its ``load_dotenv()`` call).
    """
    from dotenv import load_dotenv
    load_dotenv()

    key = os.environ.get("EXA_API_KEY")
    if not key:
        pytest.skip("EXA_API_KEY environment variable not set")
    return key


@pytest.fixture(scope="module")
def run_search(exa_api_key: str) -> Callable[..., dict[str, Any]]:
    """Factory: run ``aivocode websearch`` and return parsed JSON.

    All tests in the module share the same fixture scope to avoid
    repeated API key checks.
    """

    def _run(*args: str, timeout: int = 60) -> dict[str, Any]:
        """Invoke the CLI and return the parsed JSON result dict.

        Args:
            *args: CLI arguments after ``websearch``
                (e.g. ``"hello world", "--num-results", "2"``).
            timeout: Seconds before the subprocess is killed.

        Returns:
            Parsed JSON from stdout.

        Raises:
            subprocess.TimeoutExpired: If the search takes too long.
            json.JSONDecodeError: If stdout is not valid JSON.
        """
        cmd = ["aivocode", "websearch", *args]
        env = {**os.environ, "EXA_API_KEY": exa_api_key}
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return json.loads(proc.stdout)

    return _run


# ---------------------------------------------------------------------------
# Basic search
# ---------------------------------------------------------------------------


class TestBasicSearch:
    """Basic search — results, fields, and result-count limits."""

    def test_search_returns_results_with_expected_fields(
        self, run_search: Callable[..., dict[str, Any]]
    ) -> None:
        """A default search returns results with title, url, and highlights."""
        data = run_search("Paris", "--num-results", "2")
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
        self, run_search: Callable[..., dict[str, Any]]
    ) -> None:
        """``--num-results`` controls how many results are returned."""
        data = run_search("hello world", "--num-results", "1")
        assert data["success"] is True
        assert len(data["results"]) == 1, (
            f"expected 1 result, got {len(data['results'])}"
        )

        data = run_search("github", "--num-results", "3")
        assert data["success"] is True
        assert len(data["results"]) == 3, (
            f"expected 3 results, got {len(data['results'])}"
        )


# ---------------------------------------------------------------------------
# --type variants
# ---------------------------------------------------------------------------


class TestSearchTypes:
    """--type flag forwards the search type correctly."""

    @pytest.mark.parametrize("stype", ["auto", "fast", "instant", "deep-lite"])
    def test_type_variant_returns_results(
        self, run_search: Callable[..., dict[str, Any]], stype: str
    ) -> None:
        """Every supported ``--type`` value returns valid results."""
        data = run_search(
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


# ---------------------------------------------------------------------------
# Domain filters
# ---------------------------------------------------------------------------


class TestDomainFilters:
    """--include-domains and --exclude-domains flags."""

    def test_include_domains_restricts_urls(
        self, run_search: Callable[..., dict[str, Any]]
    ) -> None:
        """``--include-domains`` constrains all result URLs to the given domain."""
        data = run_search(
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
        self, run_search: Callable[..., dict[str, Any]]
    ) -> None:
        """``--exclude-domains`` removes results from the excluded domain."""
        data = run_search(
            "Paris city guide",
            "--exclude-domains", "wikipedia.org",
            "--num-results", "3",
        )
        assert data["success"] is True
        for r in data["results"]:
            assert "wikipedia.org" not in r["url"], (
                f"expected wikipedia.org excluded, got {r['url']}"
            )

    def test_include_and_exclude_together(
        self, run_search: Callable[..., dict[str, Any]]
    ) -> None:
        """Both ``--include-domains`` and ``--exclude-domains`` work together."""
        data = run_search(
            "python async tutorial",
            "--include-domains", "docs.python.org",
            "--include-domains", "realpython.com",
            "--exclude-domains", "reddit.com",
            "--num-results", "2",
        )
        assert data["success"] is True
        for r in data["results"]:
            url = r["url"]
            assert "docs.python.org" in url or "realpython.com" in url, (
                f"expected allowed domain, got {url}"
            )
            assert "reddit.com" not in url, (
                f"expected reddit.com excluded, got {url}"
            )


# ---------------------------------------------------------------------------
# --full-text
# ---------------------------------------------------------------------------


class TestFullText:
    """--full-text flag switches from highlights to full text content."""

    def test_full_text_returns_text_not_highlights(
        self, run_search: Callable[..., dict[str, Any]]
    ) -> None:
        """``--full-text`` populates ``text`` and omits ``highlights``."""
        data = run_search(
            "France capital", "--full-text", "--num-results", "2"
        )
        assert data["success"] is True
        for r in data["results"]:
            assert isinstance(r.get("text"), str) and len(r["text"]) > 0, (
                f"expected non-empty text field, got {r.get('text')!r}"
            )
            assert r.get("highlights") is None, (
                f"expected no highlights with --full-text, got {r.get('highlights')}"
            )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Graceful handling of missing key, invalid args, and edge cases."""

    def test_missing_api_key(self) -> None:
        """Search fails with a clear error when no API key is available."""
        env = {**os.environ, "EXA_API_KEY": ""}
        proc = subprocess.run(
            ["aivocode", "websearch", "test", "--num-results", "1"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        data = json.loads(proc.stdout)
        assert data["success"] is False, f"expected failure, got {data}"
        assert "error" in data, f"expected error key in {data}"
        assert "API key" in data["error"], f"expected API key error, got {data['error']}"

    def test_invalid_type_rejected_by_argparse(self) -> None:
        """An invalid ``--type`` value is caught by argparse before the API call."""
        env = {**os.environ, "EXA_API_KEY": "dummy"}
        proc = subprocess.run(
            ["aivocode", "websearch", "test", "--type", "nonsense"],
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
