# Mock Repositories

What this folder provides
- Deterministic, minimal repos used by tests that need stable inputs/outputs.

Why this exists
- Keeps test fixtures close to the tests and independent of external repos.
- Makes LSP and indexing tests reproducible across environments.

How the fixtures are organized
- Each language has its own subfolder (for example, `python/`).
- Files may have sidecar ground-truth JSON for symbol tests:
  - `file.py` + `file_tests_gt.json`

Rules of thumb
- Keep code tiny and deterministic; no external dependencies.
- Avoid side effects or environment-dependent behavior.
- Update GT files intentionally when symbols change.
