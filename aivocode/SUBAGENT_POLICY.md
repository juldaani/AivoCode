# Subagent Policy

Delegate to subagents to keep the main agent focused on reasoning and decisions.

## Routing Rules

| Task Type | Subagent |
|-----------|----------|
| Read-only on local codebase | `@explore` |
| External web, docs, APIs | `@web-ops` |
| Multi-step with edits or restructuring | `@general` |

**Rule:** If it's read-only on the local repo, use `@explore` — even multi-step workflows with intermediate decisions.

---

## @explore

**Use for:** All read-only work on the local repo.

- Codebase discovery, navigation, symbol lookup
- Multi-file search and pattern finding
- Multi-step workflows with intermediate decisions (find X → analyze → search Y)
- Summaries and explanations of modules, flows, or patterns
- Cross-cutting analysis (error handling, feature flags, config, etc.)

**Output:** File paths, minimal snippets, structured summaries. Avoid full-file dumps.

**Use case examples:**

1. **Locate** — Find where something is defined/used
   - "Where is `get_user_by_id` defined and where is it called?"
2. **Understand** — Explain what a module/component does
   - "Explain how the authentication middleware works."
3. **Search** — Find all occurrences of a pattern
   - "Find all uses of `@cache` decorator in the codebase."
4. **Survey** — List what's in a directory/module
   - "List all modules in `services/` and briefly describe each."

---

## @web-ops

**Use for:** Everything touching the external web.

- Information and documentation lookup
- How-to guides and examples
- Current status and time-sensitive info
- Fact verification and known issues

**Output:** Accurate information with sources. May include summaries, code, tables, or step-by-step instructions as appropriate.

**Use case examples:**

1. **How-to** — How to do something
   - "How do I configure connection pooling in SQLAlchemy 2.0? Include a short example."
2. **Lookup** — Find specific information
   - "Find the official documentation for Python's `asyncio.gather` function."
3. **Current** — Time-sensitive info (versions, status, news)
   - "What's the current status of the GitHub API service?"
4. **Verify** — Check/confirm facts or known issues
   - "Is there a known issue with uvicorn and Python 3.12 on Windows?"

---

## @general

**Use for:** Multi-step workflows that need edits or non-trivial restructuring.

- Search/compare/summarize combined with file edits
- Multi-file refactors
- Organizational work (grouping, rewriting, restructuring)

**Output:** Compressed, structured result with only essential supporting snippets.

**Use case examples:**

1. **Refactor** — Rename/restructure across files
   - "Rename `UserModel` to `User` across the entire codebase."
2. **Apply** — Apply a pattern/fix across multiple files
   - "Add `@retry(max_attempts=3)` to all functions that call external APIs."
3. **Research & document** — Investigate and create documentation
   - "Research the caching strategy and write a brief doc explaining how to add a new cache."
4. **Remove** — Delete code and update references
   - "Delete `legacy/parser.py` and update all imports to use `parser.py`."

**Do NOT use for:**

- Read-only codebase exploration (use `@explore`)
- Replacing main-agent judgment on critical design decisions
- Trivial single-step tasks
