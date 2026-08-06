---
tags: [tools, safety, mcp]
cssclasses: [topic-safety]
---

# MCP Bridge

[mcp_bridge.py](../standalone/harness/mcp_bridge.py), 373 lines — **not
mentioned in the README**, and the largest undocumented piece of the codebase.

> This is how the agent reaches real Gmail / Outlook (and anything else with an
> MCP server) without the harness reimplementing Graph or the Gmail API.

It speaks the Model Context Protocol's stdio transport directly —
newline-delimited JSON-RPC 2.0 over a child process's stdin/stdout — so it needs
no `mcp` SDK and stays **synchronous**, matching the rest of the harness.

## Shape

Deliberately identical to [[Real-Computer Mode|fs_tools]]:

| symbol | does |
|---|---|
| `enable(servers, confirm=None, mode="draft")` | launches each server, lists its tools, adapts every one into the harness `TOOLS` spec, injects them **in this process only** |
| `WRITE_TOOLS` | the injected tools that change the world, for loop-breaking and `EXTRA_WRITE_TOOLS` |
| `shutdown()` | terminates the subprocesses (also `atexit`) |
| `mail_rules(mode)` | prompt text explaining the mode's limits to the model |

`bench/` never imports it, so the simulated 14-tool registry and the
[[Raw vs Harness]] comparison are untouched.

## Safety: three guards, all on by default

These tools act on real accounts, so:

1. **`mode="draft"` (the default)** drops send/forward/transmit tools by name
   pattern, keeping create-draft, read, list, and tentative-event tools. *The
   model composes; a human sends.* `mode="live"` allows real sends — still
   confirmed. `mode="read_only"` is the third option.
2. Every world-changing call goes through the **same `confirm(action, detail)`
   callback** `fs_tools` uses; a decline raises a `ToolError` telling the model
   not to retry.
3. Per-server **allow / drop lists** override the heuristics when a server names
   its tools in a way the name-based classifier gets wrong.

Guard 1 leans on a regex over tool names, which is the load-bearing assumption
worth watching: a server whose send tool is named something the pattern misses
would be exposed in draft mode. The per-server override exists precisely because
the author expected that to happen.

`mail_rules("draft")` also tells the model that **creating the draft *is*
completing the task** — otherwise a [[Agent Loop#Finish|verifier]] looking for
"sent" would reject a correct `done`.

## Related

- [[Real-Computer Mode]] — the same enable/confirm/WRITE_TOOLS shape
- [[Tools]] · [[Architecture]]
