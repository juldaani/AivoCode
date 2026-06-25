"""Repository architecture from the import graph.

Computes a high-level structural view of the codebase — a nested directory
tree with per-folder import relationships, entry points, and hotspot files —
purely from the tree-sitter import graph (zero LSP calls).

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


def _collapse_empty_chains(tree: dict[str, dict]) -> dict[str, dict]:
    """Collapse single-child empty directories in the tree.

    When a directory has 0 direct files and exactly 1 subfolder, merge the
    directory name into the child's key and promote the child.  Processed
    bottom-up via recursion so chains of any length collapse into a single
    composite key (e.g. ``tests/data/mock_repos/python`` instead of four
    nested single-child levels).
    """
    collapsed: dict[str, dict] = {}
    for key, node in sorted(tree.items()):
        # Recursively collapse children first (bottom-up).
        if node.get("folders"):
            node["folders"] = _collapse_empty_chains(node["folders"])

        # Merge: 0 direct files + exactly 1 subfolder → collapse.
        if node.get("files", 0) == 0 and len(node.get("folders", {})) == 1:
            child_key, child_value = next(iter(node["folders"].items()))
            merged_key = f"{key}/{child_key}"
            collapsed[merged_key] = child_value
        else:
            collapsed[key] = node

    return collapsed


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
    ``summary``.  The ``structure`` is a nested directory tree where
    every folder has ``files`` (direct-file count), ``folders``
    (subdirectory entries, recursively), ``imports`` (top-level dirs
    this subtree imports from), and ``imported_by`` (top-level dirs
    that import from this subtree).  Empty single-child chains are
    collapsed to keep the tree compact.
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

    # ── 4. Structure (nested dir tree) ──────────────────────────────

    # 4a. Map every directory → all files in its subtree.
    dir_files: dict[str, list[str]] = defaultdict(list)
    for f in all_files:
        parts = Path(f).parts
        # Register *f* under every ancestor directory.
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            dir_files[prefix].append(f)

    # 4b. Pre-compute imports / imported-by per directory.
    # "imports" are top-level dirs whose files are imported by files
    # in this subtree.  "imported_by" are top-level dirs whose files
    # import from this subtree.
    dir_imports: dict[str, list[str]] = {}
    dir_imported_by: dict[str, list[str]] = {}

    for d, files_in_dir in dir_files.items():
        this_top = d.split("/")[0]

        # -- imports --
        imps: set[str] = set()
        for f in files_in_dir:
            for dep in graph.dependencies(f):
                dep_parts = Path(dep).parts
                if len(dep_parts) >= 2 and dep_parts[0] != this_top:
                    imps.add(dep_parts[0])
        dir_imports[d] = sorted(imps)

        # -- imported_by --
        ib: set[str] = set()
        for other_dir, other_files in dir_files.items():
            if other_dir.split("/")[0] == this_top:
                continue  # same top-level dir → internal, skip
            for other_f in other_files:
                for dep in graph.dependencies(other_f):
                    dep_parts = Path(dep).parts
                    if len(dep_parts) >= 2 and dep_parts[0] == this_top:
                        ib.add(other_dir.split("/")[0])
                        break  # one edge is enough
                else:
                    continue
                break
        dir_imported_by[d] = sorted(ib)

    # 4c. Build the nested tree recursively.
    def _build_node(dir_path: str) -> dict:
        """Recursively build a structure node for *dir_path*."""
        direct_files: set[str] = set()
        subdirs: set[str] = set()

        for f in dir_files.get(dir_path, []):
            rel = f[len(dir_path) + 1:] if dir_path else f
            if "/" in rel:
                subdirs.add(rel.split("/")[0])
            else:
                direct_files.add(f)

        folders: dict[str, dict] = {}
        for sub in sorted(subdirs):
            sub_path = f"{dir_path}/{sub}" if dir_path else sub
            folders[sub] = _build_node(sub_path)

        return {
            "files": len(direct_files),
            "folders": folders,
            "imports": dir_imports.get(dir_path, []),
            "imported_by": dir_imported_by.get(dir_path, []),
        }

    # Build top-level entries (dirs directly under workspace root).
    top_dirs = sorted({d for d in dir_files if "/" not in d})
    raw_structure: dict[str, dict] = {}
    for d in top_dirs:
        node = _build_node(d)
        # Collapse empty chains within this top-level dir's subfolders
        # (but never merge the top-level entry itself — the user should
        # always see every top-level directory).
        if node.get("folders"):
            node["folders"] = _collapse_empty_chains(node["folders"])
        raw_structure[d] = node

    structure = raw_structure

    # Count total directories (after internal merge) for summary.
    def _count_dirs(node: dict) -> int:
        return 1 + sum(_count_dirs(c) for c in node.get("folders", {}).values())

    total_dirs = sum(_count_dirs(node) for node in structure.values())

    return {
        "structure": structure,
        "entry_points": entry_points,
        "hotspots": hotspot_entries,
        "summary": {
            "total_files": len(all_files),
            "total_dirs": total_dirs,
        },
    }
