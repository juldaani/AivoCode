from __future__ import annotations  # MUST be first statement (PEP 236)

# ══════════════════════════════════════════════════════════════════════════════
# sys.path fix must come BEFORE local (lsp.* / file_watcher) imports.
# When this file is run as `python lsp/_daemon.py`, the script's parent dir
# (lsp/) is added to sys.path[0], but the repo root is not.  The repo root is
# needed so that `lsp` and `file_watcher` resolve as top-level packages.
# ══════════════════════════════════════════════════════════════════════════════
import sys  # noqa: E402 — at module level, before local imports
from pathlib import Path as _Path  # noqa: E402

if __name__ == "__main__":
    _REPO_ROOT = _Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_REPO_ROOT))

# ══════════════════════════════════════════════════════════════════════════════
# Normal module code follows.
# ══════════════════════════════════════════════════════════════════════════════
"""Persistent LSP daemon — lifecycle management + daemon process entry point.

What this module provides (client-side)
- ensure_daemon: start the daemon subprocess if not already running.
- send_query: send a method call to the daemon, return the result dict.
- stop_daemon: gracefully shut down the daemon for a workspace.

What this module provides (server-side, via __main__)
- _run_daemon: the asyncio entry point that runs the socket server + file
  watcher + LspClient concurrently.  Invoked as a standalone subprocess.

Why this exists
- Each ``aivocode lsp`` CLI invocation is short-lived, but the LSP server is
  heavy to start (indexes the entire workspace).  The daemon keeps the LSP
  server alive across invocations, and the file watcher keeps it in sync
  with file-system changes (critical for Docker-mounted volumes where inotify
  doesn't work — we use ``force_polling=True``).

How it works
- Client: `ensure_daemon(workspace)` checks for a Unix socket at
  ``<workspace>/.aivocode/daemons/<sha256>.sock``.  If missing or unresponsive,
  spawns ``sys.executable <path/to/_daemon.py> <workspace> <socket>``.
  Then sends LD‑JSON requests via the socket.
- Daemon: asyncio event loop running four concurrent tasks:
  1. **file watcher**: ``awatch_repos`` with ``force_polling=True``.
     Forwards every batch to ``client.notify_file_changes()``.
  2. **Unix socket server**: accepts connections, reads one line, dispatches
     by method name, writes one response line.
  3. **idle watcher**: periodically checks the time since the last client
     query.  If it exceeds ``_IDLE_TIMEOUT`` (default 600 s), triggers a
     graceful shutdown to free resources.  Controlled by env var
     ``AIVOCODE_DAEMON_IDLE_TIMEOUT``.
  4. **LspClient**: kept alive as async context manager.  Query methods
     (e.g. ``request_document_symbol_list``) are called synchronously within
     the socket handler (the handler is inside the context manager).

See Also
- lsp._protocol: Request / Response types and the wire format.
- lsp._workspace: git workspace detection used by the public API layer.
- file_watcher: awatch_repos and WatchConfig.
"""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path

from lsp._protocol import Request, Response, ping, send_request
from lsp._serialize import (
    _lsp_result_to_json,
    _normalize_positions_to_one_indexed,
    _replace_kind_integers,
    _symbol_tree_to_dict,
)
from lsp.client import LspClient
from lsp.config import LanguageEntry
from lsp_client.utils.types import lsp_type  # for Position(line, character)

# ── Per-workspace runtime directory layout ────────────────────────────────────
# All aivocode runtime files live under <workspace>/.aivocode/ — a dot-directory
# at the workspace root (like .git/).  This keeps daemon sockets and log files
# colocated with the workspace while clearly separating them from source code.
# .aivocode/ is gitignored so runtime artifacts never end up in the repo.

_SOCKET_SUBDIR = "daemons"
_LOG_SUBDIR = "logs"


def _aivocode_dir(workspace: Path, *subdirs: str) -> Path:
    """Return and create ``<workspace>/.aivocode/<subdirs...>``."""
    d = workspace.resolve() / ".aivocode"
    for s in subdirs:
        d = d / s
    d.mkdir(parents=True, exist_ok=True)
    return d


def _socket_path(workspace: Path) -> Path:
    """Compute the canonical Unix socket path for a workspace.

    Uses the first 24 chars of a SHA-256 hex digest — long enough to avoid
    collisions, short enough to stay within Unix socket path limits (108 bytes).
    """
    ws_abs = str(workspace.resolve())
    digest = hashlib.sha256(ws_abs.encode()).hexdigest()[:24]
    return _aivocode_dir(workspace, _SOCKET_SUBDIR) / f"{digest}.sock"


