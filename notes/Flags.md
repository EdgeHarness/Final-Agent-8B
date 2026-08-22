---
tags: [reference]
---

# Flags

Parsed in `parse_flags()` ([run_agent.py:76-128](../agents/8b/run_agent.py#L76-L128)).
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
| `--max-calls N` | LLM call budget (default: the model's profile — **50** at 8B — lifted to at least 40 with `--root`/`--mcp`) |
| `--mcp LIST` | comma-separated servers from `mcp/servers.json` → [[Real Accounts]] |
| `--mcp-live` | allow send/reply tools; the default is draft → [[MCP Bridge]] |
| `--mcp-read-only` | drop every world-changing MCP tool |
| `--mcp-list` | start the named servers, print their tools, exit |
| `--mcp-help` | print setup steps for every known server, exit |

## Notes

- With no task on the command line the runner prompts interactively
  ([run_agent.py:224-228](../agents/8b/run_agent.py#L224-L228)); an empty answer exits.
- `--root` and `--shell` also read from [config.json](../agents/8b/config.json) as `root`
  and `allow_shell`; the flag wins.
- `--small` and `--deep` each set `tiers` implicitly.
- `--root` overrides the [[Harness Profiles|profile]] budget for every model
  size, not just this one.
- Unknown flags are **not rejected** — they silently become part of the task
  string. A typo'd `--tier` ends up in the prompt. So does a bare `--root` with
  no path following it.

## Related

- [[Running the Agent]] · [[Harness Profiles]] — budget precedence
