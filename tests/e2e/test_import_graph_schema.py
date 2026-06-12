"""Schema tests for import-graph tools — output shape validation.

Tests the 3 new codebase functions directly (async) against the
mock_pkg test data.  Does NOT require a running REST server —
the daemon is auto-started via ``ensure_daemon``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codebase import affected_test_files, import_dependencies, import_dependents

_FIXTURE = str((Path(__file__).parent.parent.parent / "tests" / "data" / "mock_repos" / "python" / "mock_pkg" / "fixtures_classes.py").resolve())


# ═══════════════════════════════════════════════════════════════════════════════
# import_dependents
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_import_dependents_top_level_keys():
    result = await import_dependents(_FIXTURE, depth=2)
    assert set(result.keys()) >= {"file", "dependents", "depth", "info", "query"}


@pytest.mark.anyio
async def test_import_dependents_entry_shape():
    result = await import_dependents(_FIXTURE, depth=2)
    for entry in result["dependents"]:
        assert isinstance(entry, dict)
        assert "file" in entry
        assert "depth" in entry
        assert isinstance(entry["file"], str)
        assert isinstance(entry["depth"], int)
        assert entry["depth"] >= 1


@pytest.mark.anyio
async def test_import_dependents_info_shape():
    result = await import_dependents(_FIXTURE, depth=2)
    info = result["info"]
    assert isinstance(info["files_indexed"], int)
    assert isinstance(info["files_skipped"], int)
    assert isinstance(info["errors"], list)
    assert info["files_indexed"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# import_dependencies
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_import_dependencies_top_level_keys():
    result = await import_dependencies(_FIXTURE)
    assert set(result.keys()) >= {"file", "dependencies", "info", "query"}


@pytest.mark.anyio
async def test_import_dependencies_list_of_strings():
    result = await import_dependencies(_FIXTURE)
    assert isinstance(result["dependencies"], list)
    for dep in result["dependencies"]:
        assert isinstance(dep, str)


# ═══════════════════════════════════════════════════════════════════════════════
# affected_test_files
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_affected_test_files_top_level_keys():
    result = await affected_test_files(_FIXTURE, depth=4)
    assert set(result.keys()) >= {"file", "affected_test_files", "depth", "info", "query"}


@pytest.mark.anyio
async def test_affected_test_files_entry_shape():
    result = await affected_test_files(_FIXTURE, depth=4)
    for entry in result["affected_test_files"]:
        assert isinstance(entry, dict)
        assert "file" in entry
        assert "depth" in entry
        assert isinstance(entry["file"], str)
        assert isinstance(entry["depth"], int)


@pytest.mark.anyio
async def test_affected_test_files_contains_test_mock():
    result = await affected_test_files(_FIXTURE, depth=4)
    test_files = [t["file"] for t in result["affected_test_files"]]
    assert any("test_mock" in f for f in test_files), \
        f"test_mock.py not in affected tests: {test_files}"
