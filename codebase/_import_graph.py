"""Workspace-wide reverse import graph with incremental update.

Why this exists
- The import graph answers "who imports this file?" and "what does this
  file import?" without any LSP queries.  It is the foundation for tools
  like ``affected_tests``, ``dependents``, ``dependencies``, ``orphans``,
  and ``hubs``.

How it works
- On ``build_full()``, walks all source files in the workspace, parses
  imports via the registered language handlers, and builds forward and
  reverse adjacency sets.
- The ``update()`` method accepts a list of changed file paths (from the
  file watcher) and incrementally adds, removes, or refreshes edges.
- All public query methods operate on workspace-relative paths.

How to use
    graph = ImportGraph(Path("/workspaces/myproject"))
    graph.build_full()
    who = graph.dependents("src/utils.py", depth=2)
    what = graph.dependencies("src/utils.py")
    tests = graph.affected_tests("src/utils.py", depth=4)
"""

from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path

from codebase._lang_handlers import get_handler


class ImportGraph:
    """Reverse import graph for a workspace, with lazy incremental update.

    All internal edges use workspace-relative paths (strings).  Absolute
    paths are resolved only during build/update and immediately relativised.
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()

        # Forward edges:  importing_file → {imported_files}
        self._forward: dict[str, set[str]] = {}
        # Reverse edges:  imported_file → {importing_files}
        self._reverse: dict[str, set[str]] = {}
        # Module-path index:  "pkg.module" → rel_file_path
        self._file_index: dict[str, str] = {}

        # Build metadata.
        self._built_at: float = 0.0
        self._files_indexed: int = 0
        self._files_skipped: int = 0
        self._errors: list[dict] = []

    # ── Public query API ───────────────────────────────────────────────────

    def dependents(self, file: str, *, depth: int = 1) -> list[dict]:
        """Files that (transitively) import *file*, up to *depth*.

        Returns a list of ``{"file": str, "depth": int}`` dicts sorted by
        depth (shallowest first), then by file path.
        """
        if file not in self._reverse and file not in self._forward:
            return []

        seen: set[str] = {file}
        result: list[dict] = []
        queue: deque[tuple[str, int]] = deque()
        queue.append((file, 0))

        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for importer in self._reverse.get(current, ()):
                if importer not in seen:
                    seen.add(importer)
                    result.append({"file": importer, "depth": d + 1})
                    queue.append((importer, d + 1))

        result.sort(key=lambda x: (x["depth"], x["file"]))
        return result

    def dependencies(self, file: str) -> list[str]:
        """Files that *file* directly imports (forward edges)."""
        return sorted(self._forward.get(file, ()))

    def direct_dependents(self, file: str) -> list[str]:
        """Files that directly import *file* (reverse edges, depth=1)."""
        return sorted(self._reverse.get(file, ()))

    def affected_tests(self, file: str, *, depth: int = 4) -> list[dict]:
        """``dependents(file, depth)`` filtered to test files only."""
        deps = self.dependents(file, depth=depth)
        result: list[dict] = []
        for d in deps:
            handler = get_handler(d["file"])
            if handler is not None and handler.is_test_file(d["file"]):
                result.append(d)
        return result

    def files(self) -> frozenset[str]:
        """All indexed source files."""
        return frozenset(self._forward.keys()) | frozenset(self._reverse.keys())

    def info(self) -> dict:
        """Build metadata: files indexed, skipped, and any errors."""
        return {
            "files_indexed": self._files_indexed,
            "files_skipped": self._files_skipped,
            "errors": list(self._errors),
            "built_at": self._built_at,
        }

    # ── Build / rebuild ────────────────────────────────────────────────────

    def build_full(self) -> None:
        """Walk the workspace and build the complete import graph.

        Idempotent — clears any previous state before building.

        Uses a two-pass approach: first, all files are scanned to build
        the module-path index; second, imports are resolved against the
        now-complete index.
        """
        self._clear()

        # ── Pass 1: collect all module paths ──────────────────────────
        all_files: list[Path] = []
        for abs_path in self._walk_source_files():
            all_files.append(abs_path)
            handler = get_handler(abs_path)
            if handler is not None:
                mp = handler.module_path(abs_path, self._workspace)
                if mp is not None:
                    rel = self._relativize(abs_path)
                    if rel is not None:
                        self._file_index[mp] = rel

        # ── Pass 2: extract imports and add edges ─────────────────────
        for abs_path in all_files:
            self._add_file(abs_path)

        self._built_at = time.time()

    def update(self, changed: list[Path]) -> None:
        """Incrementally update the graph for a list of changed files.

        *changed* is a list of absolute ``Path`` objects (typically from
        file-watcher events).  Files that no longer exist are removed;
        files that exist are re-parsed and their edges refreshed.
        """
        for abs_path in changed:
            rel = self._relativize(abs_path)
            if rel is None:
                continue
            self._remove_file(rel)
            if abs_path.is_file() and get_handler(abs_path) is not None:
                self._add_file(abs_path)
        self._built_at = time.time()

    # ── Internal: file-level operations ────────────────────────────────────

    def _add_file(self, abs_path: Path) -> None:
        """Parse *abs_path* and add its import edges to the graph."""
        rel = self._relativize(abs_path)
        if rel is None:
            return

        handler = get_handler(abs_path)
        if handler is None:
            return

        try:
            raw_imports = handler.extract_imports(abs_path)
        except Exception as exc:
            self._files_skipped += 1
            self._errors.append({
                "file": rel,
                "reason": f"parse error: {exc}",
            })
            return

        # Register this file in the module-path index.
        mp = handler.module_path(abs_path, self._workspace)
        if mp is not None:
            self._file_index[mp] = rel

        imported: set[str] = set()
        for raw in raw_imports:
            try:
                resolved = handler.resolve_import(
                    raw, abs_path,
                    {k: self._workspace / v for k, v in self._file_index.items()},
                )
            except Exception:
                resolved = None

            if resolved is not None:
                resolved_rel = self._relativize(resolved)
                if resolved_rel is not None:
                    imported.add(resolved_rel)

        self._forward[rel] = imported
        for target in imported:
            self._reverse.setdefault(target, set()).add(rel)

        # Ensure *rel* exists as a key in _reverse (so dependents() finds it
        # even when nothing imports it).
        self._reverse.setdefault(rel, set())

        self._files_indexed += 1

    def _remove_file(self, rel: str) -> None:
        """Remove all edges involving *rel* from the graph.

        *rel* must be a workspace-relative path string (as returned by
        ``_relativize``).  Only decrements ``_files_indexed`` when the
        file was actually present in the graph (avoids drift for files
        that were never indexed, e.g. non-code files that pass through
        ``update()`` from watcher events).
        """
        # Track whether the file was actually in the graph so we only
        # decrement _files_indexed for genuine removals.
        was_in_graph = False

        # Remove forward edges: for each file rel imported, remove rel
        # from that file's reverse set.
        for imported in self._forward.pop(rel, ()):
            was_in_graph = True
            rev = self._reverse.get(imported)
            if rev is not None:
                rev.discard(rel)

        # Remove reverse edges (who imports rel).
        if self._reverse.pop(rel, None) is not None:
            was_in_graph = True

        # Remove from module-path index.
        for mp, path in list(self._file_index.items()):
            if path == rel:
                was_in_graph = True
                del self._file_index[mp]

        if was_in_graph:
            self._files_indexed = max(0, self._files_indexed - 1)

    def _clear(self) -> None:
        """Reset all internal state."""
        self._forward.clear()
        self._reverse.clear()
        self._file_index.clear()
        self._files_indexed = 0
        self._files_skipped = 0
        self._errors.clear()

    # ── Internal: workspace helpers ─────────────────────────────────────────

    def _relativize(self, abs_path: Path) -> str | None:
        """Convert an absolute path to a workspace-relative string."""
        try:
            return str(abs_path.resolve().relative_to(self._workspace))
        except ValueError:
            return None

    def _walk_source_files(self):
        """Yield absolute paths of all source files in the workspace."""
        for root, dirs, files in os.walk(self._workspace):
            # Skip hidden directories and common noise.
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d not in ("__pycache__", "node_modules", ".venv", "venv",
                              ".git", ".tox", ".eggs", ".mypy_cache",
                              ".pytest_cache", ".ruff_cache", "dist", "build",
                              "*.egg-info")
            ]
            for name in files:
                abs_path = Path(root) / name
                handler = get_handler(abs_path)
                if handler is None:
                    continue
                yield abs_path
