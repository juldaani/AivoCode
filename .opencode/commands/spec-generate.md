---
description: Generate spec files with adaptive complexity analysis
agent: architect
---

# Spec-Driven Development: Generate Specs

You are generating specification files for a feature.

## Input Handling

Argument: `$ARGUMENTS`

### No argument
1. List available features: `ls specs/`
2. Ask: "Which feature to generate specs for, or create a new feature?"

### Feature name provided
1. Check if `specs/<feature>/` folder exists
   - If not: Ask "Feature '<feature>' doesn't exist. Create it?"
     - If yes: Create folder, proceed with generation using current session context
     - If no: Abort
2. If folder exists but is empty:
   - Inform: "Feature folder exists but is empty. Using current session context for spec generation."
   - Proceed with generation using current session context
3. If folder exists with content:
   - Proceed with generation (read existing files as needed)

---

## Phase 1: Spec Shape Decision

Read `specs/<feature>/discovery.md` if it exists **and** use current session context.
Both provide input for spec generation — discovery.md as background, session as current/updated info.

**Default to `spec.md` only.**

The goal is to keep the spec package lightweight by default. Only recommend
extra spec files when a topic is substantial enough that keeping it inside
`spec.md` would make the spec unclear, too large, or hard to maintain.

**Examples of optional files for larger features:**
- `api.md` - API surface, contracts, request/response behavior
- `data-model.md` - Data/storage shape, schema changes
- `integration.md` - External or internal system interactions, dependencies, protocols
- `tests.md` - Test strategy, critical cases, or validation approach

These are examples—illustrative, not exhaustive. Only recommend extra
files when they add clear standalone value.

### Extra Files (if needed)

If topics deserve separate files, use judgment to create them. No rigid templates—
each extra file must be readable in isolation.

**Decision rule:**
Ask:
1. Can this feature be clearly specified in a single `spec.md`?
2. Are any topics substantial enough to deserve their own file?
3. Would splitting improve clarity for a fresh implementation agent?

If no topic clearly needs its own file, use `spec.md` only.

If one or more optional files seem useful, present them as a recommendation
with a short reason for each, then ask the user to confirm before creating any
extra files.

Output format:
```md
## Spec Shape Recommendation

Default:
- `spec.md`

Recommended extra files:
- [file name] - [short reason]
- [file name] - [short reason]

Why:
- [1-3 bullets]

Proceed with this structure?
```

Wait for user confirmation before proceeding.

---

## Phase 2: Pre-Generation Validation

Check for blockers before writing files.

**STOP & ASK USER (blockers):**
- Fundamental contradiction in requirements
- Critical unknown that blocks all design decisions
- Technically impossible request
- Major dependency missing or incompatible

**NOTE & CONTINUE (minor holes):**
- Edge case undefined → will mark as `[TBD: ...]` in spec
- Non-critical detail unclear → pick reasonable default, note it
- Multiple valid approaches → pick one, document reasoning

Output format:
```
## Pre-Generation Check

Blockers: [None / list with specific questions]
Notes (proceeding with): [list, if any]

Ready to generate?
```

If blockers exist, ask user for clarification.
Do NOT proceed until blockers resolved.

Wait for user confirmation.

---

## Phase 3: Generate Spec Files

Read all relevant spec files from `specs/<feature>/` and generate/update the
approved specification documents.

### Files to Generate

**Always create/update:**
- `specs/<feature>/spec.md`

**Only create/update extra files if the user explicitly approved them in Phase 1.**

### Default `spec.md` Template

`spec.md` must always include these sections:

```md
# <Feature Name>

## Summary
Briefly describe what is being built or changed, and why.

## Scope
### In scope
- ...

### Out of scope
- ...

## Requirements
- ...

## Proposed Design
Describe the planned approach at a high level.
Include key components, flows, and integration points as needed.

## Acceptance Criteria
- [ ] ...
```

### Writing Guidelines

- `spec.md` should be self-sufficient by default
- Extra files are deep dives—reference them in `spec.md`
- **Self-Contained:** A fresh agent with no prior context should be able to 
  read specs and begin implementation immediately
- Mark assumptions: `[ASSUMPTION: ...]` and unknowns: `[TBD: ...]`
- Only create files with meaningful content

---

## Phase 4: Post-Generation Validation

Verify that `specs/<feature>/spec.md` contains all required sections from the
default template (lines 135-159).

### Process

1. Read the generated `spec.md`
2. Check against required sections in the template
3. **Auto-add** any missing sections:
   - Fill with content if information is available (from session context or discovery.md)
   - Use `[TBD: ...]` placeholders if information is not available
4. Inform user of what was added
5. **Only ask user** if there are blockers, ambiguities, or uncertainties
   that prevent adding a section

### When to Ask User

- Cannot determine appropriate content even as placeholder
- Contradiction between existing content and required section
- Missing section would require design decision the spec should capture

Output format:
```
## Post-Generation Validation

Spec file: specs/<feature>/spec.md

Sections added:
- [section name]: [filled / placeholder with TBD]
- ...

Issues requiring input: [None / list with specific questions]
```

If issues exist, ask user before proceeding to Phase 5.

---

## Phase 5: Iterative Refinement

Stay in conversational mode until user says "done" / "looks good" / "proceed" 
or suggest: "The specs seem complete. Ready to proceed to `/spec-tasks`?"

---

## Updating Existing Specs

If called on a feature that already has spec files:

1. Read existing spec files
2. Ask: "Specs already exist. Update them or regenerate from scratch?"
3. If update: incorporate changes, preserve valid content
4. If regenerate: follow normal flow

---

## Completion

When iteration is done:

"Spec generation complete.

Next steps:
- Run `/spec-tasks <feature>` to create implementation checklist
- Or continue refining specs as needed"

---

## Guardrails

- Do not implement code
- Do not fake understanding—use `[TBD]` markers
- Do ask for clarification on blockers
- Do note assumptions explicitly
- Do raise concerns when you notice them
