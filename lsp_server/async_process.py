from __future__ import annotations

"""Async stdio transport for LSP (JSON-RPC over stdin/stdout).

What this file does
- Starts and manages a language server subprocess (like basedpyright).
- Speaks the LSP wire format over stdin/stdout using JSON-RPC messages.
- Keeps background reader tasks running so the server never blocks on full pipes.

Why this is needed
- LSP servers communicate over a stream (stdio), not sockets by default.
- Messages are framed with a Content-Length header, so we must parse that.
- The client must keep reading from stdout/stderr to avoid deadlocks.

How to read this file
- AsyncStdioLspProcess is the main class.
- request() sends a message and waits for a matching response id.
- notify() sends a message that expects no response.
- _read_loop() parses incoming messages and dispatches them.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

from .spec import LspServerSpec
from .types import JsonDict, JsonValue

log = logging.getLogger(__name__)

# Request: server asks client for data (e.g., workspace/configuration).
RequestHandler = Callable[[str, JsonDict | None], Awaitable[JsonValue]]
# Notification: server sends a message that doesn't expect a reply.
NotificationHandler = Callable[[JsonDict | None], Awaitable[None]]


class LspResponseError(Exception):
    """Represents an error returned by the LSP server for a request."""

    def __init__(self, code: int, message: str, data: JsonValue | None = None) -> None:
        super().__init__(f"LSP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class LspMethodNotFound(Exception):
    """Raised when the client does not implement a server-requested method."""

    pass


@dataclass
class _PendingRequest:
    # Future resolved when a response with the same id is received.
    future: asyncio.Future[JsonValue]


class AsyncStdioLspProcess:
    """Run an LSP server subprocess and communicate via stdio.

    This class handles JSON-RPC framing, response matching, notification dispatch,
    and background I/O tasks so the server does not block on full pipes.
    """

    def __init__(self, spec: LspServerSpec, process: asyncio.subprocess.Process) -> None:
        """Create a wrapper around an already-started subprocess."""
        self._spec = spec
        self._process = process
        self._write_lock = asyncio.Lock()
        # Map JSON-RPC id -> pending request future.
        self._pending: dict[int, _PendingRequest] = {}
        self._next_id = 0
        # Map method name -> list of notification handlers.
        self._notification_handlers: dict[str, list[NotificationHandler]] = {}
        self._request_handler: RequestHandler | None = None
        # Start background tasks immediately so pipes are drained.
        self._reader_task = asyncio.create_task(self._read_loop(), name="lsp-read-loop")
        self._stderr_task = asyncio.create_task(self._stderr_loop(), name="lsp-stderr-loop")

    @property
    def spec(self) -> LspServerSpec:
        """Return the launch spec used for this process."""
        return self._spec

    @classmethod
    async def start(cls, spec: LspServerSpec) -> "AsyncStdioLspProcess":
        """Start a subprocess using the spec and return a ready wrapper."""
        # Merge process environment with spec overrides.
        env = {**os.environ, **dict(spec.env)} if spec.env else None
        
        # We use start_new_session=True to ensure the child process does not
        # receive signals (like SIGINT from Ctrl+C) sent to the parent's
        # terminal process group. This allows the parent to manage the
        # child's lifecycle gracefully.
        process = await asyncio.create_subprocess_exec(
            *spec.argv,
            cwd=str(spec.cwd),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        return cls(spec=spec, process=process)

    def is_running(self) -> bool:
        """Return True if the subprocess has not exited."""
        return self._process.returncode is None

    def set_request_handler(self, handler: RequestHandler | None) -> None:
        """Set the handler for server->client requests."""
        # Called when the server sends a request that expects a response.
        self._request_handler = handler

    def add_notification_handler(self, method: str, handler: NotificationHandler) -> None:
        """Register a handler for a server->client notification method."""
        # Register callbacks for server notifications.
        self._notification_handlers.setdefault(method, []).append(handler)

    async def request(self, method: str, params: JsonDict | None = None) -> JsonValue:
        """Send a request and wait for the response result."""
        # Send a request and await its response.
        self._next_id += 1
        msg_id = self._next_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future[JsonValue] = loop.create_future()
        self._pending[msg_id] = _PendingRequest(future=future)

        await self._send_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": method,
                "params": params or {},
            }
        )

        return await future

    async def notify(self, method: str, params: JsonDict | None = None) -> None:
        """Send a notification (no response expected)."""
        # Fire-and-forget notification.
        await self._send_message(
            {"jsonrpc": "2.0", "method": method, "params": params or {}}
        )

    async def _send_message(self, payload: JsonDict) -> None:
        """Write a JSON-RPC message to stdin with proper framing."""
        # Log outgoing message at DEBUG level
        log.debug("LSP -> %s", json.dumps(payload, ensure_ascii=True))

        # JSON-RPC message framing: Content-Length header + JSON body.
        stdin = self._process.stdin
        if stdin is None:
            raise RuntimeError("LSP process stdin is not available")

        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        async with self._write_lock:
            stdin.write(header)
            stdin.write(body)
            await stdin.drain()

    async def close(self) -> None:
        """Stop background tasks and terminate the subprocess."""
        # Stop background tasks and terminate the subprocess.
        await self._shutdown_tasks()
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

    async def _shutdown_tasks(self) -> None:
        """Cancel reader tasks and wait for them to finish."""
        # Ensure reader tasks stop before terminating the process.
        for task in (self._reader_task, self._stderr_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(self._reader_task, self._stderr_task, return_exceptions=True)

    async def _read_loop(self) -> None:
        """Continuously read messages from stdout and dispatch them."""
        # Main read loop: parse messages and dispatch by type.
        while True:
            try:
                msg = await self._read_message()
            except EOFError:
                return
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("LSP read loop error")
                return

            if "id" in msg and ("result" in msg or "error" in msg):
                await self._handle_response(msg)
                continue
            if "id" in msg and "method" in msg:
                await self._handle_server_request(msg)
                continue
            if "method" in msg:
                await self._handle_notification(msg)

    async def _stderr_loop(self) -> None:
        """Continuously drain stderr so the server never blocks."""
        # Drain stderr to avoid blocking the server on full buffers.
        if self._process.stderr is None:
            return
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                log.info("LSP stderr: %s", text)
        except asyncio.CancelledError:
            return

    async def _read_message(self) -> JsonDict:
        """Read a single LSP message from stdout and parse JSON."""
        # Read header until CRLFCRLF, then read body of Content-Length.
        stdout = self._process.stdout
        if stdout is None:
            raise EOFError

        try:
            header_bytes = await stdout.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError as exc:
            if exc.partial:
                log.debug("Incomplete LSP header: %r", exc.partial)
            raise EOFError from exc
        except asyncio.LimitOverrunError as exc:
            raise EOFError from exc

        header_text = header_bytes.decode("ascii", errors="replace")
        content_length = self._parse_content_length(header_text)
        body = await stdout.readexactly(content_length)
        parsed = json.loads(body.decode("utf-8"))

        # Log incoming message at DEBUG level
        log.debug("LSP <- %s", json.dumps(parsed, ensure_ascii=True))

        return parsed

    @staticmethod
    def _parse_content_length(header_text: str) -> int:
        """Extract the Content-Length header value from the message header."""
        # LSP uses a Content-Length header for message framing.
        for line in header_text.split("\r\n"):
            if not line:
                continue
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            key, value = parts[0].strip().lower(), parts[1].strip()
            if key == "content-length":
                return int(value)
        raise ValueError("Missing Content-Length header")

    async def _handle_response(self, msg: JsonDict) -> None:
        """Resolve or reject a pending request based on the response."""
        # Resolve the pending future for this response id.
        msg_id = msg.get("id")
        pending = self._pending.pop(msg_id, None)
        if pending is None:
            log.warning("Received response for unknown request id: %s", msg_id)
            return
        future = pending.future
        if "error" in msg:
            error = msg.get("error") or {}
            code = int(error.get("code", -1))
            message = str(error.get("message", "Unknown error"))
            data = error.get("data")
            future.set_exception(LspResponseError(code=code, message=message, data=data))
            return
        future.set_result(msg.get("result"))

    async def _handle_server_request(self, msg: JsonDict) -> None:
        """Handle a server-initiated request and send a response."""
        # Server requests must be answered; otherwise it may hang.
        msg_id = msg.get("id")
        method = str(msg.get("method"))
        params = msg.get("params")

        if self._request_handler is None:
            await self._send_error(msg_id, code=-32601, message="Method not found")
            return

        try:
            result = await self._request_handler(method, params)
        except LspMethodNotFound:
            await self._send_error(msg_id, code=-32601, message="Method not found")
            return
        except Exception as exc:
            await self._send_error(msg_id, code=-32603, message=str(exc))
            return

        await self._send_message({"jsonrpc": "2.0", "id": msg_id, "result": result})

    async def _handle_notification(self, msg: JsonDict) -> None:
        """Dispatch a server notification to registered handlers."""
        # Notifications do not expect a response.
        method = str(msg.get("method"))
        params = msg.get("params")

        # Selective INFO-level logging for useful notifications
        if method == "window/logMessage" and isinstance(params, dict):
            msg_type = params.get("type", 3)
            msg_text = params.get("message", "")
            if msg_type == 1:
                log.error("LSP: %s", msg_text)
            elif msg_type == 2:
                log.warning("LSP: %s", msg_text)
            elif msg_type == 3:
                log.info("LSP: %s", msg_text)
            else:  # type 4 = Log
                log.debug("LSP: %s", msg_text)
        elif method == "window/showMessage" and isinstance(params, dict):
            msg_text = params.get("message", "")
            log.info("LSP message: %s", msg_text)
        elif method in ("$/progress", "pyright/beginProgress", "pyright/reportProgress"):
            # Progress messages at DEBUG level
            log.debug("LSP progress (%s): %s", method, params)

        handlers = self._notification_handlers.get(method, [])
        for handler in handlers:
            try:
                await handler(params)
            except Exception:
                log.exception("Notification handler failed: %s", method)

    async def _send_error(self, msg_id: JsonValue, code: int, message: str) -> None:
        """Send a JSON-RPC error response to a server request."""
        await self._send_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": code, "message": message},
            }
        )
