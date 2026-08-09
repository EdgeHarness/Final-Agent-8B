---
tags: [architecture, tuning]
cssclasses: [topic-core]
---

# Harness Profiles

[profiles.py](../standalone/harness/profiles.py) — one frozen dataclass per
model size. The harness engine is one codebase; the profile is the set of knobs
that governs it.

> One setting is never right for all five sizes, because the models fail and
> succeed differently.

The runner resolves and installs it before the loop starts
([run_agent.py:133-135](../run_agent.py#L133-L135)):

```python
profile = profiles.for_model(cfg["model"], cfg.get("harness"))
agent_mod.set_profile(profile)
cfg["num_ctx"] = cfg.get("num_ctx") or profile.num_ctx
```

## The knobs

| field | effect |
|---|---|
| `plan` / `plan_max_steps` | run the [[Agent Loop#Plan\|plan]] call, and cap its length |
| `verify_rounds` | how many times the [[Agent Loop#Finish\|verifier]] may reject `done` |
| `loop_break` | enable the repeat-budget machinery |
| `repeat_limit` | executions of an identical call while the world is unchanged |
| `repeat_limit_write` | the same for world-changing tools — pinned at 1 everywhere |
| `think_streak_cap` | consecutive `think` calls before the "act now" nudge |
| `num_predict` | driver reply length cap |
| `memory_k` | memories auto-injected into the system prompt |
| `num_ctx` | context window |
| `max_calls` | budget in the simulated world (real-file mode is always 40) |

## The five lineups

| model | label | plan | verify | repeat | think | out | mem_k | ctx | calls |
|---|---|---|---|---|---|---|---|---|---|
| `llama3.2:1b` | format-survival | ✗ | 0 | 2 | 1 | 350 | 2 | 8192 | 18 |
| `llama3.2:3b` | guided-guarded | 3 | 1 | 2 | 2 | 500 | 3 | 8192 | 14 |
| **`llama3.1:8b`** | **balanced** | **5** | **2** | **3** | **2** | **700** | **3** | **8192** | **20** |
| `qwen2.5:14b` | structured-reasoner | 6 | 2 | 3 | 3 | 900 | 4 | 12288 | 14 |
| `qwen2.5:32b` | few-precise-steps | 6 | 1 | 3 | 3 | 1000 | 4 | 16384 | 12 |

The reasoning behind the shape of that table, from the module docstring:

- **1B** — mistakes are almost all *mechanical* (broken JSON, wrong keys) and it
  loops hard. Planning and verification are dropped: it can't follow a plan or
  judge completion, so both only starve the budget. Short replies keep the JSON
  intact; extra calls compensate.
- **3B** — follows a *short* plan and survives **one** verify pass; a second
  round tends to false-negative and send it back into a loop.
- **8B** — solid instruction-following and JSON, so the full harness pays for
  itself: real planning, two verify rounds, standard budget.
  *(Raised from 14 to **20** on 2026-08-06 — plan and verify are paid out of the
  same counter, so the harness overhead was eating a 14-call budget on
  three-part tasks. `DEFAULT` stays at 14, so the benchmark is unaffected.)*
- **14B/32B** — strong at structured output and math, so richer outputs, longer
  plans, wider context. The 32B trades the second verify round and two budget
  slots for fewer, better steps: *when a call costs minutes, flailing is the
  expensive failure, not stopping early.*

The curve is not monotonic. Scaffolding is not a ladder you climb — a 1B and a
32B both get *less* of it than an 8B, for opposite reasons.

## Resolution order

`for_model(tag, override)` ([profiles.py:153](../standalone/harness/profiles.py#L153)):

1. exact tag match
2. same base family — `llama3.2:1b-instruct-q4` finds `llama3.2:1b`'s family
3. `DEFAULT`, so an unrecognised model still runs

A `harness` block in [config.json](../config.json) then patches individual
fields, filtered against the dataclass so an unknown key is ignored rather than
crashing. This folder's config sets none, so `llama3.1:8b` gets stock
**balanced**.

Budget precedence: `--max-calls` > `config.max_calls` > `40 if --root else
profile.max_calls`. Context: `config.num_ctx` > `profile.num_ctx`.

> [!note] The benchmark never sets a profile
> `bench/` runs with `DEFAULT` so the [[Raw vs Harness]] comparison stays
> byte-identical to runs already on disk. `DEFAULT` is the plain `Profile()`:
> plan on at 6 steps, 2 verify rounds, `repeat_limit` **1**, 700 tokens, 8192
> context, 14 calls — so `DEFAULT` and the 8B profile now differ on both
> `repeat_limit` and `max_calls`.

## Related

- [[Agent Loop]] · [[Raw vs Harness]] · [[Model Tiers]] · [[Flags]]
