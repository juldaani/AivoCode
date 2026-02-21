"""Watchfiles filter construction.

We rely on `watchfiles.DefaultFilter` for low-level filtering. This is executed
close to the watcher backend and reduces event volume before Python sees it.

We support:
- defaults_filter: use watchfiles' built-in defaults
- custom excludes: additional ignore dirs/patterns/paths

No user-provided callables are supported here.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, Sequence

from watchfiles import DefaultFilter


def _unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _glob_to_regex(glob_pat: str) -> str:
    # fnmatch.translate returns a regex that matches the whole string and ends with \Z.
    return fnmatch.translate(glob_pat)


def build_watchfiles_filter(
    *,
    use_defaults_filter: bool,
    repo_roots: Sequence[Path],
    ignore_dirs: Sequence[str],
    ignore_entity_globs: Sequence[str],
    ignore_entity_regex: Sequence[str],
    ignore_paths: Sequence[str],
) -> DefaultFilter | None:
    """Construct the watchfiles filter or return None.

    If use_defaults_filter is True, the resulting filter is the union of watchfiles
    defaults and custom excludes.

    If use_defaults_filter is False, only custom excludes are applied. If there are
    no custom excludes, returns None to disable watchfiles-level filtering.
    """

    custom_ignore_dirs = list(ignore_dirs)
    custom_ignore_entity_globs = list(ignore_entity_globs)
    custom_ignore_entity_regex = list(ignore_entity_regex)
    custom_ignore_paths = list(ignore_paths)

    has_custom = bool(
        custom_ignore_dirs
        or custom_ignore_entity_globs
        or custom_ignore_entity_regex
        or custom_ignore_paths
    )

    if not use_defaults_filter and not has_custom:
        return None

    if use_defaults_filter and not has_custom:
        return DefaultFilter()

    ignore_dirs_out: list[str] = []
    ignore_entity_patterns_out: list[str] = []
    ignore_paths_out: list[Path] = []

    if use_defaults_filter:
        ignore_dirs_out.extend(DefaultFilter.ignore_dirs)
        ignore_entity_patterns_out.extend(DefaultFilter.ignore_entity_patterns)

    ignore_dirs_out.extend(custom_ignore_dirs)
    ignore_entity_patterns_out.extend(_glob_to_regex(g) for g in custom_ignore_entity_globs)
    ignore_entity_patterns_out.extend(custom_ignore_entity_regex)

    # ignore_paths: absolute paths are used as-is; relative paths are expanded per repo root.
    for p_str in custom_ignore_paths:
        p = Path(p_str)
        if p.is_absolute():
            ignore_paths_out.append(p)
        else:
            ignore_paths_out.extend(root / p for root in repo_roots)

    ignore_dirs_out = _unique_preserve_order(ignore_dirs_out)
    ignore_entity_patterns_out = _unique_preserve_order(ignore_entity_patterns_out)
    ignore_paths_str = _unique_preserve_order(str(p) for p in ignore_paths_out)
    ignore_paths_out = [Path(p) for p in ignore_paths_str]

    if use_defaults_filter:
        return DefaultFilter(
            ignore_dirs=ignore_dirs_out,
            ignore_entity_patterns=ignore_entity_patterns_out,
            ignore_paths=ignore_paths_out,
        )

    # When defaults are disabled, we must override all three components to ensure
    # we don't accidentally keep any watchfiles defaults.
    return DefaultFilter(
        ignore_dirs=ignore_dirs_out,
        ignore_entity_patterns=ignore_entity_patterns_out,
        ignore_paths=ignore_paths_out,
    )
