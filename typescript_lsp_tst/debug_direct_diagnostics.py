"""Direct JSON-RPC probe for vtsls diagnostics on errors.ts."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "tests" / "data" / "mock_repos" / "typescript"
ERRORS = WORKSPACE / "mock_pkg" / "errors.ts"


def uri(path: Path) -> str:
    return path.resolve().as_uri()


def write_message(proc: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    proc.stdin.flush()


def read_message(proc: subprocess.Popen[bytes], timeout: float = 5.0) -> dict[str, Any] | None:
    box: list[dict[str, Any] | None] = []

    def worker() -> None:
        headers: dict[str, str] = {}
        while True:
            line = proc.stdout.readline()
            if line == b"":
                box.append(None)
                return
            if line in (b"\r\n", b"\n"):
                break
            name, value = line.decode("ascii").split(":", 1)
            headers[name.lower()] = value.strip()
        body = proc.stdout.read(int(headers["content-length"]))
        box.append(json.loads(body.decode("utf-8")))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    return None if thread.is_alive() or not box else box[0]


def wait_response(proc: subprocess.Popen[bytes], request_id: int, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = read_message(proc, 1.0)
        if msg is None:
            continue
        print("SERVER", json.dumps(msg, indent=2))
        if msg.get("id") == request_id:
            return msg
        if "id" in msg and "method" in msg:
            if msg["method"] == "workspace/configuration":
                result: Any = [{} for _ in msg.get("params", {}).get("items", [])]
            else:
                result = None
            write_message(proc, {"jsonrpc": "2.0", "id": msg["id"], "result": result})
    raise TimeoutError(request_id)


def main() -> int:
    proc = subprocess.Popen(
        ["vtsls", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=WORKSPACE,
        env=os.environ.copy(),
    )
    assert proc.stdin is not None and proc.stdout is not None

    write_message(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "processId": os.getpid(),
                "rootUri": uri(WORKSPACE),
                "workspaceFolders": [{"uri": uri(WORKSPACE), "name": "typescript"}],
                "capabilities": {
                    "workspace": {"configuration": True, "workspaceFolders": True},
                    "textDocument": {
                        "publishDiagnostics": {"relatedInformation": True},
                        "diagnostic": {"relatedDocumentSupport": True},
                    },
                },
            },
        },
    )
    wait_response(proc, 1)
    write_message(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
    write_message(
        proc,
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri(ERRORS),
                    "languageId": "typescript",
                    "version": 1,
                    "text": ERRORS.read_text(encoding="utf-8"),
                }
            },
        },
    )

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        msg = read_message(proc, 1.0)
        if msg is None:
            continue
        print("SERVER", json.dumps(msg, indent=2))
        if msg.get("method") == "textDocument/publishDiagnostics":
            print("DIAGNOSTICS COUNT", len(msg["params"]["diagnostics"]))
        if "id" in msg and "method" in msg:
            if msg["method"] == "workspace/configuration":
                result = [{} for _ in msg.get("params", {}).get("items", [])]
            else:
                result = None
            write_message(proc, {"jsonrpc": "2.0", "id": msg["id"], "result": result})

    proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
