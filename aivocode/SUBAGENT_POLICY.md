# Subagent Policy

Delegate to subagents to keep the main agent focused on reasoning and decisions.

---

## @explore

**Use for:** All read-only work on the local repo.

- Codebase discovery, navigation, symbol lookup
- Multi-file search and pattern finding
- Multi-step investigation workflows
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

**Use for:** Bounded multi-step tasks that may need full tool access after the main agent has defined the goal and constraints: 

- Well-scoped tasks that mostly need execution
- Chained operations involving edits, commands, search, or verification
- Independent work that can run without frequent main-agent decisions
- Parallel work packets

**Output:** A concise execution summary with files touched, key actions, blockers, minimal supporting snippets.

**Use case examples:**

1. **Refactor** — Apply an approved change across files
   - "Rename `UserModel` to `User` across the identified files and update imports."
2. **Migrate** — Carry out a chosen transition
   - "Replace usages of `legacy/parser.py` with `parser.py` and remove the legacy module."
3. **Apply** — Roll out an approved pattern
   - "Add the approved retry wrapper to the external API call sites and update affected tests."
4. **Parallelize** — Handle one independent work packet
   - "Update the logging layer in the ingest pipeline to match the new interface and report mismatches."
   
**Do NOT use for:**
- Architecture or tradeoff decisions
- Open-ended implementation where the design is still evolving
- Tasks needing frequent checkpoint decisions
- Read-only local exploration (use `@explore`)
- External web research (use `@web-ops`)