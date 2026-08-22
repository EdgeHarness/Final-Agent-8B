---
tags: [tools, safety, mcp, howto]
cssclasses: [topic-safety]
---

# Real Accounts

Gmail, Outlook and Teams, reached through off-the-shelf MCP servers. Off by
default; `--mcp` turns it on.

    python3 agents/8b/run_agent.py --mcp gmail,ms365 "Draft a reply to the budget thread"
    python3 agents/8b/run_agent.py --mcp-help        <- what each server needs
    python3 agents/8b/run_agent.py --mcp NAME --mcp-list   <- what the model will see

Full operational guide: [mcp/README.md](../mcp/README.md).

## The missing half

[[MCP Bridge|mcp_bridge.py]] could already speak MCP. What it had no way to be
told was *which servers to start* — nothing in the repo imported it. The gap was
never the protocol; it was configuration, call sites, and knowing which servers
are worth pointing at.

| piece | does |
|---|---|
| [mcp/servers.json](../mcp/servers.json) | the registry — data, not code. Adding a provider never touches the harness |
| [harness/mcp_config.py](../harness/mcp_config.py) | names → launchable configs. Command resolution, `~`/`${VAR}` expansion, the tool-count guard |
| `--mcp` in [[Running the Agent|run_agent.py]] and `webui/runner.py` | the call sites |
| [mcp/selftest_server.py](../mcp/selftest_server.py) | a fake mailbox, so the wiring is testable with no credentials |

## What it costs

Inference is still local — the loopback assertion holds and no prompt leaves the
machine. **The tools are the departure**: a Gmail call goes to Google, an Outlook
call to Microsoft. Don't pass `--mcp` during a demo whose claim is that nothing
leaves the box.

## Safety posture

Draft mode is the default and it is stronger than a permission check: tools that
transmit to a person are **never shown to the model**. Then every write is
confirmed, and a decline is terminal. See [[MCP Bridge#Safety three guards, all on by default]].

Two things that surprise people:

- **Teams is read-only in draft mode.** Teams has no draft concept, so every way
  to reach a person is a transmit tool and all of them are dropped. Posting
  needs `--mcp-live`.
- **The transmit guard is a regex over tool names.** `--mcp-list` prints the
  read/write classification the model will actually get. Run it against any
  server you add; the registry already carries a `write_tools` override because
  the classifier is wrong about `modify_*`.

## Tool count is the real constraint

An 8B at `num_ctx` 8192 holds every tool spec in its system prompt. The Microsoft
server ships **300+ tools**. Injecting them doesn't error — it quietly spends the
[[Harness Profiles|call budget]] choosing between near-identical options. The
registry pins `--preset mail,calendar`, and `mcp_config.count_warnings()` warns
past 25 tools. This is the same reason [[Real-Computer Mode]] drops the simulated
office tools: two plausible tools for one job is how a small model gets lost.

## Verified

`python3 -m mcp.test_bridge` — 22 assertions against the real bridge and a real
subprocess: draft mode drops send/reply/login, a decline raises, `modify_mail` is
a write only via the override, live mode exposes send, the simulated inbox is
removed. All passing.

End-to-end on llama3.1:8b against the fake mailbox: read inbox → read the right
thread → draft the right reply → `done`. 14 calls, 33s, `finished cleanly: True`.
At a 12-call budget the same run drafts correctly but wanders before finishing —
mail work needs the wider budget, which is why `--mcp` raises it to 40 the way
`--root` does.

## Plan

Phase 1 (done) is other people's servers behind our safety layer. Phase 2 is
replacing them with first-party ones, worst-first: `gmail` (upstream archived
March 2026), then `gcal`, then the Microsoft ones last. The registry resolves
`python3` to the running interpreter, so a server in `mcp/servers/` drops in with
no harness change.

## Known gaps

- **stdio only.** Google's *official* Gmail MCP server is remote HTTP and can't
  be used without an HTTP transport or a proxy. The community stdio servers
  sidestep it.
- **Teams tenant policy.** Blocked tenants need an own Azure app registration
  and admin consent for `Chat.*`. Not a code problem.
- **Windows.** Command resolution handles `npx.cmd`, but the npx servers have
  not yet been run on the Snapdragon box.

## Related

- [[MCP Bridge]] — the protocol layer this configures
- [[Real-Computer Mode]] — the same enable/confirm/WRITE_TOOLS shape, for files
- [[Tools]] · [[Flags]] · [[Architecture]]
