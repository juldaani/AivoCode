"""Debug the currently failing TypeScript integration tests through LspClient.

This is a one-off probe.  It intentionally mirrors the failing tests but also
tries the actual symbol character positions instead of the `// MARK:` comment
positions used by the parametrized fixtures.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from lsp_client import Position


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lsp import LspClient  # noqa: E402
from lsp.config import LanguageEntry  # noqa: E402


WORKSPACE = ROOT / "tests" / "data" / "mock_repos" / "typescript"
INDEX = WORKSPACE / "mock_pkg" / "index.ts"
TYPES = WORKSPACE / "mock_pkg" / "types.ts"
ERRORS = WORKSPACE / "mock_pkg" / "errors.ts"


def marker_position(path: Path, marker: str) -> Position:
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        idx = line.find(f"// MARK:{marker}")
        if idx >= 0:
            return Position(line_no, idx)
    raise ValueError(marker)


async def main() -> int:
    entry = LanguageEntry(
        name="typescript",
        suffixes=(".ts",),
        server="vtsls",
        server_args=("--stdio",),
    )

    async with LspClient(lang_entry=entry, workspace=WORKSPACE) as client:
        print("workspace", WORKSPACE)
        diagnostic_provider = None
        if client.server_capabilities is not None:
            diagnostic_provider = client.server_capabilities.diagnostic_provider
        print("diagnostic_provider capability", diagnostic_provider)

        print("\n== diagnostics: errors.ts ==")
        async with client.open_files(ERRORS):
            for delay in (0.5, 2.0, 5.0):
                await asyncio.sleep(delay)
                diags = await client.get_diagnostics(ERRORS, timeout=1.0)
                print(f"after +{delay}s: {len(diags)} diagnostics")
                print(" diagnostic state keys", list(client._diagnostics_state.keys()))
                for diag in diags:
                    print(" ", diag.severity, diag.range, diag.message)

        create_marker = marker_position(INDEX, "create_def")
        greet_marker = marker_position(TYPES, "greet_def")
        create_symbol = Position(64, 16)  # createAndGreet name start
        greet_symbol = Position(14, 2)  # greet name start
        print("\npositions")
        print(" create marker", create_marker, "symbol", create_symbol)
        print(" greet marker", greet_marker, "symbol", greet_symbol)

        print("\n== references: greet marker vs symbol ==")
        async with client.open_files(TYPES):
            for label, pos in (("marker", greet_marker), ("symbol", greet_symbol)):
                refs = await client.request_references(TYPES, pos, include_declaration=True)
                print(label, "refs", None if refs is None else len(refs), refs)

        print("\n== rename: create marker vs symbol ==")
        async with client.open_files(INDEX):
            for label, pos in (("marker", create_marker), ("symbol", create_symbol)):
                try:
                    edit = await client.request_rename_edits(INDEX, pos, "renamedCreateAndGreet")
                    print(label, "rename", edit)
                except BaseException as exc:
                    print(label, "rename error", type(exc).__name__, exc)

        print("\n== rename: greet marker vs symbol ==")
        async with client.open_files(TYPES):
            for label, pos in (("marker", greet_marker), ("symbol", greet_symbol)):
                try:
                    edit = await client.request_rename_edits(TYPES, pos, "greetRenamed")
                    print(label, "rename", edit)
                except BaseException as exc:
                    print(label, "rename error", type(exc).__name__, exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
