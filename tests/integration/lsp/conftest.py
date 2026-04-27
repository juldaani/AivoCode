"""Pytest configuration for LSP integration tests.

What this file provides
- Session cleanup of leftover temp workspaces.
- lang fixture: class-scoped, parametrized by language. Provides client,
  workspace, and parsed markers for universal tests.
- Isolated fixtures for mutation tests (test_file_changes.py).

Config
- Language definitions loaded from tests/lsp_test.toml.
- Test positions loaded from MARK comments in mock source files.
- Auto-skips tests if the configured language server is not on PATH.
"""

from __future__ import annotations

import glob
import re
import shutil
import tempfile
from builtins import ExceptionGroup
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator

import pytest
import tomllib

from lsp import LspClient, LanguageEntry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER = "## MARK:"  # Python
MARKER_TS = "// MARK:"  # TypeScript


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _symbol_position_before_marker(line: str, marker_index: int) -> int:
    """Return the symbol position for inline LSP marker comments.

    Markers live at the end of declaration lines so humans can see what they
    label. LSP requests, however, must point at the symbol token rather than the
    trailing comment. This helper keeps marker placement readable while making
    ``lang.pos(...)`` usable for rename/references/hover requests.
    """
    code = line[:marker_index]
    if not code.strip():
        return marker_index

    for pattern in (
        r"\b(?:def|function)\s+([A-Za-z_]\w*)",
        r"\bclass\s+([A-Za-z_]\w*)",
        r"\b([A-Za-z_]\w*)\s*\(",
        r"\b([A-Za-z_]\w*)\b",
    ):
        matches = list(re.finditer(pattern, code))
        if matches:
            return matches[-1].start(1)

    return marker_index


def _parse_markers(text: str, prefix: str) -> dict[str, tuple[int, int]]:
    """Parse MARK comments from source text.

    Returns dict mapping marker name to (line_0indexed, char_offset).
    """
    markers: dict[str, tuple[int, int]] = {}
    for line_num, line in enumerate(text.splitlines()):
        idx = line.find(prefix)
        if idx >= 0:
            name = line[idx + len(prefix) :].strip()
            markers[name] = (line_num, _symbol_position_before_marker(line, idx))
    return markers


def _cleanup_tmp_workspaces() -> None:
    """Remove any leftover lsp_* temp workspaces from /tmp."""
    for path in glob.glob(tempfile.gettempdir() + "/lsp_*"):
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# TOML config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LanguageConfig:
    """One language entry from lsp_test.toml."""

    name: str
    server: str
    server_args: tuple[str, ...]
    suffix: str
    mock_repo: str


def _load_languages() -> list[LanguageConfig]:
    """Load language configs from tests/lsp_test.toml."""
    toml_path = _repo_root() / "tests" / "lsp_test.toml"
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return [
        LanguageConfig(
            name=entry["name"],
            server=entry["server"],
            server_args=tuple(entry["server_args"]),
            suffix=entry["suffix"],
            mock_repo=entry["mock_repo"],
        )
        for entry in data["language"]
    ]


LANGUAGES = _load_languages()


# ---------------------------------------------------------------------------
# Session cleanup
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def _cleanup_workspaces_session():
    """Clean up stale temp workspaces before and after the test session."""
    _cleanup_tmp_workspaces()
    yield
    _cleanup_tmp_workspaces()


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def _make_workspace(mock_repo: str, prefix: str) -> Path:
    """Create a temp workspace by copying a mock repo.

    Returns the inner mock_pkg dir path.
    Caller is responsible for cleanup of the parent temp dir.
    """
    src = _repo_root() / "tests" / "data" / "mock_repos" / mock_repo
    dst = Path(tempfile.mkdtemp(prefix=prefix))
    workspace = dst / mock_repo
    shutil.copytree(src, workspace)
    return workspace


# ---------------------------------------------------------------------------
# Universal lang fixture (class-scoped, parametrized by language)
# ---------------------------------------------------------------------------


