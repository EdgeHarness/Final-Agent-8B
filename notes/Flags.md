---
tags: [reference]
---

# Flags

Parsed in `parse_flags()` ([run_agent.py:60-96](../run_agent.py#L60-L96)).
Everything not recognised as a flag is joined with spaces and becomes the task.

| flag | effect |
|---|---|
| `--root PATH` | enable real-file tools, scoped to PATH → [[Real-Computer Mode]] |
| `--shell` | also allow `run_command` (PowerShell), still confirmed |
| `--yolo` | skip confirmation prompts |
| `--tiers` | route model calls through the tiered router → [[Model Tiers]] |
| `--small TAG` | cheaper model for routing/verify (implies `--tiers`) |
| `--deep TAG` | on-demand heavy tier (implies `--tiers`) |
| `--with-office` | keep the simulated office tools alongside the file tools |
| `--max-calls N` | LLM call budget (default: the model's profile — **50** at 8B — lifted to at least 40 with `--root`) |

## Notes

- With no task on the command line the runner prompts interactively
  ([run_agent.py:139-143](../run_agent.py#L139-L143)); an empty answer exits.
- `--root` and `--shell` also read from [config.json](../config.json) as `root`
  and `allow_shell`; the flag wins.
- `--small` and `--deep` each set `tiers` implicitly.
- `--root` overrides the [[Harness Profiles|profile]] budget for every model
  size, not just this one.
- Unknown flags are **not rejected** — they silently become part of the task
  string. A typo'd `--tier` ends up in the prompt. So does a bare `--root` with
  no path following it.

## Related

- [[Running the Agent]] · [[Harness Profiles]] — budget precedence
