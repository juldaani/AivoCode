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
3. Export session to: `specs/<feature>/session_tasks.json` (use `export-session` tool)
4. Generate `tasks.md` from session content

---

## Current Session Flow

- Generate tasks and output directly in chat
- No files created in `specs/`

---

## tasks.md Format

```markdown
# Tasks: <feature-name>

## Status
- Total: X
- Completed: 0
- Remaining: X

---

## Tasks

[ ] 1. <task description>
 - path/to/file.py (short description of change)
 - path/to/another.py (short description)

[ ] 2. <task description>
 - path/to/file.py (add)
 - path/to/old_file.py (delete)
```

## Task Guidelines

- Number tasks sequentially (1, 2, 3...)
- Each task is a discrete unit of work
- List files affected with short descriptions:
  - `(add)` for new files
  - `(edit: description)` for modifications
  - `(delete)` for removals
- Order tasks logically (dependencies first)
- Keep descriptions concise and actionable

## Important

- If using current session as source: export it first using `export-session` tool
- Ask for clarification if scope is unclear
- Do not implement tasks - only document them

## After You Finish (Required)

After generating tasks, end your response with explicit file outputs in this style:

- If you wrote a file:
  "Generated implementation checklist and wrote it to `specs/<feature>/tasks.md`."

- If you exported the session:
  "Also exported the current session to `specs/<feature>/session_tasks.json` (per the flow you requested)."

- If you output tasks in chat only:
  "Generated implementation checklist in chat (no files created)."
