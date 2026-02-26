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
   - Export the current session to `specs/<feature-name>/session_discovery.json`
   - Use the custom tool `export-session` with `outputPath`
   - Delegate to the `@gen-discovery-spec` subagent

4. **When delegating**:
   - Provide the feature name
   - Provide the source path: `specs/<feature-name>/session_discovery.json`
   - Provide the target path: `specs/<feature-name>/discovery.md`

5. **Report results**:
   - If generated: "Created `specs/<feature-name>/discovery.md`"
   - If skipped: "Created `specs/<feature-name>/`"

## Notes

- discovery.md must be self-contained and preserve all relevant knowledge
- The subagent is responsible for summarization and structure
- Do not implement code changes
