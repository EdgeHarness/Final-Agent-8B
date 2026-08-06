---
tags: [experiment, architecture]
cssclasses: [topic-core]
---

# Raw vs Harness

[agent.py](../standalone/harness/agent.py) defines **two loops over the same
tools and the same LLM-call budget**. That pairing is the experiment the whole
project is built around.

## raw

> what you get wiring a model to tools naively: tool list in the prompt, strict
> JSON parsing, errors fed back verbatim, no other help.

`run_raw()` ([agent.py:239](../standalone/harness/agent.py#L239)) — ~35 lines.
No `format=json`, no plan, no verifier, no repair, no memory injection, no
loop-breaking. A parse failure gets one generic "respond with a single JSON
object" and another turn. `done` is accepted immediately, whatever the state of
the task.

## harness

`run_harness()` — the same skeleton plus ten named additions:

1. few-shot example per tool in the docs
2. grammar-constrained decoding (`format=json`)
3. lenient JSON extraction + repair feedback
4. deterministic call repair before rejecting anything
5. schema validation with corrective, example-bearing feedback
6. date/time argument normalization
7. a tool-grounded plan step (JSON list of tool names, not free prose)
8. loop-breaking with per-profile repeat budgets
9. a verifier pass before accepting `done()`
10. auto-injection of relevant long-term memories

Each is walked through in [[Agent Loop]].

## Why both stay in one file

The comparison only means something if the two loops share tool behaviour and
error text exactly — [tools.py](../standalone/harness/tools.py) is used by both,
and the module docstring is blunt about it: *the experiment varies only the
scaffolding around the model.*

That constraint shows up as a discipline everywhere else in the codebase:

- `bench/` runs `run_harness` with the **DEFAULT** [[Harness Profiles|profile]],
  never a per-model one, so graded runs stay byte-identical to runs already on
  disk.
- `EXTRA_RULES` and `EXTRA_WRITE_TOOLS` default to empty, keeping the graded
  system prompt unchanged.
- [[Real-Computer Mode|fs_tools]] and the [[MCP Bridge]] inject tools *in the
  calling process only*, and `bench/` imports neither.
- Even the loop-break feedback keeps a special case: when `repeat_limit == 1`
  it emits the exact phrasing the benchmark was run on
  ([agent.py:442-446](../standalone/harness/agent.py#L442-L446)).

Anywhere the codebase looks over-careful, this is usually why.

## Related

- [[Agent Loop]] · [[Harness Profiles]] · [[Architecture]]