def _log_path(workspace: Path) -> Path:
    """Compute the log file path for a workspace daemon."""
    ws_abs = str(workspace.resolve())
    digest = hashlib.sha256(ws_abs.encode()).hexdigest()[:24]
    return _aivocode_dir(workspace, _LOG_SUBDIR) / f"{digest}.log"


# ── Default language entry (MVP: Python only) ────────────────────────────────
# Language configuration is loaded from AIVOCODE_LSP_CONFIG_PATH or the
# bundled /aivocode/.lsp_config.toml.  _DEFAULT_PYTHON_LANG is the
# hardcoded fallback when no config file is found.

_DEFAULT_PYTHON_LANG = LanguageEntry(
    name="python",
    suffixes=(".py", ".pyi"),
    server="basedpyright-langserver",
    server_args=("--stdio",),
)

logger = logging.getLogger(__name__)


def _load_language_config() -> list[LanguageEntry]:
    """Load language entries from the configured TOML file.

    Resolution order:
    1. ``AIVOCODE_LSP_CONFIG_PATH`` env var (absolute path to a TOML file).
    2. ``/aivocode/.lsp_config.toml`` (bundled default in the production image).
    3. Hardcoded ``_DEFAULT_PYTHON_LANG`` fallback.

    Returns a list of ``LanguageEntry`` objects (always non-empty).
    """
    import tomllib

    # 1. Env override
    config_path = os.environ.get("AIVOCODE_LSP_CONFIG_PATH")
    if config_path:
        try:
            data = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
        except (FileNotFoundError, tomllib.TOMLDecodeError, OSError) as exc:
            logger.warning(
                "AIVOCODE_LSP_CONFIG_PATH=%s could not be read: %s — falling back",
                config_path, exc,
            )
            return [_DEFAULT_PYTHON_LANG]

    # 2. Bundled default
    if not config_path:
        bundled = Path("/aivocode/.lsp_config.toml")
        if bundled.exists():
            try:
                data = tomllib.loads(bundled.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as exc:
                logger.warning("Bundled config %s is invalid: %s", bundled, exc)
                return [_DEFAULT_PYTHON_LANG]
        else:
            return [_DEFAULT_PYTHON_LANG]

    # Parse [[language]] entries.
    entries: list[LanguageEntry] = []
    for raw in data.get("language", []):
        if not isinstance(raw, dict):
            continue
        name = raw.get("name", "")
        suffixes = tuple(raw.get("suffixes", []))
        server = raw.get("server", "")
        server_args = tuple(raw.get("server_args", ["--stdio"]))
        if name and suffixes and server:
            entries.append(LanguageEntry(
                name=name, suffixes=suffixes, server=server, server_args=server_args,
            ))

    if not entries:
        logger.warning("No valid [[language]] entries found in config — falling back")
        return [_DEFAULT_PYTHON_LANG]

    return entries

# ── Idle shutdown ─────────────────────────────────────────────────────────────
# After _IDLE_TIMEOUT seconds of no client queries, the daemon shuts itself
# down to free resources.  The next incoming query transparently auto-starts
# a fresh daemon via ensure_daemon().  Set AIVOCODE_DAEMON_IDLE_TIMEOUT env
# var to override (e.g. "15" for testing, "600" for 10‑minute production default).

_IDLE_TIMEOUT = float(os.environ.get("AIVOCODE_DAEMON_IDLE_TIMEOUT", "600"))


# ──────────────────────────────────────────────────────────────────────────────
# Client-side helpers — called by CLI / MCP / REST
# ──────────────────────────────────────────────────────────────────────────────


def _is_running(socket_path: Path) -> bool:
    """Return True if a daemon is listening on *socket_path*."""
    if not socket_path.exists():
        return False
    return ping(socket_path, timeout=2.0)


def ensure_daemon(
    workspace: Path,
    *,
    startup_timeout: float = 60.0,
) -> Path:
    """Ensure a daemon is running for *workspace*, starting one if needed.

    Parameters
    ----------
    workspace : Path
        The git repo root / LSP workspace directory.
    startup_timeout : float
        Maximum seconds to wait for the daemon to become responsive after
        spawning.  Basedpyright can take 5–30 seconds on large repos.

    Returns
    -------
    Path
        Socket path of the running daemon.

    Raises
    ------
    RuntimeError
        If the daemon fails to start within *startup_timeout*.
    """
    socket_path = _socket_path(workspace)

    if _is_running(socket_path):
        # ── Freshness check: is the daemon running stale code? ─────────
        # Compare the socket's mtime (daemon start time) against the
        # newest .py source file in the aivocode packages.  If any source
        # file changed after the daemon started, the daemon is running
        # old code — kill it, clean up, and spawn a fresh one.
        try:
            repo_root = Path(__file__).resolve().parent.parent  # workspace root
            src_mtime = max(
                p.stat().st_mtime
                for pkg in ("lsp", "codebase", "api_server", "cli")
                for p in (repo_root / pkg).rglob("*.py")
            )
            if socket_path.stat().st_mtime < src_mtime:
                logger.info(
                    "Daemon source newer than running daemon (%s < %s) — restarting",
                    socket_path.stat().st_mtime,
                    src_mtime,
                )
                stop_daemon(workspace)  # full kill + socket cleanup
                # Fall through to spawn a fresh daemon below.
            else:
                return socket_path  # daemon is fresh — reuse it
        except OSError:
            # mtime check failed (e.g. a .py file was deleted mid-glob) —
            # conservative: kill and restart to be safe.
            logger.warning(
                "mtime freshness check failed — restarting daemon"
            )
            try:
                stop_daemon(workspace)
            except Exception:
                pass
            # Fall through to spawn a fresh daemon below.

    # ── Daemon not running (or killed above) — spawn it ────────────────
    socket_path.unlink(missing_ok=True)

    daemon_script = Path(__file__)  # lsp/_daemon.py — we ARE the daemon script.
    log_file = _log_path(workspace)

    with open(log_file, "a") as log_fp:
        log_fp.write(
            f"\n─── daemon starting at {time.strftime('%Y-%m-%d %H:%M:%S')} ───\n"
        )
        log_fp.write(f"workspace={workspace}\nsocket={socket_path}\n\n")

    proc = subprocess.Popen(
        [
            sys.executable,
            str(daemon_script),
            str(workspace.resolve()),
            str(socket_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=open(log_file, "a"),
        start_new_session=True,
        env={**os.environ},
    )

    logger.info(
        "Spawned LSP daemon (pid=%d) for workspace %s",
        proc.pid,
        workspace,
    )

    # Wait for the daemon to respond.  Exponential-ish backoff.
    deadline = time.monotonic() + startup_timeout
    delay = 0.1
    while time.monotonic() < deadline:
        if _is_running(socket_path):
            logger.info("Daemon for %s is ready (pid=%d)", workspace, proc.pid)
            return socket_path
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)

    # Timeout — kill the subprocess, raise.
    logger.error("Daemon (pid=%d) failed to start within %gs", proc.pid, startup_timeout)
    try:
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass
    socket_path.unlink(missing_ok=True)
    raise RuntimeError(
        f"LSP daemon failed to start within {startup_timeout}s. "
        f"Check {log_file} for errors."
    )


def send_query(
    workspace: Path,
    method: str,
    params: dict[str, str],
) -> dict:
    """Send a query to the daemon and return the result (or raise on error).

    Parameters
    ----------
    workspace : Path
        Git repo root.
    method : str
        Method to call, e.g. ``"symbols"``, ``"ping"``.
    params : dict[str, str]
        Method parameters.

    Returns
    -------
    dict
        The ``result`` field of the response.

    Raises
    ------
    RuntimeError
        If the daemon returns an error or the request fails.
    """
    socket_path = ensure_daemon(workspace)

    req_id = int(time.monotonic() * 1_000_000) % 2_147_483_648

    resp: Response = send_request(
        socket_path,
        Request(id=req_id, method=method, params=params),
    )

    if resp.error:
        raise RuntimeError(
            f"Daemon error (code={resp.error.get('code', -1)}): "
            f"{resp.error.get('message', 'unknown')}"
        )

    return resp.result if resp.result is not None else {}


def stop_daemon(workspace: Path) -> None:
    """Shut down the daemon for *workspace*, if running.

    Removes **all** daemon socket files in ``<workspace>/.aivocode/daemons/``,
    not just the expected hash — this guarantees no orphan socket from a
    crashed or stale daemon survives to confuse ``ensure_daemon``.

    Parameters
    ----------
    workspace : Path
        Git repo root.
    """
    socket_path = _socket_path(workspace)
    daemons_dir = _aivocode_dir(workspace, _SOCKET_SUBDIR)

    try:
        if not _is_running(socket_path):
            return  # nothing to shut down

        try:
            send_request(
                socket_path,
                Request(id=0, method="shutdown", params={}),
                timeout=3.0,
            )
        except Exception:
            logger.warning(
                "Failed to send shutdown to daemon at %s", socket_path
            )
    finally:
        # ── Always clean up ALL sockets in the daemons directory ────────
        # Unlinking just the expected socket is not enough — a crashed or
        # zombie daemon can leave stray .sock files behind.  Removing every
        # socket in the directory guarantees no stale socket survives,
        # regardless of which code path brought us here.
        time.sleep(0.2)  # give the daemon a moment to flush / exit
        for sock_file in daemons_dir.glob("*.sock"):
            try:
                sock_file.unlink()
                logger.info("Removed stale socket: %s", sock_file)
            except OSError:
                logger.warning("Failed to remove socket: %s", sock_file)


# ──────────────────────────────────────────────────────────────────────────────
# Daemon process entry point
# ──────────────────────────────────────────────────────────────────────────────


async def _run_daemon(
    workspace: Path,
    socket_path: Path,
    lang_entry: LanguageEntry,
) -> None:
    """Main daemon loop — runs until shutdown, idle timeout, or a component crash.

    Crash-fast design: if the file watcher or LSP server fails, the entire
    daemon shuts down.  The next incoming CLI query will auto-start a fresh
    daemon via :func:`ensure_daemon`.  There is no retry — stale state
    (e.g. watcher out of sync with LSP index) is worse than a clean restart.

    Shutdown paths (any of these close the server):
    - **Idle timeout**: no client query for ``_IDLE_TIMEOUT`` seconds
      (default 600 s / 10 min, overridable via ``AIVOCODE_DAEMON_IDLE_TIMEOUT``).
    - **Watcher crash**: ``server.close()`` → ``serve_forever()`` returns → exit.
    - **Client ``"shutdown"``**: ``server.close()`` → exit (graceful).
    - **LspClient crash**: exception in ``async with`` → ``finally`` cleans up.
    """
    socket_path.unlink(missing_ok=True)

    # ── server_ref — mutable closure capture ───────────────────────────
    # The watcher, socket handler, and idle watcher all need to close the
    # server to trigger daemon shutdown.  The server instance doesn't exist
    # yet when these functions are defined, so we capture a mutable cell and
    # assign it after ``start_unix_server``.
    server_ref: asyncio.AbstractServer | None = None

    # ── last_activity — monotonic timestamp for idle shutdown ───────────
    # Updated by _handle_client on every client query.  The idle watcher
    # task periodically checks if (_now - last_activity) > _IDLE_TIMEOUT
    # and calls server_ref.close() if so.  Initialized to "now" so the
    # daemon isn't killed before it even starts listening.
    last_activity: float = time.monotonic()

    async with LspClient(lang_entry=lang_entry, workspace=workspace) as client:
        logger.info(
            "LSP daemon started: workspace=%s, server=%s, socket=%s",
            workspace,
            lang_entry.server,
            socket_path,
        )

        # ── Import graph (for dependency analysis tools) ─────────────────
        from codebase._import_graph import ImportGraph

        import_graph = ImportGraph(workspace)
        try:
            import_graph.build_full()
            logger.info(
                "Import graph built: %d files indexed, %d skipped",
                import_graph.info()["files_indexed"],
                import_graph.info()["files_skipped"],
            )
        except Exception:
            logger.exception("Failed to build import graph — tools will return empty")

        # ── Task 1: File watcher ───────────────────────────────────────
        async def _watcher_loop() -> None:
            from file_watcher import WatchConfig, awatch_repos

            cfg = WatchConfig(
                force_polling=True,
                poll_delay_ms=300,
                debounce_ms=1600,
                defaults_filter=True,
                gitignore_filter=True,
            )
            logger.info("File watcher started (force_polling=True)")
            try:
                async for batch in awatch_repos([workspace], cfg):
                    await client.notify_file_changes(batch)
                    # Keep the import graph in sync with file changes.
                    try:
                        import_graph.update(
                            [e.abs_path for e in batch.events]
                        )
                    except Exception:
                        logger.exception(
                            "Failed to update import graph from watcher batch"
                        )
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "File watcher crashed — shutting down daemon"
                )
                if server_ref is not None:
                    server_ref.close()

        # ── Task 3: Idle watcher ───────────────────────────────────────
        # Periodically checks whether the daemon has been idle (no client
        # queries) for longer than _IDLE_TIMEOUT.  If so, triggers a
        # graceful shutdown.  The check interval is 1/3 of the timeout
        # (capped at 30 s) so we detect idle promptly without busy-waiting.

        async def _idle_watcher() -> None:
            check_interval = min(_IDLE_TIMEOUT / 3, 30.0)
            while True:
                await asyncio.sleep(check_interval)
                elapsed = time.monotonic() - last_activity
                if elapsed >= _IDLE_TIMEOUT:
                    logger.info(
                        "Idle timeout reached (%.0fs elapsed, limit=%.0fs) — "
                        "shutting down daemon",
                        elapsed,
                        _IDLE_TIMEOUT,
                    )
                    if server_ref is not None:
                        server_ref.close()
                    return

        # ── Task 2: Socket server ──────────────────────────────────────

        # ── Helpers for position-based queries ──────────────────────────
        # Shared by definition, type_definition, references, hover,
        # call_hierarchy_incoming, call_hierarchy_outgoing, rename_edits.

        def _position_from_params(params: dict) -> lsp_type.Position:
            """Extract (line, character) from params and build a Position.

            Converts 1-indexed user input to 0-indexed LSP protocol positions.
            The daemon is the normalization boundary — all human-facing
            interfaces (CLI, REST, MCP) speak 1-indexed; internally we
            translate to 0-indexed for the LSP server.
            """
            line = int(params.get("line", 1)) - 1
            character = int(params.get("character", 1)) - 1
            if line < 0 or character < 0:
                raise ValueError(
                    f"Position must be ≥ 1 (1-indexed). "
                    f"Got line={line + 1}, character={character + 1}"
                )
            return lsp_type.Position(line=line, character=character)

        def _file_error(req_id: int, file_str: str, context: str) -> dict:
            """Return a clean error dict for missing/bad file."""
            return {
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": f"File not found for {context}: {file_str}",
                },
            }

        def _to_workspace_rel(file_str: str, ws: Path) -> str:
            """Convert *file_str* to a workspace-relative path if absolute."""
            fp = Path(file_str)
            if fp.is_absolute():
                try:
                    return str(fp.resolve().relative_to(ws))
                except ValueError:
                    return file_str
            return file_str

        async def _query_positional(
            req_id: int,
            file_str: str,
            params: dict,
            lsp_call,
            label: str,
            lang_entry: LanguageEntry,
        ) -> dict:
            """Run a position-based LSP query and return the response dict.

            Parameters
            ----------
            lsp_call : callable
                Signature: ``await lsp_call(file_path, position) -> Any``.
                For ``rename_edits``, a lambda wrapping the extra ``new_name``
                arg is passed instead.
            """
            file_path = Path(file_str)
            try:
                position = _position_from_params(params)
                result = await lsp_call(file_path, position)
                return {
                    "id": req_id,
                    "result": {
                        "result": _lsp_result_to_json(result),
                        "file": file_str,
                        # Metadata fields are str (not int) so that
                        # _normalize_positions_to_one_indexed skips them.
                        # They record the user's 1-indexed input as-is.
                        "line": str(params.get("line", "")),
                        "character": str(params.get("character", "")),
                        "label": label,
                        "language": lang_entry.name,
                        "server": lang_entry.server,
                    },
                }
            except Exception as exc:
                return {
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": f"LSP error ({label}): {exc}",
                    },
                }

        async def _handle_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            """Handle one client: read request → dispatch → write response."""
            nonlocal last_activity
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=30.0)
                if not line:
                    return

                raw = line.decode("utf-8").strip()
                if not raw:
                    return

                # ── Reset idle timer on every client request ───────────
                # Any query (ping, symbols, status, etc.) counts as activity
                # and resets the idle shutdown clock.
                last_activity = time.monotonic()

                try:
                    req_data = json.loads(raw)
                except json.JSONDecodeError as exc:
                    err = json.dumps({
                        "id": 0,
                        "error": {"code": -32700, "message": f"Parse error: {exc}"},
                    }, ensure_ascii=False)
                    writer.write((err + "\n").encode())
                    await writer.drain()
                    return

                method = req_data.get("method", "")
                req_id = req_data.get("id", 0)
                params = req_data.get("params", {})

                match method:
                    case "ping":
                        resp = {"id": req_id, "result": {}}

                    case "shutdown":
                        resp = {"id": req_id, "result": {}}
                        writer.write(
                            (json.dumps(resp, ensure_ascii=False) + "\n").encode()
                        )
                        await writer.drain()
                        if server_ref is not None:
                            server_ref.close()
                        return

                    case "status":
                        resp = {
                            "id": req_id,
                            "result": {
                                "language": lang_entry.name,
                                "server": lang_entry.server,
                            },
                        }

                    case "symbols":
                        file_str = params.get("file", "")
                        if not file_str:
                            resp = {
                                "id": req_id,
                                "error": {
                                    "code": -32602,
                                    "message": "Missing 'file' parameter",
                                },
                            }
                        else:
                            file_path = Path(file_str)
                            # ── File existence check ───────────────────
                            # The lsp-client library crashes with an
                            # ExceptionGroup when the file doesn't exist
                            # (read_file inside a TaskGroup).  Check here
                            # so we can return a clean error instead.
                            if not file_path.is_file():
                                resp = {
                                    "id": req_id,
                                    "error": {
                                        "code": -32000,
                                        "message": f"File not found: {file_str}",
                                    },
                                }
                            else:
                                try:
                                    symbols = await client.request_document_symbol_list(
                                        file_path
                                    )
                                    formatted = _symbol_tree_to_dict(symbols)
                                    resp = {
                                        "id": req_id,
                                        "result": {
                                            "symbols": formatted,
                                            "file": file_str,
                                            "language": lang_entry.name,
                                            "server": lang_entry.server,
                                        },
                                    }
                                except Exception as exc:
                                    resp = {
                                        "id": req_id,
                                        "error": {
                                            "code": -32000,
                                            "message": f"LSP error: {exc}",
                                        },
                                    }

                    # ── workspace_symbol ────────────────────────────────
                    # Query: workspace/symbol.  Returns a flat list of
                    # symbols matching the query string across the entire
                    # workspace (fuzzy substring match with basedpyright).
                    case "workspace_symbol":
                        query_str = params.get("query", "")
                        if not query_str:
                            resp = {
                                "id": req_id,
                                "error": {
                                    "code": -32602,
                                    "message": "Missing 'query' parameter",
                                },
                            }
                        else:
                            try:
                                symbols = await client.request_workspace_symbol_list(
                                    query_str
                                )
                                resp = {
                                    "id": req_id,
                                    "result": {
                                        "symbols": _lsp_result_to_json(symbols),
                                        "query": query_str,
                                        "language": lang_entry.name,
                                        "server": lang_entry.server,
                                    },
                                }
                            except Exception as exc:
                                resp = {
                                    "id": req_id,
                                    "error": {
                                        "code": -32000,
                                        "message": f"LSP error: {exc}",
                                    },
                                }

                    # ── definition ──────────────────────────────────────
                    case "definition":
                        file_str = params.get("file", "")
                        if not file_str or not Path(file_str).is_file():
                            resp = _file_error(req_id, file_str, "definition")
                        else:
                            resp = await _query_positional(
                                req_id,
                                file_str,
                                params,
                                client.request_definition,
                                "go-to-definition",
                                lang_entry,
                            )

                    # ── type_definition ─────────────────────────────────
                    case "type_definition":
                        file_str = params.get("file", "")
                        if not file_str or not Path(file_str).is_file():
                            resp = _file_error(req_id, file_str, "type definition")
                        else:
                            resp = await _query_positional(
                                req_id,
                                file_str,
                                params,
                                client.request_type_definition,
                                "go-to-type-definition",
                                lang_entry,
                            )

                    # ── references ──────────────────────────────────────
                    case "references":
                        file_str = params.get("file", "")
                        if not file_str or not Path(file_str).is_file():
                            resp = _file_error(req_id, file_str, "references")
                        else:
                            resp = await _query_positional(
                                req_id,
                                file_str,
                                params,
                                client.request_references,
                                "references",
                                lang_entry,
                            )

                    # ── hover ───────────────────────────────────────────
                    case "hover":
                        file_str = params.get("file", "")
                        if not file_str or not Path(file_str).is_file():
                            resp = _file_error(req_id, file_str, "hover")
                        else:
                            resp = await _query_positional(
                                req_id,
                                file_str,
                                params,
                                client.request_hover,
                                "hover",
                                lang_entry,
                            )

                    # ── call_hierarchy_incoming ─────────────────────────
                    case "call_hierarchy_incoming":
                        file_str = params.get("file", "")
                        if not file_str or not Path(file_str).is_file():
                            resp = _file_error(
                                req_id, file_str, "call hierarchy incoming"
                            )
                        else:
                            resp = await _query_positional(
                                req_id,
                                file_str,
                                params,
                                client.request_call_hierarchy_incoming_call,
                                "call-hierarchy-incoming",
                                lang_entry,
                            )

                    # ── call_hierarchy_outgoing ─────────────────────────
                    case "call_hierarchy_outgoing":
                        file_str = params.get("file", "")
                        if not file_str or not Path(file_str).is_file():
                            resp = _file_error(
                                req_id, file_str, "call hierarchy outgoing"
                            )
                        else:
                            resp = await _query_positional(
                                req_id,
                                file_str,
                                params,
                                client.request_call_hierarchy_outgoing_call,
                                "call-hierarchy-outgoing",
                                lang_entry,
                            )

                    # ── rename_edits ────────────────────────────────────
                    # Uses request_rename_edits (preview) — does NOT apply
                    # the rename, only returns the WorkspaceEdit.
                    case "rename_edits":
                        file_str = params.get("file", "")
                        new_name = params.get("new_name", "")
                        if not file_str or not Path(file_str).is_file():
                            resp = _file_error(req_id, file_str, "rename edits")
                        elif not new_name:
                            resp = {
                                "id": req_id,
                                "error": {
                                    "code": -32602,
                                    "message": "Missing 'new_name' parameter",
                                },
                            }
                        else:
                            resp = await _query_positional(
                                req_id,
                                file_str,
                                params,
                                lambda fp, pos: client.request_rename_edits(
                                    fp, pos, new_name
                                ),
                                "rename-edits",
                                lang_entry,
                            )

                    # ── diagnostics ─────────────────────────────────────
                    case "diagnostics":
                        file_str = params.get("file", "")
                        if not file_str:
                            resp = {
                                "id": req_id,
                                "error": {
                                    "code": -32602,
                                    "message": "Missing 'file' parameter",
                                },
                            }
                        else:
                            file_path = Path(file_str)
                            if not file_path.is_file():
                                resp = _file_error(req_id, file_str, "diagnostics")
                            else:
                                try:
                                    # ── Open file in LSP server ─────────
                                    # Diagnostics are push-based — the LSP
                                    # server only publishes them for files
                                    # that have been opened via didOpen.
                                    # Read content and notify the server
                                    # so it starts analysing the file.
                                    file_content = file_path.read_text()
                                    await client.notify_text_document_opened(
                                        file_path, file_content
                                    )
                                    diags = await client.get_diagnostics(file_path)
                                    resp = {
                                        "id": req_id,
                                        "result": {
                                            "diagnostics": _lsp_result_to_json(diags),
                                            "file": file_str,
                                            "language": lang_entry.name,
                                            "server": lang_entry.server,
                                        },
                                    }
                                except Exception as exc:
                                    resp = {
                                        "id": req_id,
                                        "error": {
                                            "code": -32000,
                                            "message": f"LSP error: {exc}",
                                        },
                                    }

                    # ── import_dependents ───────────────────────────────────
                    case "import_dependents":
                        file_str = _to_workspace_rel(params.get("file", ""), workspace)
                        depth = int(params.get("depth", "1"))
                        result = import_graph.dependents(file_str, depth=depth)
                        resp = {
                            "id": req_id,
                            "result": {
                                "file": file_str,
                                "dependents": result,
                                "depth": depth,
                                "info": import_graph.info(),
                            },
                        }

                    # ── import_dependencies ────────────────────────────────
                    case "import_dependencies":
                        file_str = _to_workspace_rel(params.get("file", ""), workspace)
                        result = import_graph.dependencies(file_str)
                        resp = {
                            "id": req_id,
                            "result": {
                                "file": file_str,
                                "dependencies": result,
                                "info": import_graph.info(),
                            },
                        }

                    # ── import_affected_tests ──────────────────────────────
                    case "import_affected_tests":
                        file_str = _to_workspace_rel(params.get("file", ""), workspace)
                        depth = int(params.get("depth", "10"))
                        result = import_graph.affected_tests(file_str, depth=depth)
                        resp = {
                            "id": req_id,
                            "result": {
                                "file": file_str,
                                "affected_test_files": result,
                                "depth": depth,
                                "info": import_graph.info(),
                            },
                        }

                    # ── architecture ─────────────────────────────────────
                    case "architecture":
                        from codebase._arch import _compute_architecture

                        hotspots = int(params.get("hotspots", "20"))
                        result = _compute_architecture(import_graph, hotspots=hotspots)
                        resp = {
                            "id": req_id,
                            "result": result,
                        }

                    # ── graph_reindex ────────────────────────────────────
                    case "graph_reindex":
                        # Accept a JSON-encoded list of absolute file paths.
                        files_raw = params.get("files", "[]")
                        try:
                            files_list: list[str] = json.loads(files_raw)
                        except (json.JSONDecodeError, TypeError):
                            files_list = []
                        import_graph.update([Path(p) for p in files_list])
                        resp = {
                            "id": req_id,
                            "result": import_graph.info(),
                        }

                    case _:
                        resp = {
                            "id": req_id,
                            "error": {
                                "code": -32601,
                                "message": f"Unknown method: {method}",
                            },
                        }

                # ── Normalize output ───────────────────────────────────
                # (1) LSP positions: 0‑indexed → 1‑indexed
                # (2) LSP kind integers → human-readable names
                if "result" in resp:
                    resp["result"] = _normalize_positions_to_one_indexed(
                        resp["result"]
                    )
                    resp["result"] = _replace_kind_integers(resp["result"])

                writer.write(
                    (json.dumps(resp, ensure_ascii=False) + "\n").encode()
                )
                await writer.drain()

            except asyncio.TimeoutError:
                pass
            except Exception:
                logger.exception("Error handling client connection")
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        server = await asyncio.start_unix_server(_handle_client, path=socket_path)
        server_ref = server  # ← closures can now call server_ref.close()

        # Make the socket world-accessible (Docker host/container user mismatch).
        try:
            os.chmod(socket_path, 0o666)
        except OSError:
            pass

        logger.info("Socket server listening on %s", socket_path)

        # ── Run until shutdown ─────────────────────────────────────────
        # Block on serve_forever().  Returns when:
        # - Idle timeout reached → idle watcher calls server_ref.close().
        # - Watcher crashes → server_ref.close() was called.
        # - Client sends "shutdown" → server_ref.close() was called.
        # - LspClient crashes → exception in async with → finally below.
        watcher_task = asyncio.create_task(_watcher_loop())
        idle_task = asyncio.create_task(_idle_watcher())

        try:
            await server.serve_forever()
        finally:
            logger.info("Daemon shutting down...")
            idle_task.cancel()
            watcher_task.cancel()
            try:
                await asyncio.gather(idle_task, watcher_task, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# __main__ — invoked as `python <path>/lsp/_daemon.py <workspace> <socket_path>`
# ──────────────────────────────────────────────────────────────────────────────
# The sys.path fix at the very top of this file (before all local imports)
# ensures `lsp` and `file_watcher` are importable when running as a script.

if __name__ == "__main__":
    # Configure logging to stderr (redirected to log file by subprocess.Popen).
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [daemon] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )

    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.executable} {__file__} <workspace> <socket_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    _workspace = Path(sys.argv[1])
    _socket = Path(sys.argv[2])

    logger.info("Daemon starting: workspace=%s, socket=%s", _workspace, _socket)

    # Load language config — select the first entry (MVP: single-client daemon).
    # In the future, multi-language daemons will use the full list.
    lang_entries = _load_language_config()
    lang_entry = lang_entries[0]

    try:
        asyncio.run(_run_daemon(_workspace, _socket, lang_entry))
    except asyncio.CancelledError:
        # Expected: server.close() cancels serve_forever(), which raises
        # CancelledError.  This is a normal shutdown path, not a crash.
        logger.info("Daemon shut down cleanly")
    except KeyboardInterrupt:
        logger.info("Daemon interrupted")
    except Exception:
        logger.exception("Daemon crashed")
    finally:
        _socket.unlink(missing_ok=True)
        logger.info("Daemon exited")
