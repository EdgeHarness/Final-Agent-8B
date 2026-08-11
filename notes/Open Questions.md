---
tags: [todo]
---

# Open Questions

Read off the source, not from a live run — nothing here has been reproduced by
executing the agent.

## Two copies of the agent folder

The root-level `run_agent.py` / `config.json` / `run.ps1` / `memory/` cannot
import their harness ([[Running the Agent]]). The `standalone/` copy is
complete. Decide which is canonical and delete or re-root the other, before the
two `memory/memory.jsonl` files drift apart — they are separate stores, and
whichever copy you run is the one that learns.

## The deny-list does nothing on macOS

`_DENY_WRITE` ([fs_tools.py:36](../standalone/harness/fs_tools.py#L36)) is
entirely Windows paths and `C:\Users\Lab User\SAIL\…` literals. Under
[[Real-Computer Mode|--root]] on this machine, layer 2 of three is inert; only
the root containment check applies. Port the entries, or note the mode as
Windows-only.

## Run-log numbering collides

`n = len(os.listdir(log_dir)) + 1` ([run_agent.py:205](../run_agent.py#L205))
counts *files*, not runs. With [[Model Tiers|--tiers]], `model_calls.jsonl`
takes a slot, so numbering jumps. Delete a log and the next run silently
overwrites an existing `run_NNN.json`. Max-of-existing-indices, or a timestamp
name, would be safer.

## Unknown flags become task text

`parse_flags()` appends anything unrecognised to the task
([run_agent.py:93-95](../run_agent.py#L93-L95)), so `--tier` (typo) is not an
error — it becomes part of the prompt. Cheap fix: reject leading-`--` tokens.

## Verifier fails open, silently

On a verifier exception *or* a malformed reply, `_verify` returns
`{"complete": True}` ([agent.py:486-493](../standalone/harness/agent.py#L486-L493)).
Right call for not trapping the agent, but a systematically broken verifier is
indistinguishable from a clean run in the transcript. Worth noting the fallback
distinctly in the episode log.

## Memory has no update or delete

[[Persistent State#How retrieval actually works|memory.py]] is append-only with
no dedupe. A corrected fact does not supersede the wrong one; both stay in the
file and both can match the same query. At one fact this is theoretical, but it
is the failure mode the "learning loop" grows into.

## Keyword retrieval misses paraphrases

Set-overlap on stopword-filtered tokens, no recency fallback. Precise, and
cheap enough to run identically for every model size — but "auth" will not
surface for "login". Embeddings would fix recall at the cost of a second
resident model, which fights the [[Model Tiers|one-model-resident]] design.

## MCP draft mode rests on a name regex

The [[MCP Bridge]] decides what transmits by pattern-matching tool names. A
server that names its send tool unusually would be exposed in `draft` mode. The
per-server allow/drop override exists for this, but it is opt-in — worth an
explicit audit of any server before pointing it at a real account.

## Tiers report models they are not using

On the [[llama.cpp Backend]], one `llama-server` serves one model and ignores
the request's `model` field. `--tiers --small llama3.2:3b` therefore runs the 8B
for every call while the banner claims two resident models and
`logs/model_calls.jsonl` records `llama3.2:3b` on every router and verifier
line. Wrong *and* silent — the accounting looks clean. Either route by model
name to a second `llama-server`, or make the [[Ollama Shim]] reject a `model` it
is not serving.

## Which Snapdragon is it, actually

Earlier tuning assumed X1E (12 cores, 135 GB/s). The current Yoga Slim 7x ships
the **X2 Elite** (18 cores, ~228 GB/s). Build flags survive either way; every
thread count and roofline figure does not. Unconfirmed, and it gates the tuning
work.

## Global harness configuration

The runner sets module-level state on `harness.agent` ([[Architecture]]), so one
process runs one agent. Fine for a CLI; a blocker for anything concurrent, and
the web UI's hooks share the same constraint.