@dataclass
class LanguageTestData:
    """Test data for one language, provided by the lang fixture."""

    name: str
    client: LspClient
    workspace: Path
    markers: dict[str, tuple[int, int]]
    marker_prefix: str
    src_file: str  # "utils.py" or "index.ts"
    types_file: str  # "types.py" or "types.ts"
    errors_file: str  # "errors.py" or "errors.ts"

    def pos(self, marker: str, *, offset: int = 0) -> tuple[int, int]:
        """Get (line, char) for a named marker, optionally with char offset."""
        line, char = self.markers[marker]
        return (line, char + offset)

    def find_after(self, marker: str, pattern: str) -> tuple[int, int]:
        """Find pattern on the line after the marker."""
        line, _ = self.markers[marker]
        for path in [self.file(self.src_file), self.file(self.types_file)]:
            if path.exists():
                lines = path.read_text(encoding="utf-8").splitlines()
                if line + 1 < len(lines):
                    next_line = lines[line + 1]
                    idx = next_line.find(pattern)
                    if idx >= 0:
                        return (line + 1, idx)
        raise ValueError(f"Pattern '{pattern}' not found after marker '{marker}'")

    def file(self, name: str) -> Path:
        """Get path to a file in the mock_pkg directory."""
        return self.workspace / "mock_pkg" / name

    def supports(self, capability: str) -> bool:
        """Check if the connected server supports a capability."""
        return self.client.supports(capability)


def _make_language_test_data(
    cfg: LanguageConfig,
    client: LspClient,
    workspace: Path,
) -> LanguageTestData:
    """Build LanguageTestData by parsing markers from mock files."""
    marker_prefix = MARKER if cfg.suffix == ".py" else MARKER_TS

    # Determine file names by suffix
    if cfg.suffix == ".py":
        src_name = "utils.py"
    else:
        src_name = "index.ts"
    types_name = f"types{cfg.suffix}"
    errors_name = f"errors{cfg.suffix}"

    src_file = workspace / "mock_pkg" / src_name
    types_file = workspace / "mock_pkg" / types_name

    markers: dict[str, tuple[int, int]] = {}
    for f in [src_file, types_file]:
        if f.exists():
            text = f.read_text(encoding="utf-8")
            markers.update(_parse_markers(text, marker_prefix))

    return LanguageTestData(
        name=cfg.name,
        client=client,
        workspace=workspace,
        markers=markers,
        marker_prefix=marker_prefix,
        src_file=src_name,
        types_file=types_name,
        errors_file=errors_name,
    )


@pytest.fixture(
    scope="class",
    params=LANGUAGES,
    ids=lambda c: c.name,
)
async def lang(request) -> AsyncGenerator[LanguageTestData, None]:
    """Parametrized fixture providing test data for each available language.

    Each test class runs once per language defined in lsp_test.toml.
    Skips if the language server is not on PATH.
    """
    cfg: LanguageConfig = request.param

    # Check server availability
    if shutil.which(cfg.server) is None:
        pytest.skip(f"{cfg.server} not found on PATH")

    # Create workspace
    workspace = _make_workspace(cfg.mock_repo, f"lsp_{cfg.name}_")

    # Build LanguageEntry
    entry = LanguageEntry(
        name=cfg.name,
        suffixes=(cfg.suffix,),
        server=cfg.server,
        server_args=cfg.server_args,
    )

    # Start client
    try:
        client = LspClient(lang_entry=entry, workspace=workspace)
        await client.__aenter__()
    except BaseException as exc:
        shutil.rmtree(workspace.parent, ignore_errors=True)
        if isinstance(exc, ExceptionGroup):
            pytest.skip(f"{cfg.server} failed to start: {exc}")
        raise

    test_data = _make_language_test_data(cfg, client, workspace)

    yield test_data

    await client.shutdown()
    shutil.rmtree(workspace.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Isolated fixtures (for mutation tests in test_file_changes.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def python_language_entry() -> LanguageEntry:
    """Return a LanguageEntry for Python (basedpyright)."""
    return LanguageEntry(
        name="python",
        suffixes=(".py", ".pyi"),
        server="basedpyright-langserver",
        server_args=("--stdio",),
    )


@pytest.fixture(scope="class")
def python_workspace_isolated():
    """Fresh Python mock repo workspace per test class."""
    workspace = _make_workspace("python", "lsp_python_isolated_")
    yield workspace
    shutil.rmtree(workspace.parent, ignore_errors=True)


@pytest.fixture(scope="class")
async def python_client_isolated(
    python_language_entry: LanguageEntry,
    python_workspace_isolated: Path,
) -> AsyncGenerator[LspClient, None]:
    """Fresh LspClient per test class with its own workspace."""
    if shutil.which(python_language_entry.server) is None:
        pytest.skip(f"{python_language_entry.server} not found on PATH")

    try:
        client = LspClient(
            lang_entry=python_language_entry,
            workspace=python_workspace_isolated,
        )
        await client.__aenter__()
    except BaseException as exc:
        if isinstance(exc, ExceptionGroup):
            pytest.skip(f"basedpyright-langserver failed to start: {exc}")
        raise
    yield client
    await client.shutdown()
