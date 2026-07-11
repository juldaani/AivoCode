"""Unit tests for the URL‑verification logic in the unified JSON cache.

Tests cover:
- ``_read_cache_markdown`` returns ``None`` when the stored URL doesn't match.
- ``_read_cache_links`` returns ``None`` when the stored URL doesn't match.
- Backward‑compat: old cache files without a ``url`` field are still trusted.
- Matching URL returns the expected content.
"""

from __future__ import annotations

import json
import os

import pytest

from web_ops.fetcher import (
    _read_cache_markdown,
    _read_cache_links,
    _write_cache,
    _cache_path,
    _cache_key,
)

URL_FOO = "https://example.com/foo"
URL_BAR = "https://example.com/bar"
URL_BAZ = "https://example.com/baz"


# ── Helpers ───────────────────────────────────────────────────────────────


def _write_raw(path: str, data: dict) -> None:
    """Write a raw JSON dict to disk — bypasses ``_write_cache``."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

def _rm(path: str) -> None:
    """Safely remove a file; ignore if missing."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# ── Fixture ───────────────────────────────────────────────────────────────


@pytest.fixture
def cache_dirs() -> list[str]:
    """Paths for the three test cache entries so we can clean them up."""
    paths = [str(_cache_path(u)) for u in (URL_FOO, URL_BAR, URL_BAZ)]
    # Pre‑clean in case a previous run left files.
    for p in paths:
        _rm(p)
    yield paths
    for p in paths:
        _rm(p)


# ── _read_cache_markdown ──────────────────────────────────────────────────


class TestReadCacheMarkdown:
    """``_read_cache_markdown`` URL‑verification behaviour."""

    def test_matching_url_returns_markdown(self, cache_dirs):
        """A cache entry with a matching url field returns the stored markdown."""
        _write_cache(URL_FOO, "hello markdown")
        result = _read_cache_markdown(URL_FOO)
        assert result == "hello markdown"

    def test_mismatched_url_returns_none(self, cache_dirs):
        """A cache entry whose ``url`` field differs from the lookup URL
        returns ``None`` — the caller should treat it as a cache miss."""
        # Write a valid entry for URL_FOO.
        _write_cache(URL_FOO, "correct content")
        # Manually overwrite the file with URL_BAR's content so the
        # *key* matches URL_FOO but the *url* field is URL_BAR.
        path_foo = str(_cache_path(URL_FOO))
        _write_raw(path_foo, {"url": URL_BAR, "markdown": "wrong content"})
        result = _read_cache_markdown(URL_FOO)
        assert result is None

    def test_identical_urls_match(self, cache_dirs):
        """Two identical URL strings (same SHA‑256 key) pass verification."""
        _write_cache(URL_FOO, "content A")
        result = _read_cache_markdown(URL_FOO)
        assert result == "content A"

    def test_old_cache_without_url_field_trusted(self, cache_dirs):
        """Pre‑fix cache files lacking a ``url`` field are treated as valid
        (backward‑compat)."""
        path_foo = str(_cache_path(URL_FOO))
        _write_raw(path_foo, {"markdown": "legacy content"})
        result = _read_cache_markdown(URL_FOO)
        assert result == "legacy content"

    def test_different_urls_produce_different_keys(self):
        """Sanity check: two different URLs produce different file names,
        so the mismatch scenario is due to cache corruption, not key collision."""
        assert _cache_key(URL_FOO) != _cache_key(URL_BAR)


# ── _read_cache_links ─────────────────────────────────────────────────────


class TestReadCacheLinks:
    """``_read_cache_links`` URL‑verification behaviour."""

    def test_matching_url_returns_links(self, cache_dirs):
        links = {"internal": [{"href": "/a", "text": "A"}]}
        _write_cache(URL_FOO, "md", links=links)
        result = _read_cache_links(URL_FOO)
        assert result == links

    def test_mismatched_url_returns_none(self, cache_dirs):
        _write_cache(URL_FOO, "md", links={"internal": [{"href": "/a", "text": "A"}]})
        path_foo = str(_cache_path(URL_FOO))
        _write_raw(path_foo, {"url": URL_BAR, "markdown": "md",
                               "links": {"internal": []}})
        result = _read_cache_links(URL_FOO)
        assert result is None

    def test_old_cache_without_url_field_trusted(self, cache_dirs):
        path_foo = str(_cache_path(URL_FOO))
        links = {"internal": [{"href": "/a", "text": "A"}]}
        _write_raw(path_foo, {"markdown": "md", "links": links})
        result = _read_cache_links(URL_FOO)
        assert result == links


# ── _write_cache ──────────────────────────────────────────────────────────


class TestWriteCache:
    """``_write_cache`` stores the URL for later verification."""

    def test_url_field_written(self, cache_dirs):
        _write_cache(URL_FOO, "content")
        path = str(_cache_path(URL_FOO))
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["url"] == URL_FOO
        assert data["markdown"] == "content"

    def test_url_field_present_with_links(self, cache_dirs):
        links = {"internal": [{"href": "/a", "text": "A"}]}
        _write_cache(URL_FOO, "md", links=links)
        path = str(_cache_path(URL_FOO))
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["url"] == URL_FOO
        assert data["links"] == links