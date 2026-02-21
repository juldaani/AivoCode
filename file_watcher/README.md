# File Watcher

Standalone CLI demo and importable API to watch one or more repo folders and
print file change events.

## Requirements

- Python 3.9+
- `watchfiles`

In this repo, `watchfiles` is already included in the conda environment `env-aivocode`.

## CLI Demo

Run the standalone demo with the repo's conda environment:

```bash
conda run -n env-aivocode python -m file_watcher.how_to_use /path/to/repo
```

Watch multiple repos/paths (single merged stream of events):

```bash
conda run -n env-aivocode python -m file_watcher.how_to_use /path/to/repo-a /path/to/repo-b
```

Disable gitignore filtering (keep watchfiles defaults/custom ignores):

```bash
conda run -n env-aivocode python -m file_watcher.how_to_use /path/to/repo --no-gitignore-filter
```

Disable watchfiles default filtering (includes `.git/` and other noisy directories):

```bash
conda run -n env-aivocode python -m file_watcher.how_to_use /path/to/repo --no-defaults-filter
```

Add custom excludes (merged into watchfiles filtering):

```bash
conda run -n env-aivocode python -m file_watcher.how_to_use /path/to/repo \
  --ignore-dirs "dist,build" \
  --ignore-entity-globs "*.log,.goutputstream-*" \
  --ignore-paths "tmp/generated.txt"
```

Faster feedback (smaller debounce window):

```bash
conda run -n env-aivocode python -m file_watcher.how_to_use . --debounce-ms 200 --step-ms 25
```

## Notes

- Output is batched: the watcher yields a set of changes after a debounce window.
- Renames/replacements may appear as `DELETED` + `ADDED` at the filesystem level.
  The library coalesces same-path events within a batch to a more human-friendly
  final label (e.g. ADDED+DELETED becomes MODIFIED if the path exists).
- By default two filters are applied:
  - watchfiles defaults (`watchfiles.DefaultFilter`)
  - gitignore filtering via `git check-ignore` (enabled when `git` is available and the root is a git worktree)
- Batch header uses two counts:
  - `raw`: events yielded by watchfiles (after watchfiles filtering, if enabled)
  - `filtered`: events remaining after gitignore filtering

## Importable API

For production code, prefer the async API (won't block the event loop):

```python
from pathlib import Path

from file_watcher import WatchConfig, awatch_repos


async def main() -> None:
    cfg = WatchConfig(
        defaults_filter=True,
        gitignore_filter=True,
        coalesce_events=True,
        step_ms=200,
    )
    async for batch in awatch_repos([Path("/path/to/repo")], cfg):
        for ev in batch.events:
            print(ev.change, ev.repo_label, ev.rel_path)
```

Nested roots are supported. When multiple roots match an event path, the watcher
attributes the event to the deepest/longest matching root.

## Files

- `how_to_use.py` - Standalone CLI demo; shows how to configure and use the watcher.
- `watcher.py` - Core async/sync APIs (`awatch_repos`, `watch_repos`).
- `types.py` - Data types (`WatchConfig`, `WatchBatch`, `WatchEvent`).
- `filters.py` - Builds watchfiles `DefaultFilter` from configuration.
- `gitignore.py` - Gitignore filtering via `git check-ignore`.
