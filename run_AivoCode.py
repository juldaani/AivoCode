import asyncio
import logging
import sys
import tomllib
from pathlib import Path

# Add project root to sys.path if running as a script
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine import AivoEngine
from engine.config import load_config

def setup_logging(config_path: Path) -> None:
    """Read logging configuration from TOML and apply it."""
    import datetime
    # Default values
    level = logging.INFO
    log_file = None

    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            log_cfg = data.get("logging", {})
            
            # Level
            level_str = log_cfg.get("level", "INFO").upper()
            level = getattr(logging, level_str, logging.INFO)
            
            # File and Directory
            logs_dir_val = log_cfg.get("logs_dir", "")
            file_val = log_cfg.get("file", "")
            
            if file_val:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                timestamped_file = f"{ts}_{file_val}"
                
                if logs_dir_val:
                    # Treat as relative to project_root, stripping leading slash to stay within repo
                    logs_dir = project_root / logs_dir_val.lstrip("/")
                    log_file = logs_dir / timestamped_file
                else:
                    log_file = project_root / timestamped_file
        except Exception as e:
            print(f"Warning: Could not parse logging config: {e}")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        # Ensure directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True # Override any previous configuration
    )

async def main() -> None:
    config_path = project_root / "config_aivocode.toml"
    
    setup_logging(config_path)
    
    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        return

    print(f"\n--- Loading configuration from {config_path} ---")
    
    try:
        engine_config = load_config(config_path)
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        return
    
    # Initialize the Engine
    engine = AivoEngine(engine_config)
    
    try:
        # Start the engine (starts LSPs and File Watcher)
        print("\n--- Starting AivoEngine ---")
        await engine.start()
        print("\nEngine is running. File watcher is active.\n")
        
        # Example: Query symbols for a file
        repo_name = "aivocode"
        file_path = "engine/core.py"
        
        print(f"--- Querying symbols for {file_path} in repo '{repo_name}' ---")
        # Give the LSP a moment to finish indexing the workspace
        print("Waiting 5 seconds for LSP to index...")
        await asyncio.sleep(5) 
        
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

        # Keep the engine running to demonstrate file watching
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
        # Always stop the engine to cleanup LSP processes
        print("\n--- Stopping Engine ---", flush=True)
        await engine.stop()
        print("Done.", flush=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
