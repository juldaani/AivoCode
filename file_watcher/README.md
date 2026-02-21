# File Watcher Prototype (ver0.1)

Standalone script to watch a repository folder and print file change events.

## Requirements

- Python 3.9+
- `watchfiles`

In this repo, `watchfiles` is already included in the conda environment `env-aivocode`.

## Usage

Run with the repo's conda environment:

```bash
conda run -n env-aivocode python -m file_watcher.watch_repo /path/to/repo
```

Watch multiple repos/paths (single merged stream of events):

```bash
conda run -n env-aivocode python -m file_watcher.watch_repo /path/to/repo-a /path/to/repo-b
```

Disable gitignore filtering (keep watchfiles defaults/custom ignores):

```bash
conda run -n env-aivocode python -m file_watcher.watch_repo /path/to/repo --no-gitignore-filter
```

Disable watchfiles default filtering (includes `.git/` and other noisy directories):

```bash
conda run -n env-aivocode python -m file_watcher.watch_repo /path/to/repo --no-defaults-filter
```

Add custom excludes (merged into watchfiles filtering):

```bash
conda run -n env-aivocode python -m file_watcher.watch_repo /path/to/repo \
  --ignore-dirs "dist,build" \
  --ignore-entity-globs "*.log,.goutputstream-*" \
  --ignore-paths "tmp/generated.txt"
```

Faster feedback (smaller debounce window):

```bash
conda run -n env-aivocode python -m file_watcher.watch_repo . --debounce-ms 200 --step-ms 25
```

## Notes

- Output is batched: the watcher yields a set of changes after a debounce window.
- Renames may appear as `DELETED` + `ADDED` depending on OS backend.
- By default two filters are applied:
  - watchfiles defaults (`watchfiles.DefaultFilter`)
  - gitignore filtering via `git check-ignore` (enabled when `git` is available and the root is a git worktree)
- Batch header uses two counts:
  - `raw`: events yielded by watchfiles (after watchfiles filtering, if enabled)
  - `filtered`: events remaining after gitignore filtering
