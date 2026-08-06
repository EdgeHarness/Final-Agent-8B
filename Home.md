---
tags: [moc, agent]
---

# Local Agent — Agent 8B

An on-device agent harness built around `llama3.1:8b` served by a **local Ollama
server** at `127.0.0.1:11434`. The runner asserts the endpoint is loopback and
refuses anything else. Inference, files, memory — nothing leaves the machine.

```json
{ "name": "Agent 8B", "model": "llama3.1:8b", "note": "Llama 3.1 8B — harness profile: balanced" }
```

The underlying claim the project exists to test:

> The model is not the agent. The model is one component inside a loop that
> supplies the structure, the checking, and the memory.

[[Raw vs Harness]] is the experiment that measures it — same model, same tools,
same call budget, ten pieces of scaffolding added or removed.

## Start here

| Note | What it covers |
|---|---|
| [[Architecture]] | The component stack — what sits between `run.ps1` and the model |
| [[Agent Loop]] | Plan → act → verify, and every repair stage in between |
| [[Raw vs Harness]] | The ablation: what the scaffolding is actually worth |
| [[Tools]] | The 14-tool registry, and what real mode swaps in |
| [[Persistent State]] | What survives between runs, and how to factory-reset |
| [[Real-Computer Mode]] | `--root`, the sandbox guardrails, the confirmation flow |
| [[Model Tiers]] | `--tiers`, role routing, the LoRA adapter seam |
| [[Harness Profiles]] | Per-model tuning — the knobs, and all five lineups |
| [[MCP Bridge]] | Real Gmail / Outlook over MCP, draft-mode by default |
| [[Determinism]] | Why two identical runs produce identical trajectories |
| [[Flags]] | Full CLI flag reference |
| [[Running the Agent]] | Which copy runs, which doesn't, and what a healthy start looks like |
| [[Open Questions]] | Rough edges worth a decision |

## Folder layout

Two copies of the same agent live here:

| path | state |
|---|---|
| `run_agent.py`, `config.json`, `run.ps1`, `memory/` at the root | **not runnable** — imports resolve outside this folder |
| `standalone/agents/8b/` + `standalone/harness/` | **complete** — the runnable copy, harness included |

See [[Running the Agent]] for why. `standalone/harness/` is the interesting
reading: ~2,100 lines across eleven modules, and the only place the actual loop
behaviour is defined.

## Vault layout

- `notes/` — the conceptual notes above
- `runs/` — one note per interesting run; start from `templates/Run Log`
- `README.md` — the original project README, kept as-is. It documents the
  design faithfully but predates some of the code; where the two disagree,
  these notes follow the source and say so.
