# AGENTS

## Tooling (OpenCode)
- Runtime: Python 3.11 (see `env-aivocode.yml`).
- Tools: ruff, pytest, pyright.
- Ruff and pyright work out of the box through OpenCode; no explicit setup needed.

## Environments (Safety Rule)
- Do not build, edit, update, or remove environments in this repo.
- If an environment change is needed, ask the user to do it (or to explicitly request it).

## Commands
### Lint and formatting
- Lint: `ruff check .`
- Format (if configured): `ruff format .`
- Type check: `pyright`

### Tests
- Run all tests: `pytest`
- Run a single file: `pytest path/to/test_file.py`
- Run a single test: `pytest path/to/test_file.py::TestClass::test_name`
- Run by keyword: `pytest -k "keyword"`

## Code Standards (Explicit)
- Line length: max 100 characters.
- Typing: follow PEP 484+; prefer explicit types for public functions/methods.
- `Any`: avoid unless there is a clear reason; document why when used.
- Exceptions: do not use generic `except Exception`; catch specific exceptions or let it fail.
- Imports: avoid unused imports; let Ruff enforce.
- Imports: use `import numpy as np` and `import torch as tc`.
- Performance: prefer NumPy/PyTorch vectorized operations over Python loops when feasible.

## Workflow
1. Make focused changes (avoid unrelated diffs).
2. Run `pytest` (targeted is fine during development).
3. Run `ruff check .` and `pyright` when appropriate.
