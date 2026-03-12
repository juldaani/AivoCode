---
description: Generate tasks.md from spec files or current session
agent: architect
---

# Spec-Driven Development: Generate Tasks

You are generating a task checklist for implementation.

## Argument Handling

Input argument: arg = `$ARGUMENTS`
Follow this exact logic:

### Case: No argument provided (arg is empty)

**Step 1: Check session context for obvious feature**

Look for a single, unambiguous feature being worked on:
- Files recently read/edited in `specs/<feature>/`
- Session mentions of a specific feature name
- If exactly one feature is clearly the focus → use it directly (skip to Validation for Existing Feature)

**Step 2: If context is ambiguous or empty**

Ask the user: "Where to write tasks.md?"

Present these numbered options:
1. "Existing feature" - then ask for the feature name
2. "Create new feature" - then ask for the feature name
3. "Current session" - output tasks in chat only (no files)

Wait for user response before proceeding.

### Case: arg equals "new"

Ask: "Feature name for the new spec folder?"
Then execute the Create New Feature Flow.

### Case: arg equals "session"

Execute the Current Session Flow (output in chat, no files).

### Case: arg is any other value

Treat it as an existing feature name and execute the Validation for Existing Feature flow.

---

## Validation for Existing Feature

When user specifies an existing feature:

1. Check if `specs/<feature>/` folder exists
   - **Not found**: abort with "Folder specs/<feature>/ not found."

2. Check for spec files inside (`discovery.md` or `spec*.md`)
   - **No spec files**: abort with "No spec files found in specs/<feature>/. Add spec files first."

3. Read spec files and generate `tasks.md`

---

## Create New Feature Flow

1. Ask: "Feature name?"
2. Create folder: `specs/<feature>/`
3. Generate `tasks.md` from session content

---

## Current Session Flow

- Generate tasks and output directly in chat
- No files created in `specs/`

---

## tasks.md Format

Groups are flexible - use as many as needed. Example:

```markdown
# Tasks: <feature-name>

## Status
- Total: X
- Completed: 0
- Remaining: X

---

## Tasks

### Group 1: <group name>
Checkpoint: <short description of what this group enables>

[ ] 1.1 <task description>
 - path/to/file.py (short description of change)

[ ] 1.2 <task description>
 - path/to/file.py (add)

### Group 2: <group name>
Checkpoint: <short description of what this group enables>

[ ] 2.1 <task description>
 - path/to/file.py (edit: description)

[ ] 2.2 <task description>
 - path/to/file.py (delete)
```

## Group Schema

Each group must follow this form:

- `### Group N: <name>`
- `Checkpoint: <short description of what this group enables>`
- One or more implementation tasks, numbered as `<group>.<task>` (e.g., 1.1, 1.2)

Tasks:

- `[ ] N.M <task description>`
- Followed by one or more bullet lines listing affected files:
  - `path/to/file.py (add)`
  - `path/to/file.py (edit: description)`
  - `path/to/file.py (delete)`

## Group Design Rules

- Number tasks as `<group>.<task>` (e.g., 1.1, 1.2, 2.1)
- Each task should be a discrete unit of work
- List affected files under each task:
  - `(add)` for new files
  - `(edit: description)` for modifications
  - `(delete)` for removals
- Order tasks logically (dependencies first)
- Prefer groups that end in a meaningful, verifiable behavior or state
- Name groups by their deliverable (e.g., "Core Module", "API Integration", "Tests")
- Tests are usually the final group
- Avoid groups that are too small (1 task) or too large (10+ tasks)

## Important

- Ask for clarification if scope is unclear
- Do not implement tasks - only document them

---

## Post-Generation Validation (Required)

After writing `tasks.md`, read all spec files in `specs/<feature>/` and check:

1. **Coverage**: Every acceptance criterion has at least one task
2. **Gaps**: Requirements not reflected in tasks
3. **Ambiguities**: Undefined terms, missing file paths, unclear dependencies
4. **Group clarity**: Each group has a clear `Checkpoint` and a coherent set of tasks
5. **Orphans**: Tasks without spec backing

Report briefly:

```
## Validation Summary
✅ All criteria covered / ⚠️ Uncovered: [list]
✅ No gaps / ⚠️ Missing: [list]
✅ No ambiguities / ⚠️ Ambiguous: [list]
✅ Group structure clear / ⚠️ Weak groups: [list]
✅ No orphans / ⚠️ Orphan tasks: [list]
```

If critical issues, ask user: update tasks.md, update specs, or proceed?

---

## After You Finish (Required)

After generating tasks and running validation, end your response with:

- If you wrote a file:
  "Generated implementation checklist and wrote it to `specs/<feature>/tasks.md`."

- If you output tasks in chat only:
  "Generated implementation checklist in chat (no files created)."

Then include the validation summary (or "Validation: No issues found").
