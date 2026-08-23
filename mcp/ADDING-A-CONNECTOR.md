# Adding a connector

How to give the agent a new real-account capability (Slack, Notion, Jira, a
first-party server you wrote) so it appears in the Agent Lab UI and its tools
land in the harness registry.

**The short version: you add one JSON object to `servers.json`. No harness code.**

The registry is data, not code. `webui/server.py` builds the connector picker
from `mcp_config.available()`, which reads this file, so a new entry shows up in
the UI checkbox list on the next restart with nothing else touched.

---

## 1. The minimal entry

Open [servers.json](servers.json) and add a key. This is the smallest thing
that works:

```json
"slack": {
  "summary": "Slack — read channels and post messages.",
  "command": "npx",
  "args": ["-y", "@some/slack-mcp-server"],
  "prefix": "slack_"
}
```

That is enough to launch, list, and inject. Everything below is refinement.

`prefix` is not optional in practice. Without it, a server whose tool is called
`search` claims the bare name `search` in a registry shared with every other
tool. Prefix everything.

---

## 2. What each field does

**Fields the bridge acts on** (anything else is documentation and gets stripped
before launch, see `_BRIDGE_KEYS` in [../harness/mcp_config.py](../harness/mcp_config.py)):

| field | purpose |
|---|---|
| `command`, `args` | how to launch the server. Run with `subprocess.Popen`, no shell |
| `env`, `cwd` | passed through. `~` and `${VARS}` are expanded, so credential paths are not machine specific |
| `prefix` | prepended to every tool name. Use it |
| `allow` | whitelist of MCP tool names to expose. Everything else is dropped |
| `drop` | blacklist, for when a whitelist is overkill |
| `read_tools`, `write_tools` | override the write classifier. **Read section 4** |
| `arg_hints`, `hide_params` | reshape a tool's parameters for a small model |
| `mode` | `draft` / `live` / `read_only`, overriding the run's mode for this server only |

**Documentation-only fields**, which the UI does surface to the user:

| field | purpose |
|---|---|
| `summary` | one line, shown next to the checkbox in the UI |
| `setup` | list of strings, shown as setup steps. Put the OAuth dance here |
| `docs` | upstream URL |
| `notes` | why any override above exists. Future you will need this |

---

## 3. Effect classes are assigned for you, from the tool name

Every injected tool gets one of four effect classes, which is what the guards
read. For MCP tools the bridge infers it (`_effect_class` in
[../harness/mcp_bridge.py](../harness/mcp_bridge.py)):

| tool name contains | class | meaning |
|---|---|---|
| no write verb | `read` | observes only |
| `draft`, but not send/forward/reply | `withheld_emission` | composes something a human releases |
| anything else world-changing | `unrecoverable_emission` | assumed to reach another party |

Note what is missing: an MCP tool is **never** classified `revertible_write`.
From a name alone we cannot tell whether a write reaches another person, and a
calendar invite does. Guessing the recoverable class would be guessing in the
one direction that costs something.

In `draft` mode, any tool whose name matches send / forward / reply is dropped
entirely and never reaches the model.

---

## 4. The one thing that will bite you: the classifier misses writes

The write/read split is a regex over the tool name (`_WRITE_RE`). It knows verbs
like send, create, delete, update, move. It does **not** know every verb a server
might use.

Real example already in the file: Gmail's `modify_email` contains no verb the
regex recognises, so without an override it would be exposed as **read-only and
skip confirmation**, despite changing a real mailbox.

So, for every tool your server exposes, ask: *does this change anything?* If yes
and the name lacks an obvious write verb, add it:

```json
"write_tools": ["modify_email", "batch_modify_emails", "download_attachment"]
```

`read_tools` is the opposite override, for a false positive. `get-mailbox-settings`
matches "set" inside "settings" and is only a read.

**Get this wrong in the read direction and a world-changing tool runs without
confirmation.** It is the highest-risk field in the entry. Write a `notes` entry
saying why each override exists.

---

## 5. Watch the tool count

An 8B at `num_ctx 8192` carries the entire tool list in its system prompt. A
server that injects 60 tools does not fail loudly, it quietly makes the agent
stupid, because the model starts picking tools at random.

`TOOL_BUDGET_WARN` is 25 and `count_warnings()` flags a run before it starts.

Measured, not guessed: the ms365 server returns **69 tools** even with
`--preset mail,calendar`. That is why its entry has a ten-name `allow` list.

Use the server's own preset flag first, then `allow` to cut the rest. Derive the
list from real `--mcp-list` output, never from the upstream docs.

---

## 6. Verify it, in this order

**a. List the tools without running an agent.** This launches the server, prints
what it exposes after filtering, and exits:

```bash
python3 agents/8b/run_agent.py --mcp slack --mcp-list
```

Check three things: the names are prefixed, the count is under budget, and every
transmitting tool is absent in draft mode.

**b. Confirm the safety guarantees still hold.** This uses the fake mailbox, no
credentials and no network:

```bash
python3 -m mcp.test_bridge
```

**c. Run the suite.**

```bash
python3 -m tests.test_harness
```

**d. Look at it in the UI.** Start the lab, open Run options, and confirm your
connector appears with its summary and setup notes.

```bash
python3 -m webui.server
```

---

## 7. Two accounts of the same service

If you add a second entry for the same provider (a work and a personal mailbox),
they will collide on every tool name. That is handled: the second provider joins
the first behind one tool name, and the tool gains a required `account`
argument naming which one to use.

You do not configure this. It happens on collision. Just be aware that the model
must then name an account on every call, because two mailboxes behind one name
have no safe default.

---

## 8. When you actually do need code

Only two cases:

**You are writing the server itself.** Use
[selftest_server.py](selftest_server.py) as the template. It is a complete MCP
server in one stdlib file, speaks JSON-RPC 2.0 over stdio, and needs no
dependencies. Point a registry entry at it with `"command": "python3"` and
`"args": ["-m", "mcp.your_server"]`.

**The server's argument shapes defeat the model.** Some servers take a whole
API entity under one `body` argument with 25 top-level keys. `arg_hints` and
`hide_params` exist for that, and the ms365 entry is the worked example. Read
the shapes off a live `--mcp-list`, not the vendor docs, because they disagree.

---

## Checklist

- [ ] entry added to `servers.json` with `summary`, `command`, `args`, `prefix`
- [ ] `setup` steps written, including any OAuth dance
- [ ] tool count under 25 after `allow`, verified with `--mcp-list`
- [ ] every world-changing tool with a non-obvious name listed in `write_tools`
- [ ] `notes` explaining each override
- [ ] `--mcp-list` shows no transmitting tools in draft mode
- [ ] `python3 -m mcp.test_bridge` passes
- [ ] `python3 -m tests.test_harness` passes
- [ ] connector visible in the Agent Lab Run options panel

## Related

- [README.md](README.md) for setup, safety and known gaps
- [../notes/MCP Bridge.md](../notes/MCP%20Bridge.md) for how the bridge works internally
