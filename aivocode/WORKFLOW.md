# Workflow

## Core Principle

Main agent's context is high-value asset for reasoning, not storage.

Pulling large amounts of raw data into context causes:
- Cluttered context
- Missed connections
- Poorer decisions

Subagents gather, compress and execute. Main agent receives summaries, not raw files.
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

Operate directly only when ALL of these are true:
- Target is precisely known (file + location)
- Single file, small output
- Judgment needed immediately on the content
- No exploration required

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