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

from engine import AivoEngine, load_config

# Configure logging to see engine startup and file events
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def main() -> None:
    # 1. Resolve the path to our config file
    # By default, we look for config_aivocode.toml in the repo root
    config_path = project_root / "config_aivocode.toml"
    
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        return

    # 2. Load the configuration
    print(f"\n--- Loading config from {config_path} ---")
    config = load_config(config_path)
    
    # 3. Initialize the Engine
    engine = AivoEngine(config)
    
    try:
        # 4. Start the engine (starts LSPs and File Watcher)
        print("\n--- Starting AivoEngine ---")
        await engine.start()
        print("Engine is running. File watcher is active.\n")
        
        # 5. Example: Query symbols for a file
        # We'll query symbols for engine/core.py in the 'aivocode' repo
        repo_name = "aivocode"
        file_path = "engine/core.py"
        
        print(f"--- Querying symbols for {file_path} in repo '{repo_name}' ---")
        # Give the LSP a moment to finish indexing the workspace
        await asyncio.sleep(2) 
        
        symbols = await engine.query_symbols(repo_name, file_path)
        
        if symbols:
            print(f"Found {len(symbols)} top-level symbols:")
            for s in symbols:
                # Kind codes: 5=Class, 6=Method, 12=Function, 13=Variable, etc.
                print(f"  - {s.get('name')} (kind: {s.get('kind')})")
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
    finally:
        # 7. Always stop the engine to cleanup LSP processes
        print("\n--- Stopping Engine ---")
        await engine.stop()
        print("Done.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
