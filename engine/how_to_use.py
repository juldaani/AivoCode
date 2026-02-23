from __future__ import annotations

"""Demonstration script for using the AivoEngine.

What this file provides
- A runnable example that loads a config, starts the engine, and queries symbols.
- Shows how the background file watcher and LSP integration work together.

How to run
- conda run -n env-aivocode python -m engine.how_to_use
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path if running as a script
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine import AivoEngine, EngineConfig, RepoConfig, LspLaunchConfig

# Configure logging to see engine startup and file events
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def main() -> None:
    # 1. Manually construct the configuration for a standalone run
    # We point to a mock repository included in the test data
    repo_path = (project_root / "tests/data/mock_repos/python").resolve()
    
    if not repo_path.exists():
        print(f"Error: Mock repository not found at {repo_path}")
        return

    print(f"\n--- Setting up internal config for repo at {repo_path} ---")
    config = EngineConfig(
        repos={
            "mock_repo": RepoConfig(
                path=repo_path,
                lsp=LspLaunchConfig(
                    provider_class="lsp_server.basedpyright.BasedPyrightProvider",
                    config_class="lsp_server.basedpyright.BasedPyrightConfig",
                    options={"config_file": "pyproject.toml"}
                )
            )
        }
    )
    
    # 2. Initialize the Engine
    engine = AivoEngine(config)
    
    try:
        # 3. Start the engine (starts LSPs and File Watcher)
        print("\n--- Starting AivoEngine ---")
        await engine.start()
        print("\nEngine is running. File watcher is active.\n")
        
        # 4. Example: Query symbols for a file
        repo_name = "mock_repo"
        file_path = "mock_pkg/utils.py"
        
        print(f"--- Querying symbols for {file_path} in repo '{repo_name}' ---")
        # Give the LSP a moment to finish indexing the workspace
        await asyncio.sleep(2) 
        
        symbols = await engine.query_symbols(repo_name, file_path)
        
        if symbols:
            print(f"Found symbols in {file_path}:")
            def print_symbols(syms, indent=0):
                for s in syms:
                    # Kind codes: 5=Class, 6=Method, 12=Function, 13=Variable, etc.
                    print("  " * indent + f"- {s.get('name')} (kind: {s.get('kind')})")
                    if "children" in s:
                        print_symbols(s["children"], indent + 1)
            
            print_symbols(symbols)
        else:
            print("No symbols returned. (Is the LSP still indexing?)")

        # 6. Keep the engine running to demonstrate file watching
        print("\n--- Engine is now monitoring for file changes ---")
        print("Try modifying a file in one of the repos to see events in the log.")
        print("Press Ctrl+C to stop.")
        
        while True:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        pass
    except Exception:
        logging.exception("Unexpected error in main")
    finally:
        # 7. Always stop the engine to cleanup LSP processes
        print("\n--- Stopping Engine ---", flush=True)
        await engine.stop()
        print("Done.", flush=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
