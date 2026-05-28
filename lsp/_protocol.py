"""LD‑JSON request/response protocol over Unix domain sockets.

What this module provides
- Request / Response dataclasses for daemon communication.
- send_request: synchronous send-one-line / recv-one-line over a Unix socket.

Why this exists
- The CLI (and future MCP/REST endpoints) communicate with the persistent LSP
  daemon via a lightweight, line-delimited JSON protocol. Unix sockets avoid
  port conflicts, and the socket file doubles as a liveness check.

How to use (client side)
    from lsp._protocol import Request, send_request

    req = Request(id=1, method="symbols", params={"file": "/path/to/file.py"})
    resp = send_request(socket_path, req)
    if resp.error:
        raise RuntimeError(resp.error["message"])
    print(resp.result["symbols"])

The daemon (server side) reads one line, dispatches by method,
and writes one response line — see lsp._daemon._run_daemon().
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Request:
    """A request sent from client to daemon over the Unix socket.

    Attributes
    ----------
    id : int
        Request identifier (echoed in response). Monotonically increasing
        per-session for future pipelining, though v1 uses one request per
        connection.
    method : str
        Method name, e.g. "symbols", "ping", "shutdown".
    params : dict[str, str]
        Method-specific parameters. Keys and values are always strings
        on the wire (file paths, etc.). The daemon handles conversion.
    """

    id: int
    method: str
    params: dict[str, str]


@dataclass(frozen=True, slots=True)
class Response:
    """A response sent from daemon back to client.

    Exactly one of *result* or *error* is non-None on success/error.

    Attributes
    ----------
    id : int
        Echo of the request id.
    result : dict | None
        Successful response payload. Arbitrary JSON structure.
    error : dict | None
        Error object with ``code`` (int) and ``message`` (str) keys.
    """

    id: int
    result: dict | None = None
    error: dict | None = None


# ── Transport ----------------------------------------------------------------


def send_request(
    socket_path: Path,
    request: Request,
    *,
    timeout: float = 5.0,
) -> Response:
    """Send one request and receive one response over a Unix socket.

    Opens a connection, writes the request as a single LD‑JSON line, reads
    one response line, and closes the connection.  The socket must already
    exist and be listening (the daemon must be running).

    Parameters
    ----------
    socket_path : Path
        Path to the Unix domain socket file.
    request : Request
        Request to send. Serialized via ``dataclasses.asdict``.
    timeout : float
        Connection + send + recv timeout in seconds. Defaults to 5.0.

    Returns
    -------
    Response
        Parsed response from the daemon. Check ``.error`` for failures.

    Raises
    ------
    ConnectionRefusedError
        If no daemon is listening on *socket_path*.
    socket.timeout
        If the connection, send, or receive exceeds *timeout*.
    json.JSONDecodeError
        If the response is not valid JSON.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        sock.connect(str(socket_path))

        # Encode request as a single LD‑JSON line.
        raw_req = json.dumps(
            {"id": request.id, "method": request.method, "params": request.params},
            ensure_ascii=False,
        )
        sock.sendall((raw_req + "\n").encode("utf-8"))

        # Read one response line.  Use a buffer and recv() in a loop to handle
        # responses that come in multiple TCP segments.
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("Daemon closed connection before sending a response")
            buf += chunk

        line = buf.split(b"\n", 1)[0]
        raw_resp = line.decode("utf-8")
        data = json.loads(raw_resp)

        return Response(
            id=data.get("id", 0),
            result=data.get("result"),
            error=data.get("error"),
        )
    finally:
        sock.close()


def ping(socket_path: Path, *, timeout: float = 2.0) -> bool:
    """Return True if a daemon is listening on *socket_path*.

    Sends a lightweight ``ping`` request; returns False on any error
    (connection refused, timeout, bad response).

    Parameters
    ----------
    socket_path : Path
        Path to the Unix domain socket file.
    timeout : float
        Connection timeout in seconds.

    Returns
    -------
    bool
        True if the daemon responded to ping.
    """
    try:
        resp = send_request(
            socket_path,
            Request(id=0, method="ping", params={}),
            timeout=timeout,
        )
        return resp.error is None
    except Exception:
        return False
