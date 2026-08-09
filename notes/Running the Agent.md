---
tags: [howto]
---

# Running the Agent

## Two copies, one of them runnable

[run_agent.py](../run_agent.py) computes its import root as
`dirname(dirname(HERE))` ([run_agent.py:36-38](../run_agent.py#L36-L38)) — it
expects to sit at `<project>/agents/<size>/` with `<project>/harness/` beside it.

| copy | resolved project root | `harness/` there? |
|---|---|---|
| `./run_agent.py` | `/Users/sharv/Documents/Work` | **no** — imports fail |
| `./standalone/agents/8b/run_agent.py` | `./standalone` | **yes** |

The two runners are byte-identical (`diff` is clean), as are the configs. Only
the position in the tree differs. **Run the `standalone/agents/8b/` copy**; treat
the root-level files as a stray flat copy, or delete them.

## Invoking it

As shipped ([run.ps1](../run.ps1)) it targets a Windows lab machine and a pinned
interpreter:

```powershell
& "C:\Users\Lab User\SAIL\python\python.exe" (Join-Path $PSScriptRoot "run_agent.py") @args
```

```powershell
cd standalone\agents\8b
.\run.ps1 "Find a free hour on Thursday and book it as Deep work"
```

On this Mac, skip `run.ps1` and call the runner directly:

```bash
cd standalone/agents/8b
python3 run_agent.py "Find a free hour on Thursday and book it as Deep work"
python3 run_agent.py            # interactive prompt
```

Prerequisites: Ollama serving on `127.0.0.1:11434` with `llama3.1:8b` pulled,
`requests`, plus `python-pptx` and `openpyxl` for the document [[Tools|tools]].
`--shell` invokes PowerShell and will not work here; everything else is
portable. Paths in the [[Real-Computer Mode|deny-list]] are Windows-shaped too,
so on macOS that layer protects nothing — the root scope still holds.

## The easy way: [[Agent Lab]]

```bash
./"Agent Lab.command"
```

Opens a local web console — pick the agent, pick an installed model, type a
task, watch it run, and click the generated `.pptx` / `.xlsx` to view them in
the browser. Nothing below is required for a demo.

## Without Ollama

On the [[Snapdragon X Elite|Yoga]], `llama-server` replaces Ollama outright —
Ollama is a wrapper around llama.cpp, so this removes a layer rather than adding
one. Stop Ollama first; it owns port 11434.

```powershell
.\serve-xelite.ps1 -Bin ... -Model ...\Meta-Llama-3.1-8B-Instruct-Q4_0.gguf
python ollama_shim.py                       # :11434 -> :8080
cd standalone\agents\8b ; python run_agent.py "..."
```

Build and flag rationale: [[llama.cpp Backend]]. Translation details and the
[[Ollama Shim#The sharp edge: tiers collapse|--tiers caveat]]: [[Ollama Shim]].

## Startup banner

A healthy run prints, before any model call:

```
[Agent 8B] fully on-device via http://127.0.0.1:11434
  harness profile: balanced — 5-step plan, 2 verify round(s), loop-break on, out<=700 tok, ctx 8192
    why: A strong general 8B with good instruction-following and JSON. ...
  model: llama3.1:8b
  budget: 20 LLM calls
```

Those numbers come from the `llama3.1:8b` entry in
[profiles.py:119-126](../standalone/harness/profiles.py#L119-L126) — see
[[Harness Profiles]]. If the endpoint is not loopback the runner asserts out
before any of it ([run_agent.py:129](../run_agent.py#L129)).

## What to expect at 8B

Tens of seconds per step on CPU — usable, not interactive. A 4-step task is a
couple of minutes; budget accordingly before starting something with `--root`
and a 40-call ceiling.

Multi-step office tasks — read an email, extract the numbers, build the deck,
reply — are within reach and are roughly where the ceiling sits for anything
you want done unattended.

## Related

- [[Flags]] · [[Persistent State]] · [[Open Questions]]
