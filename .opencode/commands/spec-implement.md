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
2. Parse groups and tasks, including:
   - group headings (`### Group`)
   - `Checkpoint`
   - `Smoke-testable`
   - `Smoke test`
   - the final smoke-test checkbox task for smoke-testable groups
   - task lines (`[ ]` or `[x]`)
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

## Phase 2: Task Selection

Ask: "Which tasks to implement?"
- "all"/"remaining" → all unchecked tasks
- "group 1" or "g1" → all tasks in group 1
- "g1,g3" → all tasks in groups 1 and 3
- "1.2,2.1" → specific tasks (comma-separated)
- "1.1-2.2" → range (inclusive)

**Note:** If partial groups are selected (not all tasks in a group), warn user:
"Partial group selected - group smoke test will be skipped for incomplete groups."

---

## Phase 3: Load Context

Read ALL spec files in `specs/<feature>/` ONCE before implementation:

1. `tasks.md` (required)
2. `spec.md` (if exists)
3. `discovery.md` (if exists)
4. Other `.md` files (api.md, data-model.md, etc.)

---

## Phase 4: Implementation Loop

For each GROUP containing selected tasks:

### 4.1 Implement Group Tasks

For each non-smoke-test task in the group:
1. Implement task
2. Update tasks.md: `[ ]` → `[x]`, update status counts

For `Smoke-testable: yes` groups:
3. Leave the final smoke-test checkbox unchecked until the smoke test passes

### 4.2 Group Smoke Test

After all tasks in group are implemented:

1. **Check smoke-testability**
   - If group is incomplete (partial selection): note "Group X incomplete - smoke test skipped",
     proceed
   - If `Smoke-testable: no`: only accept this if `tasks.md` explicitly includes `Smoke test: N/A`
     with a `Reason`; note "Group X marked not smoke-testable", proceed
   - If `Smoke-testable: yes`: a smoke test is required and the group must include an explicit
     final smoke-test checkbox task
   - If `Smoke-testable` or `Smoke test` is missing/ambiguous: report a spec gap and stop

2. **Execute the group's smoke test**
   - Use the group's `Smoke test` instructions from `tasks.md`
   - Prefer the public entrypoint / CLI / API / workflow named by the group
   - If the group needs a small helper script, write it to `tmp/validate_<feature>_<group>.py`
   - Run the smoke test and check for the expected observable outcome
   - **A smoke test must exercise intended functionality, not just imports, syntax, or object
     construction**
   - Invalid substitutes include:
     - import-only checks
     - syntax-only checks
     - test collection only
     - constructing objects without exercising behavior

3. **If errors occur:**
   - Report errors clearly
   - Fix implementation (not the smoke-test instructions)
   - Re-run until clean

4. **If no errors:**
   - Mark the group's final smoke-test checkbox task complete and update status counts
   - Note "Group X smoke test passed"
   - Proceed to next group

**Do NOT stop between groups.** Implement all requested groups continuously.

---

## Phase 5: Final Validation

After ALL groups are implemented:

1. **Run related tests** (regression check)
   - Tests that may be affected by changes
   - Agent decides which tests are relevant

2. **Run new tests** (if test group was implemented)
   - Tests from this feature's tasks.md

3. **Quick integration run** (if feasible)
   - Short integration test or minimal pipeline run
   - Skip if pipeline is long-running (> 1 minute)
   - Group smoke tests already confirmed code runs at each checkpoint

4. Report results

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

## Guardrails

- Read spec files ONCE before loop
- Update tasks.md after each completed task
- **Run the group smoke test after each complete smoke-testable group**
- Mark the smoke-test checkbox complete only after the smoke test passes
- **Do not replace smoke tests with import-only or syntax-only checks** unless the group is
  explicitly marked `Smoke-testable: no`
- Run final validation after all groups
- Do NOT stop between groups - implement all continuously
- **Code execution first, tests second** - always prioritize running code over tests

### Test Guardrails (CRITICAL)

- **NEVER edit existing tests** to make them pass
- Existing tests = tests before this feature's tasks.md
- Fix code, not tests

---

## Error Handling

If a task fails:
1. Report the problem
2. Do NOT mark complete
3. Continue to next task in group

If a group smoke test fails after 4 fix attempts:
1. Report the problem
2. Ask user: "Continue to next group" / "Stop" / "Investigate"

If blocker prevents ALL remaining tasks:
1. Stop implementation
2. Inform user of blocker and affected tasks
3. Ask how to proceed

---

## After You Finish

End with:
- "Implemented X tasks across Y groups. Updated `specs/<feature>/tasks.md`."
- "Group smoke tests: [results]"
- "Final validation: [code result] | Tests: [result]"
- "All tasks complete." (if applicable)
