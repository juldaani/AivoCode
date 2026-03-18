---
description: Archive completed feature specs
agent: architect
---

# Spec-Driven Development: Archive Feature

Move completed feature specs to aivocode/specs/archive/ with timestamp.

## Argument Handling

Input argument: arg = `$ARGUMENTS`

### Case: No argument

1. List features: `ls aivocode/specs/` (exclude archive folder)
2. If no features: abort with "No features found in aivocode/specs/."
3. Ask: "Which feature to archive?"

### Case: arg provided

Treat as feature name, proceed to validation.

---

## Validation

1. Check `aivocode/specs/<feature>/` exists
   - **Not found**: abort with "Folder aivocode/specs/<feature>/ not found."

2. Check `tasks.md` exists
   - **Not found**: abort with "No tasks.md found in aivocode/specs/<feature>/."

---

## Completion Check

1. Parse tasks.md
2. Count remaining tasks (lines starting with `[ ]`)
3. If remaining > 0:
   - Warn: "X tasks remaining. Archive anyway? [y/n]"
   - Wait for confirmation

---

## Archive

1. Create `aivocode/specs/archive/` if not exists
2. Generate timestamp: `YYYY-MM-DD`
3. Move `aivocode/specs/<feature>/` to `aivocode/specs/archive/<timestamp>_<feature>/`
4. Preserve all files

---

## Confirmation

```
Archived: aivocode/specs/<feature>/ → aivocode/specs/archive/<timestamp>_<feature>/

Files moved:
- tasks.md
- spec.md
- [other files]
```

---

## Guardrails

- Do not archive without validation
- Do warn user if tasks incomplete
- Do preserve all files
