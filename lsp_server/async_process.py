from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

from .spec import LspServerSpec
from .types import JsonDict, JsonValue

log = logging.getLogger(__name__)

RequestHandler = Callable[[str, JsonDict | None], Awaitable[JsonValue]]
NotificationHandler = Callable[[JsonDict | None], Awaitable[None]]


class LspResponseError(Exception):
    def __init__(self, code: int, message: str, data: JsonValue | None = None) -> None:
        super().__init__(f"LSP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class LspMethodNotFound(Exception):
    pass


@dataclass
class _PendingRequest:
    future: asyncio.Future[JsonValue]


class AsyncStdioLspProcess:
    def __init__(self, spec: LspServerSpec, process: asyncio.subprocess.Process) -> None:
        self._spec = spec
        self._process = process
        self._write_lock = asyncio.Lock()
        self._pending: dict[int, _PendingRequest] = {}
        self._next_id = 0
        self._notification_handlers: dict[str, list[NotificationHandler]] = {}
        self._request_handler: RequestHandler | None = None
        self._reader_task = asyncio.create_task(self._read_loop(), name="lsp-read-loop")
        self._stderr_task = asyncio.create_task(self._stderr_loop(), name="lsp-stderr-loop")

    @property
    def spec(self) -> LspServerSpec:
        return self._spec

    @classmethod
    async def start(cls, spec: LspServerSpec) -> "AsyncStdioLspProcess":
        env = {**os.environ, **dict(spec.env)} if spec.env else None
        process = await asyncio.create_subprocess_exec(
            *spec.argv,
            cwd=str(spec.cwd),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return cls(spec=spec, process=process)

    def is_running(self) -> bool:
        return self._process.returncode is None

    def set_request_handler(self, handler: RequestHandler | None) -> None:
        self._request_handler = handler

    def add_notification_handler(self, method: str, handler: NotificationHandler) -> None:
        self._notification_handlers.setdefault(method, []).append(handler)

    async def request(self, method: str, params: JsonDict | None = None) -> JsonValue:
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
        await self._send_message(
            {"jsonrpc": "2.0", "method": method, "params": params or {}}
        )

    async def _send_message(self, payload: JsonDict) -> None:
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
        await self._shutdown_tasks()
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

    async def _shutdown_tasks(self) -> None:
        for task in (self._reader_task, self._stderr_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(self._reader_task, self._stderr_task, return_exceptions=True)

    async def _read_loop(self) -> None:
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
        if self._process.stderr is None:
            return
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                log.debug("LSP stderr: %s", text)
        except asyncio.CancelledError:
            return

    async def _read_message(self) -> JsonDict:
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
        return json.loads(body.decode("utf-8"))

    @staticmethod
    def _parse_content_length(header_text: str) -> int:
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
        method = str(msg.get("method"))
        params = msg.get("params")
        handlers = self._notification_handlers.get(method, [])
        for handler in handlers:
            try:
                await handler(params)
            except Exception:
                log.exception("Notification handler failed: %s", method)

    async def _send_error(self, msg_id: JsonValue, code: int, message: str) -> None:
        await self._send_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": code, "message": message},
            }
        )
