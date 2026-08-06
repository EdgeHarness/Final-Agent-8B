---
tags: [architecture, loop]
---

# Agent Loop

`run_harness()` — [agent.py:323-470](../standalone/harness/agent.py#L323-L470).
One tool call per model reply, JSON only. Its stripped-down twin `run_raw()`
sits directly above it; see [[Raw vs Harness]].

## Setup

Relevant long-term memories are retrieved with `mem.search(task, k=PROFILE.memory_k)`
— keyword overlap, **matches only, never a recency fallback**
([agent.py:325](../standalone/harness/agent.py#L325)) — and injected under
`THINGS YOU HAVE LEARNED PREVIOUSLY`. The system prompt carries the response
shape, six rules, and full tool docs *with a worked example per tool*.

The shape string itself is deliberately abstract:

```python
SHAPE = '{"thought": "<why>", "tool": "<tool_name>", "args": { ... }}'
```

> Concrete example content in an instruction becomes an attractor that 1B models
> copy verbatim. Real examples live per-tool in docs.

## Plan

Opt-out per profile (`PROFILE.plan`). One call asks for a tool-grounded plan:
`{"steps":[{"tool":..., "what":...}]}`, capped at `PROFILE.plan_max_steps`
(5 at 8B).

- Steps naming a tool not in `TOOLS` are dropped
  ([agent.py:315](../standalone/harness/agent.py#L315)).
- `what` is truncated to 60 characters.
- The surviving plan re-enters as `Suggested tool sequence (adapt if the results demand it)`.
- The plan *request* is popped from the context
  ([agent.py:344](../standalone/harness/agent.py#L344)), so the model never sees
  its own planning prose again.

The principle: free-form prose is never allowed to become an instruction the
model then obeys.

## Act

Until `done` is accepted or the [[Flags|budget]] runs out:

| stage | what happens |
|---|---|
| decode | `format=json` — grammar-constrained, so the reply is JSON or nothing |
| parse | strict `json.loads` after fence-strip; on failure, brace-match the first object → drop trailing commas |
| repair | near-miss parameter names renamed onto missing required ones (`difflib`, cutoff 0.5, then substring fallback); unknown parameters dropped; top-level args lifted into `args` |
| normalize | `date` → `YYYY-MM-DD`; `time`/`start_time`/`end_time` → 24h `HH:MM` |
| validate | missing/unknown parameters caught **before** execution; feedback quotes the tool's own example |
| repeat check | a call already run against an unchanged world may repeat only up to its budget |
| execute | tool runs; result truncated to 2000 chars, fed back as `OBSERVATION:` |

### Normalize

[`normalize_date`](../standalone/harness/agent.py#L110) resolves against the
[[Determinism|simulated clock]], bound at call time so a runner can repoint it:
`today`, `tomorrow`, `next tuesday` (bare `tuesday` too — always the *next* one,
never today), `Jul 23`, `7/23`. Times normalize to 24-hour, with the `12am`/`12pm`
edge cases handled. Anything unrecognised passes through untouched and gets
caught by the world's own `_check_date`.

### Validate

Argument checking happens *before* execution
([tools.py:149](../standalone/harness/tools.py#L149)), and the failure message
quotes the tool's worked example rather than describing the schema. If the tool
name itself is unknown, `difflib` suggests the closest real one and quotes *its*
example. Showing a small model the right shape beats telling it.

### Repeat budget — not a hard dedupe

The README describes this as "an identical call against an unchanged world is
not re-executed". The code is more forgiving
([agent.py:426-461](../standalone/harness/agent.py#L426-L461)):

- `PROFILE.repeat_limit` executions of the same `(tool, args)` are allowed —
  **3 at 8B**, 2 at 1B/3B.
- `PROFILE.repeat_limit_write` is separately pinned at **1** for world-changing
  tools, because an identical write stacked on its own result is a duplicate
  (two invites, doubled text), not a retry.
- `world_version` bumps on every successful write and hands out a fresh budget —
  the same read can legitimately return something new now.
- `think` is exempt entirely.

The comment is explicit about why the limit isn't 1 for reads: *read the email,
think, read it again* is a real pattern a hard one-shot rule blocks.

## Finish

When the model calls `done`, a **verifier** call
([agent.py:473](../standalone/harness/agent.py#L473)) re-reads the task against
the list of non-`think` actions actually taken and answers
`{"complete": bool, "missing": str}`.

- If incomplete, `done` is rejected and the gap is quoted back.
- `PROFILE.verify_rounds` rounds (2 at 8B), and only while budget remains.
- On any verifier *error or malformed reply* it returns `{"complete": true}` —
  a broken verifier should not trap the agent in the loop forever.

At 8B this is the single highest-value piece of scaffolding: the model will
happily call `done` with the last clause of a three-part task unaddressed.

## Repetition handling

Models fall into loops, and a repeated exchange sitting in the context *is
itself the attractor* pulling them back. So when a reply is a verbatim repeat,
the harness **deletes the older copy of the exchange** from the message list
(`del messages[-3:-1]`) before restating the task. This fires in two places:
`give_feedback` for repeated invalid replies
([agent.py:362](../standalone/harness/agent.py#L362)), and the repeat-budget
branch for valid-but-redundant calls.

`PROFILE.think_streak_cap` consecutive `think` calls (2 at 8B) append
`NOTE: stop thinking and take a concrete action now.` to the observation.

## Budget honesty

Plan, verify, and every repair round are paid out of the same `MAX_CALLS`
counter as ordinary tool calls — the `while llm.calls < MAX_CALLS` condition
counts *model invocations*, not tool executions. The scaffolding does not get
free turns.

## Related

- [[Raw vs Harness]] · [[Tools]] · [[Harness Profiles]] · [[Determinism]]
