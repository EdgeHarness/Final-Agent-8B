---
tags: [architecture, models]
cssclasses: [topic-core]
---

# Model Tiers

`--tiers` routes calls through
[model_router.py](../standalone/harness/model_router.py) instead of the plain
`LLM` client ([run_agent.py:131-147](../standalone/agents/8b/run_agent.py#L131-L147)). `ModelRouter` is
a drop-in for `LLM` — same `.chat(messages, force_json=, num_predict=, role=)`
and the same `.calls` / `.output_tokens` / `.wall` counters — so
[[Agent Loop|run_harness]] accepts either object unchanged, and the shared
budget check keeps working across tiers.

## Roles

Every model call already carries a role; without `--tiers` it is only a label.

| role | job | num_predict | keep_alive |
|---|---|---|---|
| `driver` | chooses the next tool | 700 | 30m |
| `router` | the [[Agent Loop#Plan\|plan]] call | 250 | 30m |
| `verifier` | the pre-`done` check | 250 | 30m |
| `deep` | declared, `on_demand` | 900 | `"0"` |

## One model resident

The default lineup ([model_router.py:34](../standalone/harness/model_router.py#L34))
points `driver`, `router` and `verifier` at **one base tag**, so exactly one
model stays in RAM. `deep` is marked `on_demand` with `keep_alive: "0"` — Ollama
loads it for that call and evicts it immediately, so it never co-resides for
longer than a single request. Nothing invokes it automatically; `resident_models()`
excludes it, and that is what the banner reports.

Clients are cached by `(model, keep_alive)` and reused, so shared roles share one
connection.

```powershell
.\run.ps1 --tiers "Summarise the README and write a one-line TODO file"
.\run.ps1 --tiers --small llama3.2:3b "..."   # 3B plans and verifies; 2 models resident
.\run.ps1 --tiers --deep qwen2.5:32b "..."    # heavier on-demand tier
```

`--small llama3.2:3b` is the most useful variant: planning and verification are
short, structured calls a 3B handles well, so the 8B spends its time driving.
The cost is a second model resident in RAM.

`llama3.1:8b` is the router's own hard-coded default base, and `qwen2.5:14b` its
default deep tier — this folder is the configuration the tier system was written
around.

## Accounting

Every call appends a record — role, model, adapter, prompt/output tokens,
latency — to `self.call_log` and to `logs/model_calls.jsonl`. Log write failures
are swallowed (`except OSError: pass`) so a read-only disk cannot kill a run.
`usage_by_role()` aggregates it for the end-of-run summary.

## Config-driven alternative

A `router` block in [config.json](../standalone/agents/8b/config.json) enables the router without the
flag ([run_agent.py:136](../standalone/agents/8b/run_agent.py#L136)) and can pin `base`, `small`,
`deep`, or a full `roles` map. This folder's config has no such block.

## The LoRA seam

Each role may name an `adapter`. Ollama's HTTP API cannot hot-swap a LoRA per
request, so the default backend treats the field as documentation and
specialises the base **by prompt and sampling instead**. A `llama-server`
backend — which ships with Ollama — *can* toggle a LoRA per call via its
`/lora-adapters` endpoint at ~0 RAM cost; that is where a trained GGUF adapter
would plug in. `adapters_note()` prints the honest status in the banner, and the
field is already carried through into the call log.

## On a llama.cpp backend, tiers collapse

Everything above assumes Ollama, which manages models and honours `keep_alive`.
Behind the [[Ollama Shim]] one `llama-server` serves **one** loaded model and
ignores the `model` field, so `--small` and `--deep` silently route to whatever
is loaded while the banner and `model_calls.jsonl` still report the tag that was
*asked* for. The default single-base lineup is unaffected; `--small llama3.2:3b`
is actively misleading. `keep_alive: "0"` has no equivalent either, so the
on-demand eviction above does not happen. See
[[Ollama Shim#The sharp edge: tiers collapse|the shim note]].

## Related

- [[Architecture]] · [[Harness Profiles]] · [[Flags]] · [[Ollama Shim]]
