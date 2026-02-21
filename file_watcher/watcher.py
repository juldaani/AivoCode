"""Importable repository file watcher.

This module provides both sync and async APIs.

Key behaviors
- Uses watchfiles to watch one or more roots.
- Classifies each raw path to the deepest matching root (nested roots supported).
- Optionally filters yielded batches using gitignore via `git check-ignore`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import subprocess
from typing import DefaultDict
from typing import AsyncIterator, Iterator, Sequence

from watchfiles import Change, DefaultFilter, awatch, watch

from file_watcher.filters import build_watchfiles_filter
from file_watcher.gitignore import GitignoreStatus, build_gitignore_status, git_check_ignore
from file_watcher.types import RootInfo, WatchBatch, WatchConfig, WatchEvent


def _normalize_roots(roots: Sequence[Path]) -> RootInfo:
    resolved: list[Path] = []
    for r in roots:
        rr = r.expanduser().resolve()
        if not rr.exists() or not rr.is_dir():
            raise ValueError(f"Invalid root (must exist and be a directory): {rr}")
        resolved.append(rr)

    # Deduplicate preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for r in resolved:
        if r in seen:
            continue
        seen.add(r)
        unique.append(r)

    roots_out: Sequence[Path] = unique

    # Labels: basename, disambiguated with #n if needed.
    base_names = [r.name or str(r) for r in roots_out]
    counts: dict[str, int] = {}
    for n in base_names:
        counts[n] = counts.get(n, 0) + 1
    used: dict[str, int] = {}
    labels: dict[Path, str] = {}
    for r, n in zip(roots_out, base_names, strict=True):
        if counts[n] == 1:
            labels[r] = n
        else:
            used[n] = used.get(n, 0) + 1
            labels[r] = f"{n}#{used[n]}"

    nested_pairs: list[tuple[Path, Path]] = []
    for i, a in enumerate(roots_out):
        for b in roots_out[i + 1 :]:
            if b.is_relative_to(a):
                nested_pairs.append((a, b))
            elif a.is_relative_to(b):
                nested_pairs.append((b, a))

    return RootInfo(roots=roots_out, labels=labels, nested_pairs=nested_pairs)


def _classify_path(raw_path: str, *, roots: Sequence[Path], labels: dict[Path, str]) -> WatchEvent:
    p = Path(raw_path).resolve(strict=False)
    best_root: Path | None = None
    for root in roots:
        if p.is_relative_to(root):
            if best_root is None or len(root.parts) > len(best_root.parts):
                best_root = root

    if best_root is None:
        return WatchEvent(change=Change.modified, abs_path=p, repo_root=None, repo_label="?", rel_path=raw_path)

    label = labels[best_root]
    try:
        rel = str(p.relative_to(best_root))
    except ValueError:
        rel = raw_path
    return WatchEvent(change=Change.modified, abs_path=p, repo_root=best_root, repo_label=label, rel_path=rel)


def _event_for(change: Change, raw_path: str, *, roots: Sequence[Path], labels: dict[Path, str]) -> WatchEvent:
    classified = _classify_path(raw_path, roots=roots, labels=labels)
    return replace(classified, change=change)


def _apply_gitignore_filter(
    events: Sequence[WatchEvent],
    *,
    status: GitignoreStatus,
    cfg: WatchConfig,
) -> tuple[Sequence[WatchEvent], Sequence[str]]:
    if not status.enabled or not status.git_available:
        return events, ()

    # Group by root.
    root_to_paths: dict[Path, list[str]] = defaultdict(list)
    for ev in events:
        if ev.repo_root is None or not status.root_ok.get(ev.repo_root, False):
            continue
        rel_git = ev.rel_path.replace("\\", "/")
        root_to_paths[ev.repo_root].append(rel_git)
        # Directory-only ignore patterns (e.g. `.pytype/`) may not match deleted paths unless
        # we also query with a trailing slash.
        if ev.change == Change.deleted or ev.abs_path.is_dir():
            if not rel_git.endswith("/"):
                root_to_paths[ev.repo_root].append(rel_git + "/")

    ignored_by_root: dict[Path, set[str]] = {}
    warnings: list[str] = []
    for root, rel_paths in root_to_paths.items():
        ignored: set[str] = set()
        try:
            for i in range(0, len(rel_paths), cfg.git_chunk_size):
                chunk = rel_paths[i : i + cfg.git_chunk_size]
                ignored.update(git_check_ignore(root, chunk, timeout_s=cfg.git_timeout_s))
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            warnings.append(f"gitignore filtering failed for {root}: {e} (fail-open)")
            ignored = set()
        ignored_by_root[root] = ignored

    if not ignored_by_root:
        return events, tuple(warnings)

    out: list[WatchEvent] = []
    for ev in events:
        if ev.repo_root is None:
            out.append(ev)
            continue
        ignored_set = ignored_by_root.get(ev.repo_root)
        if not ignored_set:
            out.append(ev)
            continue
        key = ev.rel_path.replace("\\", "/").rstrip("/")
        if key not in ignored_set:
            out.append(ev)
    return out, tuple(warnings)


def _coalesce_events(events: Sequence[WatchEvent]) -> Sequence[WatchEvent]:
    """Coalesce multiple events for the same path within a batch.

    Some tools (e.g. git restore/checkout, some editors) replace files using an
    atomic write/rename pattern which can show up as ADDED+DELETED for the same
    path in a single batch. This is confusing to read as "deleted" even when the
    file exists after the operation.

    This function reduces per-path noise and chooses a "final" change:
    - If ADDED and DELETED both occurred:
      - If the path exists now: MODIFIED
      - Otherwise: DELETED
    - If only ADDED occurred (or ADDED+MODIFIED): ADDED
    - If DELETED occurred without ADDED: DELETED
    - Otherwise: MODIFIED
    """

    # Key by repo_root + rel_path (preferred); fall back to abs_path for unknown roots.
    seen_order: list[tuple[Path | None, str, Path]] = []
    flags: DefaultDict[tuple[Path | None, str, Path], set[Change]] = defaultdict(set)
    last_event: dict[tuple[Path | None, str, Path], WatchEvent] = {}

    for ev in events:
        key = (ev.repo_root, ev.rel_path, ev.abs_path)
        if key not in last_event:
            seen_order.append(key)
        flags[key].add(ev.change)
        last_event[key] = ev

    out: list[WatchEvent] = []
    for key in seen_order:
        ev = last_event[key]
        f = flags[key]

        has_added = Change.added in f
        has_deleted = Change.deleted in f
        has_modified = Change.modified in f

        final_change: Change
        if has_deleted and not has_added:
            final_change = Change.deleted
        elif has_added and not has_deleted:
            final_change = Change.added
        elif has_added and has_deleted:
            # Replacement or create+remove. Decide based on current existence.
            final_change = Change.modified if ev.abs_path.exists() else Change.deleted
        elif has_modified:
            final_change = Change.modified
        else:
            final_change = ev.change

        out.append(replace(ev, change=final_change))

    return out


def build_startup_info(roots: Sequence[Path], cfg: WatchConfig) -> tuple[RootInfo, DefaultFilter | None, GitignoreStatus]:
    root_info = _normalize_roots(roots)
    watch_filter = build_watchfiles_filter(
        use_defaults_filter=cfg.defaults_filter,
        repo_roots=root_info.roots,
        ignore_dirs=cfg.ignore_dirs,
        ignore_entity_globs=cfg.ignore_entity_globs,
        ignore_entity_regex=cfg.ignore_entity_regex,
        ignore_paths=cfg.ignore_paths,
    )
    git_status = build_gitignore_status(roots=root_info.roots, enabled=cfg.gitignore_filter)
    return root_info, watch_filter, git_status


def watch_repos(roots: Sequence[Path], cfg: WatchConfig) -> Iterator[WatchBatch]:
    root_info, watch_filter, git_status = build_startup_info(roots, cfg)

    for changes in watch(
        *(str(r) for r in root_info.roots),
        watch_filter=watch_filter,
        debounce=cfg.debounce_ms,
        step=cfg.step_ms,
        recursive=cfg.recursive,
        force_polling=cfg.force_polling,
        ignore_permission_denied=cfg.ignore_permission_denied,
    ):
        ts = datetime.now()
        raw_n = len(changes)
        events = [_event_for(change, raw_path, roots=root_info.roots, labels=root_info.labels) for change, raw_path in changes]
        filtered_events, warnings = _apply_gitignore_filter(events, status=git_status, cfg=cfg)
        final_events = _coalesce_events(filtered_events) if cfg.coalesce_events else filtered_events
        yield WatchBatch(
            ts=ts,
            raw=raw_n,
            filtered=len(final_events),
            events=tuple(final_events),
            warnings=warnings,
        )


async def awatch_repos(roots: Sequence[Path], cfg: WatchConfig) -> AsyncIterator[WatchBatch]:
    root_info, watch_filter, git_status = build_startup_info(roots, cfg)

    async for changes in awatch(
        *(str(r) for r in root_info.roots),
        watch_filter=watch_filter,
        debounce=cfg.debounce_ms,
        step=cfg.step_ms,
        recursive=cfg.recursive,
        force_polling=cfg.force_polling,
        ignore_permission_denied=cfg.ignore_permission_denied,
    ):
        ts = datetime.now()
        raw_n = len(changes)
        events = [_event_for(change, raw_path, roots=root_info.roots, labels=root_info.labels) for change, raw_path in changes]
        filtered_events, warnings = _apply_gitignore_filter(events, status=git_status, cfg=cfg)
        final_events = _coalesce_events(filtered_events) if cfg.coalesce_events else filtered_events
        yield WatchBatch(
            ts=ts,
            raw=raw_n,
            filtered=len(final_events),
            events=tuple(final_events),
            warnings=warnings,
        )
