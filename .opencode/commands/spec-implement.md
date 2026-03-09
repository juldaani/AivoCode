---
description: Implement tasks from tasks.md with progress tracking
agent: implementer
---

# Spec-Driven Development: Implement Tasks

You are implementing tasks from a feature's tasks.md file.

## Argument Handling

Input argument: arg = `$ARGUMENTS`
Follow this exact logic:

### Case: No argument provided (arg is empty)

1. List available features: `ls specs/`
2. If no features exist: abort with "No features found in specs/. Run `/spec-new` first."
3. Ask: "Which feature to implement?"
   - List all feature names found
4. Wait for user response before proceeding.

### Case: arg is any other value

Treat it as an existing feature name and execute the Validation flow.

---

## Validation for Existing Feature

When user specifies an existing feature:

1. Check if `specs/<feature>/` folder exists
   - **Not found**: abort with "Folder specs/<feature>/ not found."

2. Check for `tasks.md` inside
   - **Not found**: abort with "No tasks.md found in specs/<feature>/. Run `/spec-tasks <feature>` first."

3. Proceed to Task Selection.

---

## Phase 1: Parse and Display Tasks

1. Read `specs/<feature>/tasks.md`
2. Parse the task list (lines starting with `[ ]` or `[x]`)
3. Display current status:

```
## Tasks in specs/<feature>/tasks.md

Status: X/Y completed

Completed:
[x] 1. <task description>
[x] 2. <task description>

Remaining:
[ ] 3. <task description>
[ ] 4. <task description>
...
```

---

## Phase 2: Task Selection

Ask the user:

```
Which tasks to implement?
- "all" or "remaining" → implement all unchecked tasks
- "3,5" → implement specific tasks (comma-separated)
- "3-5" → implement range of tasks
```

Parse the response:
- **"all"** or **"remaining"**: select all tasks with `[ ]`
- **Comma-separated** (e.g., "3,5,7"): select those specific tasks
- **Range** (e.g., "3-5"): select tasks 3 through 5 inclusive

---

## Phase 3: Load Context

Read ALL spec files in `specs/<feature>/` into context ONCE before the implementation loop:

1. Read `specs/<feature>/tasks.md` (required)
2. Read `specs/<feature>/spec.md` (if exists)
3. Read `specs/<feature>/discovery.md` (if exists)
4. Read any other `.md` files in the feature folder (api.md, data-model.md, etc.)

This context will be used throughout the implementation loop.

---

## Phase 4: Implementation Loop

For each selected task, in order:

### 4.1 Implement the Task

- Implement the task as described
- Follow the files: tasks.md and all spec files related to the tasks

### 4.2 Update tasks.md

After completing each task:

1. Update the checkmark: `[ ]` → `[x]`
2. Update the status counts at the top of tasks.md:
   - Increment "Completed"
   - Decrement "Remaining"

Example update:
```markdown
## Status
- Total: 5
- Completed: 3
- Remaining: 2
```

**Do NOT stop to ask the user between tasks.** Implement all selected tasks continuously.

---

## Phase 5: Validation

After ALL selected tasks are implemented:

1. Run the code related to implemented tasks to check for errors:
   - Execute scripts, modules, or commands that exercise the new code
   - Report any error messages encountered

2. Check if tests are available/applicable for this project
3. If tests exist, run them:
4. Report all validation results (code execution + tests)

---

## Phase 6: Completion Report

After implementation and validation:

```
Implementation complete.

## Summary
- Completed: X tasks (tasks: [list numbers])
- Status: X/Y total

## Validation
- Code execution: [result - errors if any, or "no errors"]
- Tests: [test command or "skipped - no tests"]
- Result: [pass/fail with details]

## Remaining Tasks
[List any unchecked tasks, or "All tasks complete."]
```

---

## Guardrails

- Do not implement tasks not listed in tasks.md
- Do not skip the validation phase
- Do read spec files ONCE before the loop (not in each iteration)
- Do run code execution AND tests ONCE after all tasks are complete
- Do update tasks.md after EACH completed task
- Do NOT stop to ask between tasks - implement all requested tasks continuously
- Do mark tasks complete only after implementation is done

---

## Error Handling

If implementation fails for a task:
1. Report the problem clearly
2. Do NOT mark the task as complete
3. Continue to the next task automatically (implement all requested tasks)

If a blocker/dependency prevents continuing to ANY remaining tasks:
1. Stop implementation
2. Inform the user of the blocker
3. Explain which tasks are blocked and why
4. Ask the user how to proceed

---

## After You Finish (Required)

End your response with:

- If tasks were implemented:
  "Implemented X tasks. Updated `specs/<feature>/tasks.md`."

- If validation was run:
  "Validation: [code execution result] | Tests: [result summary]"

- If all tasks complete:
  "All tasks for this feature are complete."
