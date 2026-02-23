"""Integration tests for file_watcher.

What this file tests
- Full watcher pipeline with real filesystem events.
- Uses sync watch_repos API with short debounce for faster tests.
- Uses daemon threads; watcher is forcefully terminated when test ends.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from watchfiles import Change

from file_watcher.types import WatchBatch, WatchConfig
from file_watcher.watcher import watch_repos


DEBOUNCE_MS = 200
INIT_WAIT_S = 0.3
EVENT_WAIT_S = 0.4


def _run_watcher(
    roots: list[Path], cfg: WatchConfig, batches: list[WatchBatch], stop_event: threading.Event
) -> None:
    """Run watcher in a loop, collecting batches until stop_event is set."""
    for batch in watch_repos(roots, cfg):
        batches.append(batch)
        if stop_event.is_set():
            break


class TestWatchIntegration:
    """Integration tests for watch_repos using real filesystem events."""

    def test_watch_single_file_change(self, tmp_path: Path) -> None:
        """Modify a file and verify MODIFIED event is captured."""
        cfg = WatchConfig(debounce_ms=DEBOUNCE_MS, gitignore_filter=False)
        batches: list[WatchBatch] = []
        stop_event = threading.Event()

        test_file = tmp_path / "existing.txt"
        test_file.write_text("initial")

        thread = threading.Thread(
            target=_run_watcher, args=([tmp_path], cfg, batches, stop_event), daemon=True
        )
        thread.start()

        time.sleep(INIT_WAIT_S)
        test_file.write_text("modified")
        time.sleep(EVENT_WAIT_S)

        stop_event.set()
        (tmp_path / "_trigger_stop.txt").write_text("trigger")
        thread.join(timeout=1.0)

        assert len(batches) >= 1
        all_events = [e for b in batches for e in b.events]
        assert any(e.change == Change.modified and e.rel_path == "existing.txt" for e in all_events)

    def test_watch_file_added(self, tmp_path: Path) -> None:
        """Create a new file and verify ADDED event is captured."""
        cfg = WatchConfig(debounce_ms=DEBOUNCE_MS, gitignore_filter=False)
        batches: list[WatchBatch] = []
        stop_event = threading.Event()

        thread = threading.Thread(
            target=_run_watcher, args=([tmp_path], cfg, batches, stop_event), daemon=True
        )
        thread.start()

        time.sleep(INIT_WAIT_S)
        (tmp_path / "new_file.py").write_text("test")
        time.sleep(EVENT_WAIT_S)

        stop_event.set()
        (tmp_path / "_trigger_stop.txt").write_text("trigger")
        thread.join(timeout=1.0)

        assert len(batches) >= 1
        all_events = [e for b in batches for e in b.events]
        assert any(e.change == Change.added and e.rel_path == "new_file.py" for e in all_events)

    def test_watch_file_deleted(self, tmp_path: Path) -> None:
        """Delete a file and verify DELETED event is captured."""
        cfg = WatchConfig(debounce_ms=DEBOUNCE_MS, gitignore_filter=False)
        batches: list[WatchBatch] = []
        stop_event = threading.Event()

        test_file = tmp_path / "to_delete.txt"
        test_file.write_text("will be deleted")

        thread = threading.Thread(
            target=_run_watcher, args=([tmp_path], cfg, batches, stop_event), daemon=True
        )
        thread.start()

        time.sleep(INIT_WAIT_S)
        test_file.unlink()
        time.sleep(EVENT_WAIT_S)

        stop_event.set()
        (tmp_path / "_trigger_stop.txt").write_text("trigger")
        thread.join(timeout=1.0)

        assert len(batches) >= 1
        all_events = [e for b in batches for e in b.events]
        assert any(e.change == Change.deleted and e.rel_path == "to_delete.txt" for e in all_events)

    def test_watch_gitignore_filtering(self, mock_python_repo: Path) -> None:
        """Ignored files (via .gitignore) are filtered from events."""
        cfg = WatchConfig(debounce_ms=DEBOUNCE_MS, gitignore_filter=True)
        batches: list[WatchBatch] = []
        stop_event = threading.Event()

        gitignore_path = mock_python_repo / ".gitignore"
        py_file = mock_python_repo / "tracked.py"
        log_file = mock_python_repo / "ignored.log"

        try:
            gitignore_path.write_text("*.log\n")

            thread = threading.Thread(
                target=_run_watcher, args=([mock_python_repo], cfg, batches, stop_event), daemon=True
            )
            thread.start()

            time.sleep(INIT_WAIT_S)
            py_file.write_text("# python")
            log_file.write_text("log content")
            time.sleep(EVENT_WAIT_S)

            stop_event.set()
            (mock_python_repo / "_trigger_stop.txt").write_text("trigger")
            thread.join(timeout=1.0)

            all_events = [e for b in batches for e in b.events]
            rel_paths = [e.rel_path for e in all_events]

            assert "tracked.py" in rel_paths
            assert "ignored.log" not in rel_paths
        finally:
            gitignore_path.unlink(missing_ok=True)
            py_file.unlink(missing_ok=True)
            log_file.unlink(missing_ok=True)
            (mock_python_repo / "_trigger_stop.txt").unlink(missing_ok=True)

    def test_watch_multiple_roots(self, tmp_path: Path) -> None:
        """Watching two separate roots reports events with correct labels."""
        dir1 = tmp_path / "repo_alpha"
        dir2 = tmp_path / "repo_beta"
        dir1.mkdir()
        dir2.mkdir()

        cfg = WatchConfig(debounce_ms=DEBOUNCE_MS, gitignore_filter=False)
        batches: list[WatchBatch] = []
        stop_event = threading.Event()

        thread = threading.Thread(
            target=_run_watcher, args=([dir1, dir2], cfg, batches, stop_event), daemon=True
        )
        thread.start()

        time.sleep(INIT_WAIT_S)
        (dir1 / "alpha.txt").write_text("a")
        (dir2 / "beta.txt").write_text("b")
        time.sleep(EVENT_WAIT_S)

        stop_event.set()
        (dir1 / "_trigger_stop.txt").write_text("trigger")
        thread.join(timeout=1.0)

        assert len(batches) >= 1
        all_events = [e for b in batches for e in b.events]

        labels_found = {e.repo_label for e in all_events}
        assert "repo_alpha" in labels_found
        assert "repo_beta" in labels_found

    def test_watch_nested_roots(self, tmp_path: Path) -> None:
        """Events in nested roots are attributed to the deepest matching root."""
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)

        cfg = WatchConfig(debounce_ms=DEBOUNCE_MS, gitignore_filter=False)
        batches: list[WatchBatch] = []
        stop_event = threading.Event()

        thread = threading.Thread(
            target=_run_watcher, args=([parent, child], cfg, batches, stop_event), daemon=True
        )
        thread.start()

        time.sleep(INIT_WAIT_S)
        (child / "nested_file.txt").write_text("nested")
        time.sleep(EVENT_WAIT_S)

        stop_event.set()
        (parent / "_trigger_stop.txt").write_text("trigger")
        thread.join(timeout=1.0)

        assert len(batches) >= 1
        all_events = [e for b in batches for e in b.events]

        child_events = [e for e in all_events if e.rel_path == "nested_file.txt"]
        assert len(child_events) >= 1
        assert child_events[0].repo_root == child

    def test_watch_coalesce_replacement(self, tmp_path: Path) -> None:
        """Rapid delete+create of same path results in MODIFIED (file exists)."""
        cfg = WatchConfig(debounce_ms=DEBOUNCE_MS, gitignore_filter=False, coalesce_events=True)
        batches: list[WatchBatch] = []
        stop_event = threading.Event()

        test_file = tmp_path / "replace_me.txt"
        test_file.write_text("original")

        thread = threading.Thread(
            target=_run_watcher, args=([tmp_path], cfg, batches, stop_event), daemon=True
        )
        thread.start()

        time.sleep(INIT_WAIT_S)
        test_file.unlink()
        test_file.write_text("replacement")
        time.sleep(EVENT_WAIT_S)

        stop_event.set()
        (tmp_path / "_trigger_stop.txt").write_text("trigger")
        thread.join(timeout=1.0)

        assert len(batches) >= 1
        all_events = [e for b in batches for e in b.events if e.rel_path == "replace_me.txt"]

        assert len(all_events) == 1
        assert all_events[0].change == Change.modified

        test_file.unlink(missing_ok=True)
        (tmp_path / "_trigger_stop.txt").unlink(missing_ok=True)