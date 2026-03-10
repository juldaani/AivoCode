---
description: Start new spec-driven feature development
---

# Spec-Driven Development: New Spec

You are starting a new spec-driven development workflow.

## Your Task

1. **Create the spec folder**:
   - If `$ARGUMENTS` provided: use that as the feature name
   - If no arguments: ask the user for a feature name
     - Suggest a name based on the current conversation context
   - Create folder: `specs/<feature-name>/`
   - Use: `mkdir -p specs/<feature-name>/` (safe, no overwrite)

2. **Ask about discovery.md**:
   - Ask the user if they want to generate `discovery.md` now

3. **If user says yes**:
   - Generate `discovery.md` directly from the current conversation context
   - Write to: `specs/<feature-name>/discovery.md`

## discovery.md Requirements

The document must be self-contained: a fresh agent reading only `discovery.md` 
should understand everything the original conversation conveyed.

Capture:
- All requirements, constraints, decisions
- Open questions and context
- Important terminology and naming from the conversation

Guidelines:
- Be clear and structured, but prioritize completeness over brevity
- DO NOT fake understanding or fill in blanks that are not grounded in context
- Do not implement code changes

## Report Results

- If generated: "Created `specs/<feature-name>/discovery.md`"
- If skipped: "Created `specs/<feature-name>/`"
