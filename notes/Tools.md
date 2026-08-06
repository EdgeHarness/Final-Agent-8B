---
tags: [tools]
---

# Tools

`TOOLS` in [tools.py:20](../standalone/harness/tools.py#L20) is a plain dict.
Each entry carries `desc`, `params` as `{name: (type_description, required)}`,
an `example` call, and a `run` lambda. Both [[Raw vs Harness|loops]] share it;
the raw prompt renders the docs *without* the examples, the harness prompt *with*.

## The 14 simulated-office tools

| tool | required args |
|---|---|
| `list_emails` | — |
| `read_email` | `id` |
| `send_email` | `to`, `subject`, `body` |
| `list_events` | — (`date` optional) |
| `add_event` | `title`, `date`, `start_time`, `end_time` (+ `attendees`, `location`) |
| `send_message` | `to`, `text` |
| `set_reminder` | `text`, `date`, `time` |
| `create_presentation` | `filename`, `slides` |
| `create_spreadsheet` | `rows`, `filename` (+ `sheet_name`) |
| `read_spreadsheet` | `filename` |
| `think` | `thought` |
| `save_memory` | `fact` |
| `recall_memories` | `query` |
| `done` | `summary` |

`create_presentation` and `create_spreadsheet` write **real** files via
`python-pptx` / `openpyxl` into `workspace/files/` — a slide is
`{"title": str, "bullets": [str, ...]}`, a first slide without bullets becomes a
title slide, and a cell string beginning with `=` becomes a live Excel formula.
Everything else is simulated against `workspace/state.json`
([[Persistent State]]).

Two tools are special-cased outside the registry: `done` has `run: None` and is
handled by the [[Agent Loop#Finish|loop]], and `think` returns a fixed string and
is exempt from the repeat budget.

`recall_memories` searches with `k=5`, wider than the `k=3` the harness
auto-injects — an explicit lookup should out-reach the automatic one.

## Which tools count as writes

The [[Agent Loop#Repeat budget — not a hard dedupe|repeat budget]] treats these
as world-changing ([agent.py:356](../standalone/harness/agent.py#L356)):

`send_email` · `add_event` · `send_message` · `set_reminder` ·
`create_presentation` · `create_spreadsheet` · `save_memory`

`fs_tools.WRITE_TOOLS` and the [[MCP Bridge]]'s equivalent are merged in via
`EXTRA_WRITE_TOOLS` when enabled.

## Real files (`--root`)

[[Real-Computer Mode]] adds `list_dir`, `read_file`, `write_file`,
`append_file`, `delete_path`, `move_path`, `search_files` — plus `run_command`
with `--shell`. The office tools are **dropped**
(`fs_tools.restrict_to_files()`, [run_agent.py:150](../run_agent.py#L150)) — a
fake inbox is a known distraction for a small model doing real work.
`--with-office` keeps both sets. The meta tools (`think`, `save_memory`,
`recall_memories`, `done`) survive either way.

## Errors are observations

`execute()` ([tools.py:173](../standalone/harness/tools.py#L173)) never raises:
`ToolError` becomes `ERROR: <message>`, a `KeyError` becomes
`missing required parameter 'x'`, and any other exception is caught so a tool
bug cannot kill the episode. Every attempt — successful or not — is appended to
`world.actions`, which is what the [[Agent Loop#Finish|verifier]] later reads.

## Related

- [[Agent Loop]] — how a call is parsed, repaired and dispatched
- [[Persistent State]] — where the side effects land
