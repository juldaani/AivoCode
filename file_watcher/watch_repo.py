#!/usr/bin/env python3
"""Watch a repository directory and print file changes.

This is a standalone prototype script (ver0.1) using the `watchfiles` library.

Behavior
- Watches a directory recursively by default.
- Prints a batch header followed by one line per change.
- Uses `watchfiles.DefaultFilter` by default (ignores `.git/`, caches, etc.).
- Optionally filters changes using gitignore rules via `git check-ignore`.
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from watchfiles import Change, DefaultFilter, watch

_CHANGE_LABELS: dict[Change, str] = {
    Change.added: "ADDED",
    Change.modified: "MODIFIED",
    Change.deleted: "DELETED",
}


def _unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    # Basic comma-separated list parsing.
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


def _glob_to_regex(glob_pat: str) -> str:
    """Translate a shell-style glob to a regex string.

    watchfiles' `ignore_entity_patterns` expects regex strings.
    """

    # fnmatch.translate returns a regex that matches the whole string and ends with \Z.
    return fnmatch.translate(glob_pat)


def _build_watchfiles_filter(
    *,
    use_defaults_filter: bool,
    repo_roots: Sequence[Path],
    ignore_dirs_csv: str | None,
    ignore_entity_globs_csv: str | None,
    ignore_entity_regex_csv: str | None,
    ignore_paths_csv: str | None,
) -> DefaultFilter | None:
    custom_ignore_dirs = _split_csv(ignore_dirs_csv)
    custom_ignore_entity_globs = _split_csv(ignore_entity_globs_csv)
    custom_ignore_entity_regex = _split_csv(ignore_entity_regex_csv)
    custom_ignore_paths = _split_csv(ignore_paths_csv)

    ignore_dirs: list[str] = []
    ignore_entity_patterns: list[str] = []
    ignore_paths: list[Path] = []

    if use_defaults_filter:
        ignore_dirs.extend(DefaultFilter.ignore_dirs)
        ignore_entity_patterns.extend(DefaultFilter.ignore_entity_patterns)

    ignore_dirs.extend(custom_ignore_dirs)
    ignore_entity_patterns.extend(_glob_to_regex(g) for g in custom_ignore_entity_globs)
    ignore_entity_patterns.extend(custom_ignore_entity_regex)

    # ignore_paths: absolute paths are used as-is; relative paths are expanded per repo root.
    for p_str in custom_ignore_paths:
        p = Path(p_str)
        if p.is_absolute():
            ignore_paths.append(p)
        else:
            ignore_paths.extend(root / p for root in repo_roots)

    ignore_dirs = _unique_preserve_order(ignore_dirs)
    ignore_entity_patterns = _unique_preserve_order(ignore_entity_patterns)
    ignore_paths_str = _unique_preserve_order(str(p) for p in ignore_paths)
    ignore_paths = [Path(p) for p in ignore_paths_str]

    if not ignore_dirs and not ignore_entity_patterns and not ignore_paths:
        return None
    return DefaultFilter(
        ignore_dirs=ignore_dirs,
        ignore_entity_patterns=ignore_entity_patterns,
        ignore_paths=ignore_paths,
    )


def _git_available() -> bool:
    return shutil.which("git") is not None


def _git_is_worktree(root: Path) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def _git_check_ignore(root: Path, rel_paths: Sequence[str], *, timeout_s: float) -> set[str]:
    """Return the subset of rel_paths ignored by gitignore rules.

    Uses `git check-ignore --stdin -z` for batching.
    """

    if not rel_paths:
        return set()
    # Use NUL-separated input and output for unambiguous parsing.
    inp = "\0".join(rel_paths) + "\0"
    proc = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--stdin", "-z"],
        input=inp,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_s,
    )
    if proc.returncode not in (0, 1):
        # 1 means "no matches".
        raise RuntimeError(proc.stderr.strip() or f"git check-ignore failed (code {proc.returncode})")
    if not proc.stdout:
        return set()
    out = proc.stdout.split("\0")
    # git ends with a trailing NUL, so last item is usually empty.
    # Normalize: git may return paths with a trailing slash when a directory pattern matches
    # (e.g. `.pytype/`). We compare using a slash-stripped form.
    return {p.rstrip("/") for p in out if p}


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="watch_repo",
        description="Watch a repository directory and print file change events.",
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
        help="Disable gitignore filtering (by default enabled when git is available).",
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
    parser.set_defaults(force_polling=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    repo_roots: list[Path] = []
    for raw_root in args.paths_to_repo:
        root = raw_root.expanduser().resolve()
        if not root.exists():
            print(f"error: path does not exist: {root}", file=sys.stderr)
            return 2
        if not root.is_dir():
            print(f"error: path is not a directory: {root}", file=sys.stderr)
            return 2
        repo_roots.append(root)

    # Deduplicate roots while preserving order.
    seen_roots: set[Path] = set()
    unique_roots: list[Path] = []
    for r in repo_roots:
        if r in seen_roots:
            continue
        seen_roots.add(r)
        unique_roots.append(r)
    repo_roots = unique_roots

    # Human-friendly labels for output; disambiguate duplicates.
    base_names: list[str] = [r.name or str(r) for r in repo_roots]
    counts: dict[str, int] = {}
    for n in base_names:
        counts[n] = counts.get(n, 0) + 1
    used: dict[str, int] = {}
    repo_labels: dict[Path, str] = {}
    for r, n in zip(repo_roots, base_names, strict=True):
        if counts[n] == 1:
            repo_labels[r] = n
        else:
            used[n] = used.get(n, 0) + 1
            repo_labels[r] = f"{n}#{used[n]}"

    use_defaults_filter = not args.no_defaults_filter
    watch_filter = _build_watchfiles_filter(
        use_defaults_filter=use_defaults_filter,
        repo_roots=repo_roots,
        ignore_dirs_csv=args.ignore_dirs,
        ignore_entity_globs_csv=args.ignore_entity_globs,
        ignore_entity_regex_csv=args.ignore_entity_regex,
        ignore_paths_csv=args.ignore_paths,
    )
    recursive = not args.non_recursive

    use_gitignore_filter = not args.no_gitignore_filter
    gitignore_available = _git_available()
    gitignore_roots_ok: dict[Path, bool] = {}
    if use_gitignore_filter and gitignore_available:
        for r in repo_roots:
            gitignore_roots_ok[r] = _git_is_worktree(r)
    else:
        for r in repo_roots:
            gitignore_roots_ok[r] = False

    # Nested root warnings.
    nested_pairs: list[tuple[Path, Path]] = []
    for i, a in enumerate(repo_roots):
        for b in repo_roots[i + 1 :]:
            if b.is_relative_to(a):
                nested_pairs.append((a, b))
            elif a.is_relative_to(b):
                nested_pairs.append((b, a))

    defaults_label = "on" if use_defaults_filter else "off"
    gitignore_label = "on" if use_gitignore_filter else "off"
    print(
        "Watching: "
        f"{', '.join(str(r) for r in repo_roots)} "
        f"(recursive={recursive}, defaults_filter={defaults_label}, gitignore_filter={gitignore_label}, "
        f"debounce_ms={args.debounce_ms}, step_ms={args.step_ms})",
        flush=True,
    )
    print("Press Ctrl+C to stop.", flush=True)

    if nested_pairs:
        print("Warning: nested watched roots detected:", flush=True)
        for outer, inner in nested_pairs:
            print(f"- {outer} contains {inner}", flush=True)
        print(
            "Attribution: when multiple roots match an event path, the deepest/longest root is used.",
            flush=True,
        )

    if use_gitignore_filter:
        if not gitignore_available:
            print("Gitignore filter: enabled, but git not found on PATH (no-op).", flush=True)
        else:
            for r in repo_roots:
                status = "ok" if gitignore_roots_ok[r] else "unavailable (not a git worktree)"
                print(f"Gitignore filter: {repo_labels[r]} -> {status}", flush=True)

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

    try:
        for changes in watch(
            *(str(r) for r in repo_roots),
            watch_filter=watch_filter,
            debounce=args.debounce_ms,
            step=args.step_ms,
            recursive=recursive,
            force_polling=args.force_polling,
            ignore_permission_denied=args.ignore_permission_denied,
        ):
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            raw_n = len(changes)

            def _classify_path(raw_path: str) -> tuple[Path | None, str, str]:
                p = Path(raw_path).resolve(strict=False)
                best_root: Path | None = None
                for root in repo_roots:
                    if p.is_relative_to(root):
                        if best_root is None or len(root.parts) > len(best_root.parts):
                            best_root = root

                if best_root is None:
                    return None, "?", raw_path
                label = repo_labels[best_root]
                try:
                    rel = str(p.relative_to(best_root))
                except ValueError:
                    rel = raw_path
                return best_root, label, rel

            classified: list[tuple[Change, str, Path | None, str, str]] = []
            for change, raw_path in changes:
                root, repo_label, rel_path = _classify_path(raw_path)
                classified.append((change, raw_path, root, repo_label, rel_path))

            filtered = classified
            if use_gitignore_filter and gitignore_available:
                # Group paths by root and filter using gitignore rules.
                root_to_paths: dict[Path, list[str]] = {}
                for chg, raw_path, root, _repo_label, rel_path in classified:
                    if root is None or not gitignore_roots_ok.get(root, False):
                        continue
                    # git expects '/' separators.
                    rel_git = rel_path.replace("\\", "/")
                    root_to_paths.setdefault(root, []).append(rel_git)
                    # Directory-only ignore patterns (e.g. `.pytype/`) may not match deleted paths
                    # unless we query with a trailing slash.
                    if chg == Change.deleted or Path(raw_path).is_dir():
                        if not rel_git.endswith("/"):
                            root_to_paths[root].append(rel_git + "/")

                ignored_by_root: dict[Path, set[str]] = {}
                for root, rel_paths in root_to_paths.items():
                    ignored: set[str] = set()
                    chunk_size = 4000
                    for i in range(0, len(rel_paths), chunk_size):
                        chunk = rel_paths[i : i + chunk_size]
                        try:
                            ignored.update(_git_check_ignore(root, chunk, timeout_s=10.0))
                        except (subprocess.TimeoutExpired, RuntimeError) as e:
                            print(
                                f"{ts}  warning: gitignore filtering failed for {root}: {e} (fail-open)",
                                flush=True,
                            )
                            ignored = set()
                            break
                    ignored_by_root[root] = ignored

                if ignored_by_root:
                    filtered = [
                        item
                        for item in classified
                        if item[2] is None
                        or not ignored_by_root.get(item[2], set()).__contains__(
                            item[4].replace("\\", "/").rstrip("/")
                        )
                    ]

            filtered_n = len(filtered)
            print(f"{ts}  --- batch: raw={raw_n} filtered={filtered_n} ---", flush=True)

            def sort_key(item: tuple[Change, str, Path | None, str, str]) -> tuple[str, int]:
                change, _raw_path, _root, repo_label, rel = item
                return f"{repo_label}/{rel}", int(change)

            for change, _raw_path, _root, repo_label, rel_path in sorted(filtered, key=sort_key):
                label = _CHANGE_LABELS.get(change, str(change))
                print(f"{ts}  {label:<8}  [{repo_label}] {rel_path}", flush=True)

    except KeyboardInterrupt:
        print("Stopped.", flush=True)
        return 0

    # Normally unreachable unless `watch()` stops iteration.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
