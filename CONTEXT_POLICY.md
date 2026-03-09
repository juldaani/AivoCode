# Context Preservation Policy

## Core Principle

Preserve the main agent’s context for reasoning, synthesis, and decisions.

Use main-agent context for thinking, not for storing raw or intermediate information that can be gathered, filtered, and compressed elsewhere.

## Delegation Default

Delegate whenever:
- delegation meaningfully reduces context load, and
- the work can be done without the main agent’s judgment during execution.

This includes both single operations and multi-step workflows.

If a subagent can independently gather, inspect, filter, and extract the needed information, delegate it.

## Direct Operation Exception

Operate directly only when:
- the task is precise and tightly scoped,
- the information is small and low-noise, or
- the main agent’s judgment is needed between steps,
- and the information must remain in context for immediate reasoning.

If the work mainly produces raw information rather than reasoning value, delegate it.

## Delegation Signals

Prefer delegation for:
- large or noisy retrieval
- exploratory or uncertain lookup
- repeated or chained information-gathering
- filtering raw material into a few facts
- comparing or summarizing multiple sources
- tool-use patterns where small outputs accumulate into context bloat

These are signals, not rigid rules.

## Accumulation Trap

Context pollution also comes from many small outputs.

A chain like:
*search → read → search → read → compare*

should usually be delegated unless the main agent’s reasoning is required between steps.

## Delegation as Compression

Subagents are context-compression filters.

When delegating:
- specify what to extract
- request structured output
- ask for minimal supporting context
- avoid full content unless necessary

After delegation, summarize the findings in your own words before continuing.

## Heuristic

Ask:

**“Does this need to live in my context for reasoning, or can it be compressed before it reaches me?”**

- If it can be compressed elsewhere → **delegate**
- If it must remain in context for reasoning → **operate directly, carefully**
