#!/usr/bin/env python3
"""Standalone demo showing how to use the file watcher from the command line.

What it does
- Watches one or more repository directories for file changes.
- Prints each batch of events to stdout with human-readable labels.
- Demonstrates the main configuration options available via CLI flags.

Why this exists
- Quick manual testing of the watcher without writing code.
- Reference example for how to configure and invoke the importable API
  (`file_watcher.watcher.watch_repos` and `awatch_repos`).

How to read this file
- Entry point: `main()` parses CLI args, builds a `WatchConfig`, and calls
  the library function `watch_repos()` in a loop.
- Configuration is split into: (1) watchfiles tuning (debounce, step, polling)
  and (2) filtering (defaults, gitignore, custom excludes).
- The loop prints a batch header, any warnings, and sorted event lines.

Usage
- Module invocation (recommended): python -m file_watcher.how_to_use /path/to/repo
- Script invocation also works: python file_watcher/how_to_use.py /path/to/repo

See Also
- file_watcher/README.md for CLI examples and notes.
- file_watcher.watcher for the importable API used by production code.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from watchfiles import Change

# When executed as a script (`python file_watcher/how_to_use.py`), Python sets
# sys.path[0] to `.../file_watcher`, which breaks importing the `file_watcher`
# package. Add the repo root to sys.path to support both script and module usage.
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from file_watcher.types import WatchConfig  # noqa: E402
from file_watcher.watcher import build_startup_info, watch_repos  # noqa: E402

# Human-readable labels for the Change enum values used in output.
_CHANGE_LABELS: dict[Change, str] = {
    Change.added: "ADDED",
    Change.modified: "MODIFIED",
    Change.deleted: "DELETED",
}


def _split_csv(value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated string into a tuple of trimmed non-empty items.

    Used for CLI flags that accept comma-separated lists (e.g. --ignore-dirs).
    Returns an empty tuple if the input is None or empty.
    """
    if not value:
        return ()
    parts = [p.strip() for p in value.split(",")]
    return tuple(p for p in parts if p)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments for the watcher demo.

    Arguments are grouped into:
    - Positional: paths to watch (one or more directories).
    - Filtering: toggles for defaults/gitignore and custom exclude options.
    - Watch tuning: debounce, step, recursion, polling behavior.
    """
    parser = argparse.ArgumentParser(
        prog="file_watcher.how_to_use",
        description="Demo: watch one or more repository directories and print file change events.",
    )
    parser.add_argument(
        "paths_to_repo",
        type=Path,
        nargs="+",
        help="One or more repository directories to watch.",
    )
    parser.add_argument(
        "--no-defaults-filter",
        action="store_true",
        help="Disable watchfiles' default filtering (e.g. include .git).",
    )
    parser.add_argument(
        "--no-gitignore-filter",
        action="store_true",
        help="Disable gitignore filtering (enabled by default when git is available).",
    )
    parser.add_argument(
        "--ignore-dirs",
        default=None,
        help='Comma-separated directory names to ignore (e.g. ".cache,dist").',
    )
    parser.add_argument(
        "--ignore-entity-globs",
        default=None,
        help='Comma-separated glob patterns to ignore by basename (e.g. "*.log,.goutputstream-*").',
    )
    parser.add_argument(
        "--ignore-entity-regex",
        default=None,
        help='Comma-separated regex patterns to ignore by basename (advanced).',
    )
    parser.add_argument(
        "--ignore-paths",
        default=None,
        help=(
            "Comma-separated paths to ignore. Absolute paths are used as-is; relative paths are "
            "expanded under each watched root."
        ),
    )
    parser.add_argument(
        "--debounce-ms",
        type=int,
        default=1600,
        help="Max time in ms to group changes before yielding (default: 1600).",
    )
    parser.add_argument(
        "--step-ms",
        type=int,
        default=50,
        help="Time in ms to wait for more changes once changes start (default: 50).",
    )
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Watch only the top-level directory (default: recursive).",
    )
    parser.add_argument(
        "--ignore-permission-denied",
        action="store_true",
        help="Ignore permission denied errors while watching.",
    )
    parser.add_argument(
        "--force-polling",
        dest="force_polling",
        action="store_true",
        help="Force polling instead of filesystem notifications.",
    )
    parser.add_argument(
        "--no-force-polling",
        dest="force_polling",
        action="store_false",
        help="Disable forced polling (use native notifications when possible).",
    )
    parser.add_argument(
        "--poll-delay-ms",
        type=int,
        default=300,
        help="Delay in ms between polls when force_polling is enabled (default: 300).",
    )
    parser.set_defaults(force_polling=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the watcher demo: parse args, print configuration, and stream batches.

    Returns
    - 0 on clean exit (Ctrl+C or natural end).
    - 2 on invalid input (e.g. non-existent directory).

    Side effects
    - Prints watcher configuration and event batches to stdout.
    - On gitignore errors, prints warnings but continues (fail-open).
    """
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    roots = list(args.paths_to_repo)
    cfg = WatchConfig(
        recursive=not args.non_recursive,
        debounce_ms=args.debounce_ms,
        step_ms=args.step_ms,
        force_polling=args.force_polling,
        poll_delay_ms=args.poll_delay_ms,
        ignore_permission_denied=args.ignore_permission_denied,
        defaults_filter=not args.no_defaults_filter,
        gitignore_filter=not args.no_gitignore_filter,
        ignore_dirs=_split_csv(args.ignore_dirs),
        ignore_entity_globs=_split_csv(args.ignore_entity_globs),
        ignore_entity_regex=_split_csv(args.ignore_entity_regex),
        ignore_paths=_split_csv(args.ignore_paths),
    )

    # Validate roots and compute effective filter configuration.
    try:
        root_info, watch_filter, git_status = build_startup_info(roots, cfg)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Print startup banner with effective configuration.
    defaults_label = "on" if cfg.defaults_filter else "off"
    gitignore_label = "on" if cfg.gitignore_filter else "off"
    print(
        "Watching: "
        f"{', '.join(str(r) for r in root_info.roots)} "
        f"(recursive={cfg.recursive}, defaults_filter={defaults_label}, gitignore_filter={gitignore_label}, "
        f"debounce_ms={cfg.debounce_ms}, step_ms={cfg.step_ms})",
        flush=True,
    )
    print("Press Ctrl+C to stop.", flush=True)

    # Warn about nested roots; attribution prefers deepest/longest matching root.
    if root_info.nested_pairs:
        print("Warning: nested watched roots detected:", flush=True)
        for outer, inner in root_info.nested_pairs:
            print(f"- {outer} contains {inner}", flush=True)
        print(
            "Attribution: when multiple roots match an event path, the deepest/longest root is used.",
            flush=True,
        )

    # Print per-root gitignore status.
    if cfg.gitignore_filter:
        if not git_status.git_available:
            print("Gitignore filter: enabled, but git not found on PATH (no-op).", flush=True)
        else:
            for r in root_info.roots:
                status = "ok" if git_status.root_ok.get(r, False) else "unavailable (not a git worktree)"
                print(f"Gitignore filter: {root_info.labels[r]} -> {status}", flush=True)

    # Print effective watchfiles filter configuration.
    print("Watchfiles filter:", flush=True)
    if watch_filter is None:
        print("- watch_filter: None (no watchfiles-level filtering)", flush=True)
    else:
        ignore_dirs = ", ".join(watch_filter.ignore_dirs)
        ignore_entity_patterns = ", ".join(watch_filter.ignore_entity_patterns)
        ignore_paths = ", ".join(str(p) for p in watch_filter.ignore_paths)
        print(f"- ignore_dirs ({len(watch_filter.ignore_dirs)}): {ignore_dirs or '(none)'}", flush=True)
        print(
            f"- ignore_entity_patterns ({len(watch_filter.ignore_entity_patterns)}): "
            f"{ignore_entity_patterns or '(none)'}",
            flush=True,
        )
        print(
            f"- ignore_paths ({len(watch_filter.ignore_paths)}): {ignore_paths or '(none)'}",
            flush=True,
        )

    # Main loop: yield batches and print events.
    try:
        for batch in watch_repos(root_info.roots, cfg):
            ts = batch.ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"{ts}  --- batch: raw={batch.raw} filtered={batch.filtered} ---", flush=True)

            # Print any warnings (e.g. gitignore subprocess failures).
            for w in batch.warnings:
                print(f"{ts}  warning: {w}", flush=True)

            # Sort events for stable, readable output.
            def sort_key(ev):
                return ev.repo_label, ev.rel_path, int(ev.change)

            for ev in sorted(batch.events, key=sort_key):
                label = _CHANGE_LABELS.get(ev.change, str(ev.change))
                print(f"{ts}  {label:<8}  [{ev.repo_label}] {ev.rel_path}", flush=True)
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
