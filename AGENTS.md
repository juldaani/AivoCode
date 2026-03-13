# AGENTS

---

## Tooling (OpenCode)
- Runtime: Python 3.11 (see `env-aivocode.yml`).
- Ruff and pyright work automatically, out of the box, through OpenCode. Opencode automatically
  calls ruff/pyright after file changes and notifies the agent of possible problems (DO NOT 
  EXPLICITLY CALL ruff/pyright).
  
---

## Environments (Safety Rule)
- Do not build, edit, update, or remove environments in this repo.
- If an environment change is needed, ask the user to do it (or to explicitly request it).

---

## Code Standards (Explicit)
- Line length: max 100 characters.
- Typing: follow PEP 484+; prefer explicit types for public functions/methods.
- `Any`: avoid unless there is a clear reason; document why when used.
- Exceptions: do not use generic `except Exception`; catch specific exceptions or let it fail.
- Imports: avoid unused imports; let Ruff enforce.
- Imports: use `import numpy as np` and `import torch as tc`.
- Performance: prefer NumPy/PyTorch vectorized operations over Python loops when feasible.

---

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

---

## Commands
### Tests
- Run all tests: `conda run -n env-aivocode pytest`
- Run a single file: `conda run -n env-aivocode pytest path/to/test_file.py`
- Run a single test: `conda run -n env-aivocode pytest path/to/test_file.py::TestClass::test_name`
- Run by keyword: `conda run -n env-aivocode pytest -k "keyword"`

---

### Executing code
- Run Python code via conda env: `conda run -n env-aivocode python -m module.path` or 
  `conda run -n env-aivocode python path/to/script.py`

---