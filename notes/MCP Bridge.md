---
tags: [tools, safety, mcp]
cssclasses: [topic-safety]
---

# MCP Bridge

[mcp_bridge.py](../harness/mcp_bridge.py), ~380 lines — the protocol
layer. It was written before anything called it; [[Real Accounts]] is the
configuration and the call sites that turned it on.

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

`bench/` never imports it, so the simulated registry and the
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

## Two accounts, one tool name

`ms365` and `ms365-personal` ship the same `outlook_` prefix and an identical
ten-entry allow list. Connecting a work mailbox and a personal one therefore
collided on all ten names, and the old fallback qualified the loser with its
server id: `outlook_list-mail-messages` beside
`ms365-personal_list-mail-messages`. Twenty tools for ten operations, and the
model had to learn two unrelated names for one thing.

The bridge now treats that case as **several providers of one capability**
rather than a name clash, which is what Cordis §6.2 calls a service broker as
against exclusive binding. The second provider joins the first behind the
existing name, and the tool grows a required `account` argument naming the
connected mailboxes.

Measured on the real bridge, with the selftest server enabled twice:

| | tools | tool-doc block |
|---|---|---|
| one provider | 4 | +772 chars |
| two, exclusive binding | 8 | +1648 chars (2.13x) |
| two, brokered | 4 | +1136 chars (1.47x) |

Half the tool count, which is the number an 8B is most sensitive to. The
residual 1.47x is the `account` line itself, and it is why the account list is
named **once** on the parameter and not repeated in the description: printing it
twice ate most of what brokering saved.

> [!warning] `account` is required, deliberately
> With two mailboxes behind one name there is no safe default. A silent choice
> is merely confusing for a read and outright wrong for an emission, so an
> omitted or unknown `account` refuses and names the options instead of
> picking one. Cordis calls this an explicit target named by the consumer.

A broker only ever appears on collision, so single-provider setups keep exactly
the tools and signatures they had. A clash with a *base* harness tool is still
a clash, not a provider, and still qualifies with the server id: only tools this
module injected can broker. Where two providers disagree on effect class, the
most dangerous one wins, so the guards follow the worse case rather than
whichever server was connected first.

## Related

- [[Real Accounts]] — the registry, the `--mcp` flag, and which servers to use
- [[Real-Computer Mode]] — the same enable/confirm/WRITE_TOOLS shape
- [[Tools]] · [[Architecture]]
