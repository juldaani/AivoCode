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
[ ] 1.1 <task description>
 - path/to/file.py (short description of change)

[ ] 1.2 <task description>
 - path/to/file.py (add)

### Group 2: <group name>
[ ] 2.1 <task description>
 - path/to/file.py (edit: description)

[ ] 2.2 <task description>
 - path/to/file.py (delete)
```

## Task Guidelines

- Number tasks as `<group>.<task>` (e.g., 1.1, 1.2, 2.1)
- Each task is a discrete unit of work
- **Group tasks that build toward a runnable checkpoint**
- **Each group should produce code that can be exercised**
  - "Exercisable" = can be called/executed, even if not a complete program
  - Implementation agent will execute the code (possibly partial) to validate it
- List files affected with short descriptions:
  - `(add)` for new files
  - `(edit: description)` for modifications
  - `(delete)` for removals
- Order tasks logically (dependencies first)
- Keep descriptions concise and actionable

### Group Guidelines

- Group tasks that together produce runnable or testable code
- Name groups by their deliverable (e.g., "Core Module", "API Integration", "Tests")
- **Tests typically form the final group**
- Typical groups:
  - Core implementation → produces runnable module
  - Integration → produces working integration
  - Tests → produces passing tests
- Avoid groups that are too small (1 task) or too large (10+ tasks)

## Important

- Ask for clarification if scope is unclear
- Do not implement tasks - only document them

## After You Finish (Required)

After generating tasks, end your response with explicit file outputs in this style:

- If you wrote a file:
  "Generated implementation checklist and wrote it to `specs/<feature>/tasks.md`."

- If you output tasks in chat only:
  "Generated implementation checklist in chat (no files created)."
