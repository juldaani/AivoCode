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
- Daemon: asyncio event loop running three concurrent tasks:
  1. **file watcher**: ``awatch_repos`` with ``force_polling=True``.
     Forwards every batch to ``client.notify_file_changes()``.
  2. **Unix socket server**: accepts connections, reads one line, dispatches
     by method name, writes one response line.
  3. **LspClient**: kept alive as async context manager.  Query methods
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
from lsp._serialize import _symbol_tree_to_dict
from lsp.client import LspClient
from lsp.config import LanguageEntry

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
# In the future this will come from lsp_config.toml or CLI arguments.

_DEFAULT_PYTHON_LANG = LanguageEntry(
    name="python",
    suffixes=(".py", ".pyi"),
    server="basedpyright-langserver",
    server_args=("--stdio",),
)

logger = logging.getLogger(__name__)


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
        return socket_path

    # ── Daemon not running — spawn it ──────────────────────────────────
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

    Parameters
    ----------
    workspace : Path
        Git repo root.
    """
    socket_path = _socket_path(workspace)
    if not _is_running(socket_path):
        socket_path.unlink(missing_ok=True)
        return

    try:
        send_request(
            socket_path,
            Request(id=0, method="shutdown", params={}),
            timeout=3.0,
        )
    except Exception:
        logger.warning("Failed to send shutdown to daemon at %s", socket_path)
    finally:
        time.sleep(0.2)
        socket_path.unlink(missing_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# Daemon process entry point
# ──────────────────────────────────────────────────────────────────────────────


async def _run_daemon(
    workspace: Path,
    socket_path: Path,
    lang_entry: LanguageEntry,
) -> None:
    """Main daemon loop — runs until shutdown or a component crash.

    Crash-fast design: if the file watcher or LSP server fails, the entire
    daemon shuts down.  The next incoming CLI query will auto-start a fresh
    daemon via :func:`ensure_daemon`.  There is no retry — stale state
    (e.g. watcher out of sync with LSP index) is worse than a clean restart.

    Failure paths:
    - Watcher crash → ``server.close()`` → ``serve_forever()`` returns → exit.
    - Client sends ``"shutdown"`` → ``server.close()`` → exit (graceful).
    - LspClient crash → exception in ``async with`` → ``finally`` cleans up.
    """
    socket_path.unlink(missing_ok=True)

    # ── server_ref — mutable closure capture ───────────────────────────
    # The watcher and socket handler both need to close the server to
    # trigger daemon shutdown.  The server instance doesn't exist yet when
    # these functions are defined, so we capture a mutable cell and assign
    # it after ``start_unix_server``.
    server_ref: asyncio.AbstractServer | None = None

    async with LspClient(lang_entry=lang_entry, workspace=workspace) as client:
        logger.info(
            "LSP daemon started: workspace=%s, server=%s, socket=%s",
            workspace,
            lang_entry.server,
            socket_path,
        )

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
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "File watcher crashed — shutting down daemon"
                )
                if server_ref is not None:
                    server_ref.close()

        # ── Task 2: Socket server ──────────────────────────────────────

        async def _handle_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            """Handle one client: read request → dispatch → write response."""
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=30.0)
                if not line:
                    return

                raw = line.decode("utf-8").strip()
                if not raw:
                    return

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

                    case _:
                        resp = {
                            "id": req_id,
                            "error": {
                                "code": -32601,
                                "message": f"Unknown method: {method}",
                            },
                        }

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
        # - Watcher crashes → server_ref.close() was called.
        # - Client sends "shutdown" → server_ref.close() was called.
        # - LspClient crashes → exception in async with → finally below.
        watcher_task = asyncio.create_task(_watcher_loop())

        try:
            await server.serve_forever()
        finally:
            logger.info("Daemon shutting down...")
            watcher_task.cancel()
            try:
                await watcher_task
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

    try:
        asyncio.run(_run_daemon(_workspace, _socket, _DEFAULT_PYTHON_LANG))
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
