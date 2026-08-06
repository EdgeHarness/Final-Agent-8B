---
tags: [architecture]
cssclasses: [topic-core]
---

# Architecture

```
run.ps1
  └─ run_agent.py            config, flags, state paths, banner
       ├─ harness/llm.py         Ollama client (temp 0, seed 42, usage counters)
       │   or model_router.py    tiered variant, one model resident (--tiers)
       ├─ harness/world.py       simulated office: inbox, calendar, messages,
       │                         reminders — persisted to workspace/state.json
       ├─ harness/office.py      REAL .pptx / .xlsx writing (python-pptx, openpyxl)
       ├─ harness/fs_tools.py    REAL file tools, opt-in via --root
       ├─ harness/mcp_bridge.py  REAL MCP servers as tools, opt-in
       ├─ harness/memory.py      long-term memory (JSONL + keyword retrieval)
       ├─ harness/profiles.py    per-model harness tuning
       ├─ harness/tools.py       the tool registry + validation
       └─ harness/agent.py       run_raw() and run_harness(): the two loops
```

Source: [standalone/harness/](../standalone/harness/) — see [[Running the Agent]]
for why there are two copies of the agent folder.

## What the runner owns

[run_agent.py](../run_agent.py) is a thin shell, byte-identical across every
model-size folder; only [config.json](../config.json) differs. It:

1. reads the config and asserts the Ollama URL is local
   ([run_agent.py:129](../run_agent.py#L129))
2. resolves the [[Harness Profiles|profile]] for the model and installs it
   ([run_agent.py:133-135](../run_agent.py#L133-L135))
3. parses [[Flags|flags]] and settles the LLM call budget
4. opens `workspace/` as a **persistent** [[Persistent State|world]] and
   `memory/memory.jsonl`
5. builds a plain `LLM` or a tiered [[Model Tiers|ModelRouter]]
   ([run_agent.py:99-115](../run_agent.py#L99-L115))
6. calls `run_harness(llm, world, mem, task)`
7. prints what happened and writes `logs/run_NNN.json`

## The seam: module-level configuration

The runner does not pass options down — it *sets globals* on `harness.agent`:

| global | set when | effect |
|---|---|---|
| `PROFILE` | always, via `set_profile()` | every tuning knob ([[Harness Profiles]]) |
| `MAX_CALLS` | always | the shared budget for plan, act, repair and verify |
| `EXTRA_RULES` | `--root` | appends real-file rules to the system prompt |
| `EXTRA_WRITE_TOOLS` | `--root` | teaches loop-breaking which new tools write |
| `SIM_TODAY` / `SIM_TODAY_HUMAN` | `--root` | swaps the fixed clock for today |

That is what lets one runner serve five model sizes and two worlds. It is also
the sharpest edge in the design: the harness is effectively a singleton, so one
process runs one agent. Fine for a CLI, a blocker for anything concurrent.

The same pattern appears as opt-in hooks — `llm.STREAM_HOOK`,
`agent.EVENT_HOOK`, `tools.TOOL_HOOK` — all `None` by default so the
[[Raw vs Harness|benchmark]] path stays untouched, and set by the web UI to
watch a run live.

## Design rule visible throughout

Every extension is bolted on *outside* the graded core.
[fs_tools.py](../standalone/harness/fs_tools.py) and
[mcp_bridge.py](../standalone/harness/mcp_bridge.py) inject their tools into the
shared registry **in that process only**, and `bench/` imports neither — so
raw-vs-harness stays comparable with runs already on disk. The benchmark is the
fixed point; the agents are the variations.

## Related

- [[Agent Loop]] · [[Tools]] · [[Determinism]] · [[Raw vs Harness]]
