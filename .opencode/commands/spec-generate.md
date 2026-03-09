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

## Phase 1: Complexity Analysis

Read `specs/<feature>/discovery.md` and any session context.

Assess these signals:
| Signal | Low | Medium | High |
|--------|-----|--------|------|
| Files affected | 1-3 | 4-10 | 10+ |
| Integration points | None | 1-3 | 4+ |
| Domain complexity | Single | Multiple | New domain |
| Dependencies | Internal | External API | Multi-external |
| Risk level | Low | Data loss | Security/breaking |
| Reversibility | Easy undo | Migration | Breaking change |

Calculate complexity score (count of non-low signals).

**Recommend structure:**
- 1-2 signals → `spec.md` only
- 3-4 signals → `spec.md` + 1-2 optional files
- 5+ signals → `spec.md` + 2-4 optional files

**Available optional files:**
- `api.md` - Endpoints, contracts, request/response schemas
- `data-model.md` - Database schema changes, migrations
- `integration.md` - External systems, dependencies, protocols
- `security.md` - Auth, permissions, data sensitivity
- `tests.md` - Test strategy, key test cases, coverage goals
- `migration.md` - Rollout plan, data migration steps

Present your analysis and recommended structure.
Ask user to confirm or adjust.

Wait for user response before proceeding.

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
specification documents.

### Spec Files to Generate

**Always create:**
- `specs/<feature>/spec.md` - Overview, requirements, acceptance criteria

**Optionally create (only if meaningful content):**
- `specs/<feature>/api.md` - API endpoints, contracts
- `specs/<feature>/data-model.md` - Schema changes, migrations
- `specs/<feature>/integration.md` - External systems, dependencies
- `specs/<feature>/security.md` - Auth, permissions, data sensitivity
- `specs/<feature>/tests.md` - Test strategy, key test cases
- `specs/<feature>/migration.md` - Rollout plan, data migration

### Writing Guidelines

- Be complete, not perfect
- Mark assumptions: `[ASSUMPTION: ...]`
- Mark unknowns: `[TBD: ...]`
- Only create files with meaningful content (no empty templates)
- Cross-reference between spec files where relevant

---

## Phase 4: Iterative Refinement

You are in conversational iteration mode with human in the loop.

**Your role:**
- Answer questions about the spec
- Raise concerns when you notice issues
- Suggest completion when specs seem sufficient

**Completion triggers:**
- User explicitly says "done" / "looks good" / "proceed"
- Agent can suggest: "The specs seem complete. Ready to proceed to `/spec-tasks`?"

Continue until either trigger occurs.

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
- Do not fake understanding - use [TBD] markers
- Do not create empty template files
- Do ask for clarification on blockers
- Do note assumptions explicitly
- Do wait for user input at each phase
- Do raise concerns when you notice them
