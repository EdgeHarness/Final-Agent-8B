---
tags: [reproducibility]
cssclasses: [topic-core]
---

# Determinism

Two runs of the same task against the same state produce the same trajectory.

| knob | value | source |
|---|---|---|
| temperature | `0.0` | `LLM` default, [llm.py:20](../harness/llm.py#L20) |
| seed | `42` | hard-coded in every payload, [llm.py:48](../harness/llm.py#L48) |
| `num_ctx` | [config.json](../agents/8b/config.json), else the [[Harness Profiles\|profile]] | 8192 here |
| decode format | `format=json` when `force_json` | harness loop only |
| `keep_alive` | `30m` | model stays warm between calls |
| simulated clock | **Monday, 2026-07-20** | [world.py:12](../harness/world.py#L12) |

The fixed clock is what makes date reasoning reproducible: "next Tuesday" has to
resolve to the same `YYYY-MM-DD` on every run for a benchmark to mean anything.
`normalize_date` binds it at *call* time rather than import time, precisely so a
runner can repoint it without touching the module.

Note that `format=json` is a [[Raw vs Harness|harness-only]] affordance — the raw
loop calls `chat(..., force_json=False)` and parses whatever prose comes back.
Grammar-constrained decoding is one of the things being measured, not a
baseline.

## Where determinism breaks, on purpose

- **[[Real-Computer Mode|--root]]** swaps in the real system date
  ([run_agent.py:240-242](../agents/8b/run_agent.py#L240-L242)). A real-file agent should
  reason about today. Real-mode runs are therefore not reproducible across days,
  and that is the intended trade.
- **`deep` tier** ([[Model Tiers]]) is the one role with a non-zero temperature
  (`0.2`). Nothing invokes it automatically.
- **Streaming.** When `STREAM_HOOK` is set (the web UI), the request switches to
  `stream=True`. The payload is otherwise identical, so sampling is unchanged.

## What "same state" means

State accumulates ([[Persistent State]]), so the precondition is stronger than
it looks — the same task run twice in a row is *not* the same experiment,
because the first run mutated `workspace/state.json` and possibly
`memory/memory.jsonl`, and an injected memory changes the system prompt. Reset
between comparisons. The benchmark sidesteps this entirely by running
`persistent=False`.

## Related

- [[Agent Loop]] · [[Persistent State]] · [[Raw vs Harness]] · [[Real-Computer Mode]]
