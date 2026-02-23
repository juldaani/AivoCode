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
import re
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


def build_watchfiles_filter(
    *,
    use_defaults_filter: bool,
    repo_custom_ignores: dict[Path, Sequence[str]],
) -> DefaultFilter | None:
    """Construct the watchfiles filter or return None.

    If use_defaults_filter is True, the resulting filter is the union of watchfiles
    defaults and custom ignores per repository.

    If use_defaults_filter is False, only custom excludes are applied. If there are
    no custom excludes, returns None to disable watchfiles-level filtering.
    """

    has_custom = bool(repo_custom_ignores)

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

    for root, ignores in repo_custom_ignores.items():
        for ign in ignores:
            if "*" in ign or "?" in ign:
                # Provide a glob translation bound to the repo root.
                # Since watchfiles applies regex globally, we prefix the regex with the repo root path.
                pat = fnmatch.translate(ign)
                # fnmatch in Python 3.11 outputs `(?s:...)`. We inject the repo root prefix inside it.
                if pat.startswith("(?s:"):
                    repo_pat = f"(?s:^{re.escape(str(root) + '/')}{pat[4:]}"
                else:
                    repo_pat = f"^{re.escape(str(root) + '/')}{pat}"
                ignore_entity_patterns_out.append(repo_pat)
            else:
                p = Path(ign)
                if p.is_absolute():
                    ignore_paths_out.append(p)
                else:
                    ignore_paths_out.append(root / p)

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
