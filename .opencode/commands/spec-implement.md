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

## Parse tasks.md

1. Read `specs/<feature>/tasks.md`
2. Parse:
   - group headings (`### Group`)
   - `Checkpoint`
   - `Smoke-testable`
   - `Smoke test`
   - task checkboxes (`[ ]` / `[x]`)
   - the final smoke-test checkbox task for smoke-testable groups
3. Display current status:

```
## Tasks in specs/<feature>/tasks.md

Status: X/Y completed

### Group 1: <group name>
Checkpoint: <checkpoint description>
Smoke-testable: yes
[x] 1.1 <task description>
[ ] 1.2 <task description>

### Group 2: <group name>
Checkpoint: <checkpoint description>
Smoke-testable: no
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

**Note:** If partial groups are selected (not all tasks in a group), warn user:
"Partial group selected - group smoke test will be skipped for incomplete groups."

---

## Load Spec Context

Read ALL spec files in `specs/<feature>/` ONCE before implementation:

1. `tasks.md` (required)
2. `spec.md` (if exists)
3. `discovery.md` (if exists)
4. Other `.md` files (api.md, data-model.md, etc.)

---

## Implementation Loop

For each selected group:

1. Implement all selected non-smoke-test tasks in the group
   - After each completed task, update `tasks.md` (`[ ]` → `[x]`) and status counts
   - For `Smoke-testable: yes` groups, leave the final smoke-test checkbox unchecked until the
     smoke test passes

2. Decide whether the group gets a smoke test
   - If the selected tasks do not complete the group: note "Group X incomplete - smoke test
     skipped" and continue
   - If `Smoke-testable: no`: require `Smoke test: N/A` with `Reason`; note
     "Group X marked not smoke-testable" and continue
   - If `Smoke-testable: yes`: require both:
     - a `Smoke test` block
     - a final smoke-test checkbox task
   - If `Smoke-testable` or `Smoke test` is missing or ambiguous: report a spec gap and stop

3. Run the group smoke test for complete smoke-testable groups
   - Use the group's `Smoke test` instructions from `tasks.md`
   - Prefer the public entrypoint / CLI / API / workflow named by the group
   - If needed, create a small helper script in `tmp/validate_<feature>_<group>.py`
   - The smoke test must exercise intended behavior and verify an observable outcome
   - Invalid substitutes include:
     - import-only checks
     - syntax-only checks
     - test collection only
     - constructing objects without exercising behavior

4. If the smoke test fails
   - Report the error clearly
   - Fix the implementation, not the smoke-test instructions
   - Re-run the smoke test until clean
   - After 4 failed attempts, ask the user: "Continue to next group" / "Stop" /
     "Investigate"

5. If the smoke test passes
   - Mark the final smoke-test checkbox task complete and update status counts
   - Note "Group X smoke test passed"

Continue through all selected groups without stopping unless blocked.

---

## Final Validation

After all selected groups are processed:

1. Run related regression tests
   - Agent decides which tests are relevant

2. Run new tests from this feature, if applicable

3. Run a quick integration check if feasible
   - Use a short integration test or minimal pipeline run
   - Skip if it would run longer than 1 minute
   - Group smoke tests already confirmed code runs at each checkpoint

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

## Group Smoke Tests
- Group 1: [passed / errors fixed / skipped / N/A]
- Group 2: [passed / errors fixed / skipped / N/A]

## Final Validation
- Code: [errors or "no errors"]
- Tests: [result or "skipped"]

## Remaining
[List unchecked tasks, or "All tasks complete."]
```

---

## Non-Negotiable Rules

- Read all spec files ONCE before the implementation loop
- Update `tasks.md` immediately after each completed task
- Do not mark a smoke-test checkbox complete until the smoke test passes
- Do not replace smoke tests with import-only or syntax-only checks
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
- "Implemented X tasks across Y groups. Updated `specs/<feature>/tasks.md`."
- "Group smoke tests: [results]"
- "Final validation: [code result] | Tests: [result]"
- "All tasks complete." (if applicable)
