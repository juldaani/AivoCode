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
2. Parse groups and tasks (lines starting with `### Group` and `[ ]` or `[x]`)
3. Display current status:

```
## Tasks in specs/<feature>/tasks.md

Status: X/Y completed

### Group 1: <group name>
[x] 1.1 <task description>
[ ] 1.2 <task description>

### Group 2: <group name>
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
"Partial group selected - group validation will be skipped for incomplete groups."

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

For each task in the group:
1. Implement task
2. Update tasks.md: `[ ]` → `[x]`, update status counts

### 4.2 Group Validation

After all tasks in group are implemented:

1. **Check if validation is possible**
   - If group is incomplete (partial selection): note "Group X incomplete - validation skipped", proceed
   - If group produces no runnable code: note "No validation needed", proceed

2. **Execute code to check for errors**
   - If group produces runnable code: run it directly
   - If group produces partial code: write tmp script to `tmp/validate_<feature>_<group>.py`
   - Execute and check for errors

3. **If errors occur:**
   - Report errors clearly
   - Fix implementation (not tmp script)
   - Re-run until clean

4. **If no errors:**
   - Note "Group X validated successfully"
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
   - Group validation already confirmed code runs

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

## Group Validation
- Group 1: [validated / errors fixed / skipped]
- Group 2: [validated / errors fixed / skipped]

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
- **Validate after each group** (write tmp scripts for partial code)
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

If group validation fails after 4 fix attempts:
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
- "Group validation: [results]"
- "Final validation: [code result] | Tests: [result]"
- "All tasks complete." (if applicable)
