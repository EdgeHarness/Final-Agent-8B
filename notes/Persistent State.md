---
tags: [state, memory]
---

# Persistent State

The world is opened with `persistent=True`
([run_agent.py:161](../run_agent.py#L161)) — the benchmark uses
`persistent=False` and gets fresh fixtures every episode, so runs accumulate
only for the on-device agents.

| path | contents |
|---|---|
| `workspace/state.json` | inbox, calendar, sent mail, chat messages, reminders — seeded with demo fixtures on first run, then evolves |
| `workspace/files/` | the real `.pptx` / `.xlsx` the agent produced |
| `memory/memory.jsonl` | long-term memory; say "remember that …" and later runs get it injected |
| `logs/run_NNN.json` | full transcript: system prompt, plan, every model reply, repairs, observations, verdicts |
| `logs/model_calls.jsonl` | per-call tier/token/latency records ([[Model Tiers\|--tiers]] only) |

`world.snapshot()` runs at the end of both loops, so state is written even if
the episode ran out of budget without calling `done`.

## The learning loop

`memory/memory.jsonl` in this folder already carries one fact from an earlier
session:

```json
{"fact": "Dana owns the auth fix, Priya is waiting on it, Sam owns the billing webhook blocker."}
```

Any task whose wording overlaps those keywords gets it injected into the system
prompt automatically — the model never has to call `recall_memories`. That is
the whole learning loop: `save_memory` in one episode, keyword-matched injection
in the next.

## How retrieval actually works

[memory.py](../standalone/harness/memory.py) is 53 lines and does exactly what
it says:

- lowercase, split on `[a-z0-9]+`, drop a 22-word stoplist
- score each fact by **set-overlap count** with the query
- sort by score, return the top `k` — `PROFILE.memory_k`, so 3 at 8B
- facts with **zero** overlap are never returned; there is no recency fallback

An unrelated task therefore gets nothing rather than the three most recent
facts, which keeps irrelevant context out of an 8B's already tight window. The
cost is that paraphrases miss entirely: a memory about "auth" will not surface
for a task phrased around "login", and set-overlap ignores repetition, so a long
fact is not favoured over a short one.

Facts are append-only strings. There is no dedupe, no update, no delete — saving
a corrected version leaves the wrong one in the file, and both can match.

## Factory reset

Delete `workspace/state.json` and `memory/memory.jsonl`.

## Log numbering

The run-log index is `len(os.listdir(log_dir)) + 1`
([run_agent.py:205](../run_agent.py#L205)) — a *file count*, not a max of
existing run numbers. `logs/model_calls.jsonl` occupies a slot in that count, so
with `--tiers` the numbering skips ahead by one, and deleting an old log makes
the next run overwrite an existing transcript. See [[Open Questions]].

## Related

- [[Agent Loop]] · [[Tools]] · [[Running the Agent]]
