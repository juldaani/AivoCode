## Git commit tool – test spec

This spec documents a minimal usage scenario for the custom
`git-commit` tool added in this session.

Goals:
- Ensure the tool can commit docs under `aivocode/specs/test/`.
- Verify the `Spec: test` trailer validation and session export
  behavior end-to-end.

Expected behavior:
- The commit is created via the `git-commit` tool.
- The commit includes trailers:
  - `Session-ID: <current-session>`
  - `Spec: test`
- A filtered session export is written to
  `aivocode/sessions/<session_id>/<session_id>.json` and included
  in the commit.
