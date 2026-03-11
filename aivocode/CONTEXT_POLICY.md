# Context Preservation Policy

## Core principle

- Keep the main agent's context for reasoning and decisions, not for storage.
- Do not pull in raw or intermediate data that a subagent can gather and compress.
- Context pollution degrades reasoning. A cluttered context leads to missed
  connections and poorer decisions.

## When to delegate

Always delegate when:

- Delegation meaningfully reduces context load, and
- The work can run without the main agent's judgment during execution.

Treat both single operations and multi-step workflows as candidates for delegation.
If a subagent can independently search, read, filter, compare, and summarize, delegate
instead of pulling raw content yourself.

If intermediate decisions in subagent's multi-step workflows require your judgment —
e.g., evaluating tradeoffs, choosing between options, assessing architectural
fit — keep it in main context or break into smaller delegations with checkpoints.

For hybrid tasks spanning multiple phases, split by phase and use the appropriate
subagent for each. This creates checkpoints for main-agent judgment.

## When to operate directly

Operate directly only when all of these hold:

- The task is precise and tightly scoped (typically 1-2 files or a small output).
- The information is small and low-noise.
- The main agent's judgment is needed between steps.
- The information must remain in context for immediate reasoning.

If the work mainly produces raw information rather than reasoning value, delegate it.

## Simple rule of thumb

- If you expect to touch more than 2 files or produce more than about 150 lines of raw
  tool output, delegate.
- If the task can be answered by one or two tightly scoped reads or searches, and you
  need to reason immediately on the result, operate directly.
- When in doubt, delegate and ask subagents to return structured summaries plus minimal
  supporting snippets.

## Avoid the accumulation trap

- Many small tool calls can pollute context just as much as one large dump.
- Avoid repeated patterns like: search -> read -> search -> read -> compare in the
  main agent.
- For these patterns, group the work into a single delegated subagent task instead.
- Before making a tool call, ask: what else will I likely need? Anticipate your
  information needs and bundle them into one delegation rather than discovering
  them incrementally.

## Delegation as compression

Treat subagents as context-compression filters.

When delegating:

- State the goal and the decisions you need to make.
- Specify what to extract and in what format (lists, tables, bullet summaries).
- Ask for concise summaries with only the minimal supporting snippets needed.

After delegation, summarize the important findings in your own words before continuing.

## Final heuristic

Before pulling data into context, ask:

- "Do I need this raw, here, to think?"
- "Is this exploration, or judgment?"

If it's exploration, delegate.
If it's judgment, keep it in the main agent.
If it's both, delegate the exploration phase and return for a checkpoint.
