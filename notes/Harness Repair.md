---
tags: [architecture, explainer]
cssclasses: [topic-core]
---

# Harness Repair

How a broken model reply becomes a valid tool call, and why most of that costs
nothing. [[Agent Loop]] covers the loop's shape; this is the repair pipeline
inside one turn.

![[harness-repair.svg]]

## The problem it solves

An 8B model does not fail the way a large one does. Its mistakes are mostly
**mechanical** — a fenced reply, a trailing comma, `to_addr` where the tool
wants `to`, `"2pm"` where it wants `"14:00"`. None of these are reasoning
failures, and none of them mean the model misunderstood the task.

A naive loop treats every one as an error: send it back, burn a turn, hope.
On a 20-call budget that is how a run dies with the task half done — not
because the model could not do it, but because it spent its budget being told
it wrote `to_addr`.

## Stage by stage

| # | stage | fixes | cost |
|---|---|---|---|
| 1 | [`parse_lenient`](../harness/agent.py#L79) | fences, prose around the JSON, trailing commas, unbalanced tails | free |
| 2 | [`repair_args`](../harness/agent.py#L252) | near-miss parameter names, unknown keys | free |
| 3 | [`normalize_args`](../harness/agent.py#L167) | `"2pm"` → `"14:00"`, `"tomorrow"` → an ISO date | free |
| 4 | `validate_call` | anything still wrong — feedback carries the tool's own example | 1 call |
| 5 | [`task_date_mismatch`](../harness/agent.py#L213) + plan checks | a date the task did not mean, an unplanned write, a write before the read you planned | 1 call |
| 6 | loop-break | the same call against an unchanged world | 1 call |

### 1–3 are silent

They happen in Python, before anything is judged. `repair_args` uses
`difflib.get_close_matches` to rename a near-miss to the required parameter,
then drops what is left over. The model is never told, because there is nothing
useful to tell it — it already expressed the right intent.

### 4 rejects, but usefully

Only once deterministic repair has failed. The feedback is not "invalid call";
it carries the **example from that tool's own docs**, and if the tool name
itself is wrong, the closest real name with *its* example. A rejection that
does not show the right shape just buys another wrong guess.

### 5 questions, it does not rewrite

This is the newest layer and the one with the sharpest rationale. `normalize_date`
returns immediately when the model has already written a well-formed
`YYYY-MM-DD` — so a model that does the weekday arithmetic itself and gets it
wrong sails straight through, and every tool answers honestly for the wrong day.

Observed live: the task said Wednesday, the 8B sent a Monday, and the agent told
a colleague their Wednesday was clear.

The fix deliberately stops short of correcting it. The harness says what looks
wrong and what the task implied, and lets the model decide — because a tool
result may know something the task text does not. It also only fires when the
task names **exactly one** date, so "move my Wednesday meeting to Friday" is
left alone.

The same principle covers writes: a write not named in the plan, or a write
before the lookup the plan promised, gets questioned rather than blocked.

### 6 edits the transcript

When a call repeats past its budget against an unchanged world, the harness does
not merely refuse to re-run it:

```python
if messages[-3]["content"] == reply:
    del messages[-3:-1]
```

**Repetition in context is an attractor.** Leaving the duplicate in makes the
next repeat more likely, so the duplicate is removed. The transcript is
something the harness manages, not an append-only log.

The budget is counted against a `world_version` that bumps on every successful
write, so a repeat only burns budget while nothing has changed. Re-reading an
unchanged inbox is pointless; re-reading it after writing may be legitimate.

## What makes the comparison honest

Every one of these — the plan, both verify rounds, and each repair above — is
paid for out of **the same `MAX_CALLS` the unscaffolded loop gets**. The harness
is not given more compute. It spends the same budget on fewer wasted turns.

That is the whole claim, and it is why [[Raw vs Harness|both loops live in one
file]] over one set of tools.

## Related

- [[Agent Loop]] — the shape of one turn end to end
- [[Raw vs Harness]] — the experiment this pipeline is the treatment in
- [[Harness Profiles]] — which of these are switched off for which model size
- [[Determinism]] · [[Tools]]
