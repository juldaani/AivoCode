"""One-off vtsls documentSymbol probe.

This script intentionally does not use the repo's lsp/ package.  It speaks the
minimum JSON-RPC/LSP framing needed to start `vtsls --stdio`, open a TypeScript
file from tests/data/mock_repos/typescript, and request textDocument/documentSymbol.

Run from the repository root:
    python typescript_lsp_tst/test_document_symbol_vtsls.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "tests" / "data" / "mock_repos" / "typescript"
TARGET = WORKSPACE / "mock_pkg" / "index.ts"


def uri(path: Path) -> str:
    return path.resolve().as_uri()


def read_message(proc: subprocess.Popen[bytes], timeout: float = 10.0) -> dict[str, Any] | None:
    """Read one LSP message from stdout with a timeout guarded by a helper thread."""
    result: list[dict[str, Any] | None] = []
    error: list[BaseException] = []

    def worker() -> None:
        try:
            headers: dict[str, str] = {}
            while True:
                line = proc.stdout.readline() if proc.stdout is not None else b""
                if line == b"":
                    result.append(None)
                    return
                if line in (b"\r\n", b"\n"):
                    break
                name, value = line.decode("ascii").split(":", 1)
                headers[name.lower()] = value.strip()

            content_length = int(headers["content-length"])
            body = proc.stdout.read(content_length) if proc.stdout is not None else b""
            result.append(json.loads(body.decode("utf-8")))
        except BaseException as exc:  # noqa: BLE001 - smoke probe should print raw failures.
            error.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return None
    if error:
        raise error[0]
    return result[0] if result else None


def write_message(proc: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    if proc.stdin is None:
        raise RuntimeError("server stdin is closed")
    proc.stdin.write(header + body)
    proc.stdin.flush()


def wait_for_response(
    proc: subprocess.Popen[bytes], request_id: int, timeout: float = 20.0
) -> dict[str, Any]:
    """Return the response for request_id while printing server notifications/requests."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = read_message(proc, timeout=max(0.1, min(2.0, deadline - time.monotonic())))
        if message is None:
            continue

        if message.get("id") == request_id:
            return message

        # vtsls sends useful window/logMessage and telemetry notifications while
        # booting. Keep these visible because this is a diagnostic throwaway script.
        print("SERVER:", json.dumps(message, indent=2), flush=True)

        # LSP servers may send client/registerCapability or configuration requests.
        # Reply with harmless defaults so initialization can continue.
        if "id" in message and "method" in message:
            method = message["method"]
            if method == "workspace/configuration":
                result: Any = [{} for _ in message.get("params", {}).get("items", [])]
            else:
                result = None
            write_message(proc, {"jsonrpc": "2.0", "id": message["id"], "result": result})

    raise TimeoutError(f"timed out waiting for response id={request_id}")


def main() -> int:
    if not WORKSPACE.exists() or not TARGET.exists():
        print(f"missing workspace or target: {WORKSPACE} / {TARGET}", file=sys.stderr)
        return 2

    text = TARGET.read_text(encoding="utf-8")
    proc = subprocess.Popen(
        ["vtsls", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=WORKSPACE,
        env={**os.environ, "TSS_LOG": "-level verbose"},
    )

    stderr_thread = threading.Thread(
        target=lambda: [print("STDERR:", line.decode(errors="replace").rstrip()) for line in proc.stderr or []],
        daemon=True,
    )
    stderr_thread.start()

    try:
        initialize_id = 1
        write_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": initialize_id,
                "method": "initialize",
                "params": {
                    "processId": os.getpid(),
                    "clientInfo": {"name": "aivocode-vtsls-probe", "version": "0"},
                    "rootPath": str(WORKSPACE),
                    "rootUri": uri(WORKSPACE),
                    "workspaceFolders": [{"uri": uri(WORKSPACE), "name": "typescript"}],
                    "capabilities": {
                        "workspace": {
                            "configuration": True,
                            "workspaceFolders": True,
                        },
                        "textDocument": {
                            "documentSymbol": {
                                "dynamicRegistration": False,
                                "hierarchicalDocumentSymbolSupport": True,
                                "symbolKind": {"valueSet": list(range(1, 27))},
                            }
                        },
                    },
                    "initializationOptions": {},
                    "trace": "verbose",
                },
            },
        )
        init_response = wait_for_response(proc, initialize_id)
        print("INITIALIZE RESPONSE:", json.dumps(init_response, indent=2), flush=True)
        if "error" in init_response:
            return 1

        write_message(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})

        document = {"uri": uri(TARGET), "languageId": "typescript", "version": 1, "text": text}
        write_message(
            proc,
            {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": document}},
        )

        # Give tsserver a brief chance to load the project after didOpen.  Without
        # this vtsls can still answer, but diagnostics/log notifications are noisier.
        time.sleep(1.0)

        symbols_id = 2
        write_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": symbols_id,
                "method": "textDocument/documentSymbol",
                "params": {"textDocument": {"uri": uri(TARGET)}},
            },
        )
        symbols_response = wait_for_response(proc, symbols_id)
        print("DOCUMENT SYMBOL RESPONSE:", json.dumps(symbols_response, indent=2), flush=True)

        result = symbols_response.get("result")
        if isinstance(result, list):
            print(f"documentSymbol returned {len(result)} top-level symbols")
            for symbol in result:
                print(" -", symbol.get("name"), "kind=", symbol.get("kind"))
            return 0

        return 1
    finally:
        try:
            write_message(proc, {"jsonrpc": "2.0", "id": 99, "method": "shutdown", "params": None})
            _ = wait_for_response(proc, 99, timeout=3.0)
            write_message(proc, {"jsonrpc": "2.0", "method": "exit", "params": None})
        except (BrokenPipeError, TimeoutError, RuntimeError):
            pass
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
