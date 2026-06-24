"""Repository architecture from the import graph.

Computes a high-level structural view of the codebase — directory-level
import relationships, entry points, and hotspot files — purely from the
tree-sitter import graph (zero LSP calls).

Entry point
    ``_compute_architecture(graph, hotspots)`` → architecture dict.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codebase._import_graph import ImportGraph

# Transitive depth to use when computing dependents counts.  Must be
# larger than the deepest import chain in the workspace so that every
# reachable file is counted exactly once.
_MAX_TRANSITIVE_DEPTH = 99999


def _is_test_file(file_path: str, get_handler) -> bool:
    """``True`` when *file_path* matches the test-file naming convention."""
    handler = get_handler(file_path)
    return handler is not None and handler.is_test_file(file_path)


def _compute_architecture(
    graph: ImportGraph,
    hotspots: int = 20,
) -> dict:
    """Return a repo architecture report from *graph*.

    Parameters
    ----------
    graph : ImportGraph
        A fully-built import graph (forward + reverse edges populated).
    hotspots : int
        Max number of hotspot files to return (default 20).

    Returns
    -------
    dict with keys ``structure``, ``entry_points``, ``hotspots``,
    ``summary``.
    """
    from codebase._lang_handlers import get_handler

    all_files = sorted(graph.files())

    # ── 1. Transitive dependents per file ───────────────────────────
    transitive: dict[str, int] = {}
    for f in all_files:
        deps = graph.dependents(f, depth=_MAX_TRANSITIVE_DEPTH)
        transitive[f] = len(deps)

    # ── 2. Entry points (no transitive dependents, non-test) ───────
    entry_points = sorted(
        f for f, count in transitive.items()
        if count == 0 and not _is_test_file(f, get_handler)
    )

    # ── 3. Hotspots (top N by transitive DESC, >=2) ─────────────────
    ranked = sorted(
        ((f, count) for f, count in transitive.items() if count >= 2),
        key=lambda x: (-x[1], x[0]),
    )[:hotspots]

    hotspot_entries: list[dict] = []
    for f, trans in ranked:
        direct = len([d for d in graph.dependents(f, depth=1) if d["file"] != f])
        hotspot_entries.append({
            "file": f,
            "imported_by": direct,
            "imported_by_transitive": trans,
        })

    # ── 4. Structure (dir-level grouping) ───────────────────────────
    dir_files: dict[str, list[str]] = defaultdict(list)
    for f in all_files:
        parts = Path(f).parts
        if len(parts) >= 2:
            dir_files[parts[0]].append(f)

    structure: dict[str, dict] = {}
    for dir_name in sorted(dir_files):
        fnames = dir_files[dir_name]
        # Compute dir-level import edges: if any file in this dir
        # imports any file in another dir, record the edge.
        dir_imports: set[str] = set()
        dir_imported_by: set[str] = set()
        for fname in fnames:
            for dep in graph.dependencies(fname):
                dep_parts = Path(dep).parts
                if len(dep_parts) >= 2 and dep_parts[0] != dir_name:
                    dir_imports.add(dep_parts[0])
        # Compute reverse edges by checking all files in other dirs.
        for other_dir in dir_files:
            if other_dir == dir_name:
                continue
            for other_f in dir_files[other_dir]:
                if any(
                    Path(d).parts[0] == dir_name
                    for d in graph.dependencies(other_f)
                ):
                    dir_imported_by.add(other_dir)
                    break  # one edge is enough

        structure[dir_name] = {
            "files": len(fnames),
            "imports": sorted(dir_imports),
            "imported_by": sorted(dir_imported_by),
        }

    return {
        "structure": structure,
        "entry_points": entry_points,
        "hotspots": hotspot_entries,
        "summary": {
            "total_files": len(all_files),
            "total_dirs": len(structure),
        },
    }
