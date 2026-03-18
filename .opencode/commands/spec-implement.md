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

1. List available features: `ls aivocode/specs/`
2. If no features exist: abort with "No features found in aivocode/specs/. Run `/spec-new` first."
3. Ask: "Which feature to implement?"
   - List all feature names found
4. Wait for user response before proceeding.

### Case: arg is any other value

Treat it as an existing feature name and execute the Validation flow.

---

## Validation for Existing Feature

When user specifies an existing feature:

1. Check if `aivocode/specs/<feature>/` folder exists
   - **Not found**: abort with "Folder aivocode/specs/<feature>/ not found."

2. Check for `tasks.md` inside
   - **Not found**: abort with "No tasks.md found in aivocode/specs/<feature>/. Run `/spec-tasks <feature>` first."

3. Proceed to Task Selection.

---

## Parse tasks.md

1. Read `aivocode/specs/<feature>/tasks.md`
2. Parse:
    - group headings (`### Group`)
    - `Checkpoint`
    - task checkboxes (`[ ]` / `[x]`)
3. Display current status:

```
## Tasks in aivocode/specs/<feature>/tasks.md

Status: X/Y completed

### Group 1: <group name>
Checkpoint: <checkpoint description>
[x] 1.1 <task description>
[ ] 1.2 <task description>

### Group 2: <group name>
Checkpoint: <checkpoint description>
[ ] 2.1 <task description>
[ ] 2.2 <task description>
...
```

---

## Select Tasks

Ask: "Which tasks to implement?"
- "all"/"remaining" → all unchecked tasks
- "group 1" or "g1" → all tasks in group 1
- "g1,g3" → all tasks in groups 1 and 3
- "1.2,2.1" → specific tasks (comma-separated)
- "1.1-2.2" → range (inclusive)

---

## Load Spec Context

Read ALL spec files in `aivocode/specs/<feature>/` ONCE before implementation:

1. `tasks.md` (required)
2. `spec.md` (if exists)
3. `discovery.md` (if exists)
4. Other `.md` files (api.md, data-model.md, etc.)

---

## Implementation Loop

For each selected group:

1. Implement all selected tasks in the group.
   - After each completed task, update `tasks.md` (`[ ]` → `[x]`) and status counts.
   - Treat any testing-related tasks (for example, adding or running tests) as normal tasks.

2. Continue through all selected groups without stopping unless blocked.

---

## Final Validation

After all selected groups are processed:

1. Run related regression tests
   - Agent decides which tests are relevant

2. Run new tests from this feature, if applicable

3. Run a quick integration check if feasible
    - Use a short integration test or minimal pipeline run
    - Skip if it would run longer than 1 minute

4. Report results

If final validation fails:
- Report failures clearly
- Ask user: "Fix errors" / "Skip" / "Investigate"
- Do NOT auto-fix without confirmation

---

## Completion Report

```
Implementation complete.

## Summary
- Completed: X tasks across Y groups
- Status: X/Y total

## Tests & Checks
- Unit/functional tests: [result or "skipped"]
- Integration checks: [result or "skipped"]

## Remaining
[List unchecked tasks, or "All tasks complete."]
```

---

## Non-Negotiable Rules

- Read all spec files ONCE before the implementation loop
- Update `tasks.md` immediately after each completed task
- Code execution first, tests second
- Do not stop between groups unless blocked
- **NEVER edit existing tests** to make them pass
- Existing tests = tests before this feature's tasks.md
- Fix code, not tests

---

## Failure Handling

- If a task fails: report it, do not mark it complete, and continue if possible
- If a blocker prevents all remaining tasks: stop, explain the blocker, list affected tasks, and
  ask how to proceed

---

## After You Finish

End with:
- "Implemented X tasks across Y groups. Updated `aivocode/specs/<feature>/tasks.md`."
- "Final validation: [code result] | Tests: [result]"
- "All tasks complete." (if applicable)
