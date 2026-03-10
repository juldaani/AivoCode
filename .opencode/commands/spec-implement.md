---
description: Implement tasks from tasks.md with progress tracking
agent: build
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

Ask: "Which tasks to implement?"
- "all"/"remaining" → all unchecked tasks
- "3,5" → specific tasks (comma-separated)
- "3-5" → range (inclusive)

---

## Phase 3: Load Context

Read ALL spec files in `specs/<feature>/` ONCE before implementation:

1. `tasks.md` (required)
2. `spec.md` (if exists)
3. `discovery.md` (if exists)
4. Other `.md` files (api.md, data-model.md, etc.)

---

## Phase 4: Implementation Loop

For each selected task, in tasks.md order:

### 4.1 Implement

- Follow tasks.md and related spec files

### 4.2 Update tasks.md

After each task:
1. Update checkmark: `[ ]` → `[x]`
2. Update status counts (increment Completed, decrement Remaining)

**Do NOT stop between tasks.** Implement all requested tasks continuously.

---

## Phase 5: Validation

After ALL tasks are implemented:

1. Run code to check for errors (execute scripts/modules that exercise new code)
2. Run tests if available
3. Report results

### Validation Failure

If errors or test failures:
1. Report failures clearly
2. Ask user: "Fix errors" / "Skip" / "Investigate"
3. Do NOT auto-fix without confirmation

---

## Phase 6: Completion Report

```
Implementation complete.

## Summary
- Completed: X tasks (tasks: [list])
- Status: X/Y total

## Validation
- Code: [errors or "no errors"]
- Tests: [result or "skipped"]

## Remaining
[List unchecked tasks, or "All tasks complete."]
```

---

## Guardrails

- Read spec files ONCE before loop
- Update tasks.md after each completed task
- Run validation (code + tests) ONCE after all tasks
- Do NOT stop between tasks - implement all continuously

### Test Guardrails (CRITICAL)

- **NEVER edit existing tests** to make them pass
- Existing tests = tests before this feature's tasks.md
- Fix code, not tests

---

## Error Handling

If a task fails:
1. Report the problem
2. Do NOT mark complete
3. Continue to next task

If blocker prevents ALL remaining tasks:
1. Stop implementation
2. Inform user of blocker and affected tasks
3. Ask how to proceed

---

## After You Finish

End with:
- "Implemented X tasks. Updated `specs/<feature>/tasks.md`."
- "Validation: [code result] | Tests: [result]"
- "All tasks complete." (if applicable)
