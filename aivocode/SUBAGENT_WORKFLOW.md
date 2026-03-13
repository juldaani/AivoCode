# Subagent Workflow

---

## Core Principle

Main agent's context is high-value asset for reasoning, not storage.

Pulling large amounts of raw data into context causes:
- Cluttered context
- Missed connections
- Poorer decisions

Subagents gather, synthetize, compress and execute. Main agent receives summaries, not raw files.

This preserves context for what matters: thinking and deciding.

---

## Context Hierarchy

**Main Agent:** Full session context: planning, strategy, reasoning, decisions, orchestration.

**Subagents:** Isolated context (what you provide): execution of specific tasks, gathering info.

Subagents are weaker models. They cannot see the big picture.
Think of them like functions: discrete inputs, bounded scope.

**Context Handoff Rule:** 
Subagents have NO session context—they only see
what you give them. You are responsible for providing all relevant context.

Before delegating, ask: "What does the subagent need that I already know?"
- Known URLs/links → provide directly
- Relevant file paths → include in prompt
- Previous findings → summarize and pass

If you withhold context, the subagent will search blindly or force re-delegation.
If you have it and it's relevant, provide it.

---

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

---

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

---

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

---

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

### Context Withholding
Not providing enough session context for the subagent (known URLs, links, file paths, 
relevant findings..). Always hand off relevant information that enables subagent to execute 
the task efficiently.

---

## Example Scenarios

### Finding Code Locations
Goal: Find where `process_payment` is defined and called.
- Delegate to @explore: "Find definitions and calls. Return: paths + line numbers."
- Receive results. Goal complete.

### Looking Up Documentation
Goal: Find SQLAlchemy 2.0 transaction handling patterns.
- Delegate to @web-ops: "SQLAlchemy 2.0 and nested transactions? Return: summary + code example."
- Receive results. Ready to decide. Loop.

### Quick Verification
Goal: Check return type of `process()` in known file.
- Operate directly: Target known, single file, small output.
- Read specific function. Goal complete.

### Implementation After Design
Goal: Implement approved refactoring.
- Delegate to @general: "Apply changes to these files. Return: modified files, issues."
- Receive results. Goal complete.

---

## Subagent Quick Reference

Quick lookup: which subagent for what task.

### @explore

Use for: All read-only work on the codebase.
- Finding code locations
- Understanding modules or flows
- Multi-file search

Returns: File paths, minimal snippets, structured summaries.

### @web-ops

Use for: External web lookup.
- Documentation and guides
- API references
- Other web-related read ops

Returns: Summaries, code examples, sources.

### @general

Use for: Bounded self-contained tasks.
- File editing, Bash
- Multi-step workflows combining read + write
- Parallel execution of independent tasks

Do NOT use: codebase exploration (@explore), web lookup (@web-ops)

Context Test: Needs session context? → Main agent. Self-contained? → @general.

If task needs session context → main agent
If task is self-contained → @general

Note: @general is capable of complex work. The constraint is context isolation,
not task complexity. Provide all needed context in the delegation.

Returns: Files touched, actions taken, blockers.

---
