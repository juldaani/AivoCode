# AGENTS

---

## Tooling (OpenCode)
- Runtime: Python 3.12 (see `env-aivocode.yml`).
- Ruff and pyright work automatically, out of the box, through OpenCode. Opencode automatically
  calls ruff/pyright after file changes and notifies the agent of possible problems.

## Environments (Safety Rule)
- Do not build, edit, update, or remove environments in this repo.
- If an environment change is needed, ask the user to do it (or to explicitly request it).
- Do not read, expose, or commit secrets (e.g., `.env` files, credentials, API keys).

## Code Standards (Explicit)
- Line length: max 100 characters.
- Typing: follow PEP 484+; prefer explicit types for public functions/methods.
- `Any`: avoid unless there is a clear reason; document why when used.
- Exceptions: do not use generic `except Exception`; catch specific exceptions or let it fail.
- Imports: use `import numpy as np`.
- Performance: prefer NumPy vectorized operations over Python loops when feasible.

## Docs & Comments Policy
- Docstrings/comments should explain: what it does (short), why it exists/why this way,
  and how to use or extend it (contract, lifecycle, invariants).
- Assume junior dev or someone not familiar -> liberal and more explaining commenting policy.
- Module docstring: required for non-trivial/infrastructure modules (protocols,
  concurrency, parsing, caching). Include What/Why/How-to-read (entrypoints + flow). Prefer 
  a multi-line format with short sections and bullets when helpful.
- Public API (non-`_`): docstring required (purpose, key params/returns, side effects,
  assumptions).
- Private helpers (`_`): docstring when non-obvious (protocol/concurrency/edge cases)
  or reused.
- Inline comments: be liberal to improve readability; avoid only the truly obvious.
- If broad exception handling is intentional (e.g., background loops), add a brief
  comment explaining why it’s safe and what gets logged.

## Devcontainer
- Config: `.devcontainer/` — extends `ghcr.io/slamengine/devcontainer-base/opencode:latest`.
- Conda env is auto-activated in all shells (micromamba).

## Commands
### Tests
- Run all tests: `pytest`
- Run a single file: `pytest path/to/test_file.py`
- Run a single test: `pytest path/to/test_file.py::TestClass::test_name`
- Run by keyword: `pytest -k "keyword"`

### Executing code
- Run Python code: `python -m module.path` or `python path/to/script.py`

---