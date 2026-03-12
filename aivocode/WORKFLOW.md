# Workflow

## Core Principle

Main agent's context is high-value asset for reasoning, not storage.

Pulling large amounts of raw data into context causes:
- Cluttered context
- Missed connections
- Poorer decisions

Subagents gather, synthetize, compress and execute. Main agent receives summaries, not raw files.

This preserves context for what matters: thinking and deciding.

### Main Agent Role

- Planning and strategy
- Understanding and context
- Decisions and judgments
- Orchestration

### Subagent Role

- Execution of specific tasks
- Gathering information
- Carrying out delegated work

Note: Subagents are weaker models. They cannot see the big picture or
the full session context. They only see what you provide in the delegation.
Think of them like functions: discrete inputs, bounded scope.

## WORKFLOW LOOP

1. HAS GOAL
   Main agent starts with a goal.

2. IDENTIFIES GAP
   What information or action is needed next?

3. CAN DELEGATE?
   See Delegation Rules for criteria.
   
   - YES: Delegate to subagent.
          Subagent: gathers, searches, filters.
          Returns: results.
          Go to 4.
   
   - NO: Operate directly.
         (Rare. Requires justification.)
         Go to 4.

4. INTEGRATES
   Absorb results. Update understanding.

5. DECIDES NEXT STEP
   
   - Gap remains? Loop to 2.
   - Goal complete? End.

## Delegation Rules

Default: Delegate.

### What to Delegate

Tasks suitable for delegation are:
- Discrete: Clear start and end
- Bounded: Limited scope (files, operations)
- Well-defined: Specific ask and expected output
- Independent: Can run without main agent reasoning in between
- Parallelizable: Can run alongside other tasks 

### Operate Directly

Operate directly only when ALL of these are true:
- Target is precisely known (file + location)
- Single file, small output
- Judgment needed immediately on the content
- No exploration required

If a task needs main agent judgment during execution, it's too large.
Break it into smaller tasks with checkpoints.

If the work produces raw information rather than reasoning value, delegate.

If uncertain, delegate.

## Self-Correcting Triggers

Triggers catch you mid-execution when falling into anti-patterns.

Incremental discovery feels natural — read one file, then another — but
pollutes context before you notice. These triggers interrupt the accumulation.

Apply during: file reads, glob, grep, web fetch, bash output, and any
output-producing operations.

- After 2 file reads / web fetches in one investigation:
   PAUSE. Consider delegating.

- After 3 file reads / web fetches without delegating:
   STOP. Delegate remaining work.

- After any tool output exceeds ~100 lines:
   PAUSE. You should have delegated. Note for next time.

- After 2 tool executions in one investigation, exceeding ~200 lines:
   STOP. Delegate remaining work.

## Anti-Patterns

Named bad behaviors. DO NOT engage.

### Cascading Reads
Reading A → see reference to B → read B → see reference to C → read C.

### Search-Read Loop
grep → read → grep → read in main agent.

### File Delivery Service
Using subagents to return full files/web pages.

### Default to General
Sending any "coding task" to @general without checking if bounded.
@general is for execution after design is decided. Not for exploration or decisions.

### Premature Delegation
Delegating before you know the goal, scope, or approach.
Plan first. Delegate when the task is clear and bounded.

## Example Scenarios

Concrete cases showing the workflow in action.

### Scenario 1: Finding Code Locations

Goal: Find where `process_payment` is defined and called.

Step 1: HAS GOAL — Locate payment function.
Step 2: IDENTIFIES GAP — Don't know which files.
Step 3: CAN DELEGATE? Yes. Location unknown.
   Delegate to @explore: "Find all definitions and calls of process_payment.
   Return: file paths + line numbers + 1-line context each."
Step 4: INTEGRATES — Has locations.
Step 5: DECIDES — Goal complete.

### Scenario 2: Understanding a Module

Goal: Understand auth flow before making changes.

Step 1: HAS GOAL — Understand auth architecture.
Step 2: IDENTIFIES GAP — Don't know the flow.
Step 3: CAN DELEGATE? Yes. Exploration needed.
   Delegate to @explore: "Explain authentication flow: entry points,
   validation steps, session management. Return: numbered steps + key files."
Step 4: INTEGRATES — Has mental model.
Step 5: DECIDES — Ready to design changes. Loop to 2.

### Scenario 3: Quick Verification

Goal: Check return type of `process()` in known file.

Step 1: HAS GOAL — Verify function signature.
Step 2: IDENTIFIES GAP — Need type annotation.
Step 3: CAN DELEGATE? No. Target known, single file, small output.
   Operate directly: Read specific function in services/processor.py.
Step 4: INTEGRATES — Has answer.
Step 5: DECIDES — Goal complete.

### Scenario 4: Implementation After Design

Goal: Implement approved refactoring.

Step 1: HAS GOAL — Apply changes.
Step 2: IDENTIFIES GAP — Need execution.
Step 3: CAN DELEGATE? Yes. Bounded task, design decided.
   Delegate to @general: "Rename UserModel to User in these 3 files.
   Update imports. Return: files modified, any issues."
Step 4: INTEGRATES — Changes applied.
Step 5: DECIDES — Goal complete.

### Scenario 5: Anti-Pattern — Cascading Reads

What happened:
- Read auth.py → saw import of session.py
- Read session.py → saw reference to cache.py
- Read cache.py → saw import of config.py
- Read config.py → context polluted, 4 files in memory

What should have happened:
- After 2nd read: PAUSE. Consider delegating.
- After 3rd read: STOP. Delegate remaining investigation to @explore.

## Subagent Quick Reference

Quick lookup: which subagent for what task.

### @explore

Use for: All read-only work on local repo.
- Finding code locations
- Understanding modules or flows
- Multi-file search
- Cross-cutting analysis

Returns: File paths, minimal snippets, structured summaries.
Do NOT ask for: Full file contents.

### @web-ops

Use for: External web lookup.
- Documentation and guides
- API references
- Current status or versions
- How-to examples
- Other web-related reads

Returns: Summaries, code examples, sources.

### @general

Use for: Bounded execution after design is decided.
- Applying approved changes
- Running tests
- Executing well-defined tasks

Returns: Files touched, actions taken, blockers.
NOT for: Exploration, design decisions, open-ended work.

### Decision Guide

| Need to... | Use |
|------------|-----|
| Find code in repo | @explore |
| Understand a module | @explore |
| Look up docs or guides | @web-ops |
| Execute bounded changes | @general |
| Make a decision | Main agent (stay here) |