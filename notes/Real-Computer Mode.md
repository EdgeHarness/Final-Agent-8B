---
tags: [tools, safety]
cssclasses: [topic-safety]
---

# Real-Computer Mode

`--root` swaps the fake office for real files under one folder, Codex /
Claude-Code style. [fs_tools.py](../standalone/harness/fs_tools.py), 322 lines,
opt-in and **not part of the benchmark**.

```powershell
.\run.ps1 --root "C:\Users\Lab User\Desktop\sandbox" "Tidy these notes into folders"
.\run.ps1 --root . --shell "What changed in this project today?"
```

Tools added: `list_dir`, `read_file`, `write_file`, `append_file`,
`delete_path`, `move_path`, `search_files`, and with `--shell`, `run_command`.
The simulated office [[Tools|tools]] are dropped unless `--with-office`.

The module docstring states the threat model plainly:

> A 1B model that scores 0.3 on "put the right number in a spreadsheet" will
> eventually issue a wrong `delete_path`. Choose root accordingly.

## Extra rules injected

The runner appends `REAL_RULES` to the system prompt
([run_agent.py:49-57](../run_agent.py#L49-L57)):

- **Look before you write** — call `list_dir` or `read_file` first, so you
  change the file that actually exists instead of one you assumed.
- Never delete or overwrite anything the task did not ask you to change.
- A declined confirmation is final — do not retry it, choose another approach.

## Three layers of guardrail

**1 — Scope.** `_resolve()`
([fs_tools.py:56](../standalone/harness/fs_tools.py#L56)) expands `~` and
`%VAR%`, strips quotes, joins against the root, takes `abspath`, and *only then*
checks containment with `_within()`. Resolving first and checking after is the
part that matters — it is what makes `..\`, absolute paths and variable
expansion land inside the sandbox rather than around it. An absolute path is not
rejected outright; `os.path.join` returns it unchanged and the containment check
decides.

**2 — Deny-list.** `_DENY_WRITE`
([fs_tools.py:36](../standalone/harness/fs_tools.py#L36)) is never writable even
if the root is a drive root: `%SystemRoot%`, both `Program Files`, the Ollama
model blobs, the Python interpreter running the agent, the live `results\`, and
the agent's own `harness\`. Reads are unaffected — this is a write guard only.

> [!warning] The deny-list is Windows-shaped
> Every entry is a hard-coded `C:\Users\Lab User\SAIL\…` path or a Windows
> environment variable. On macOS none of them match anything, so layer 2 is
> inert and the root scope is doing all the work. See [[Open Questions]].

**3 — Confirmation.** Overwrite, delete, move and shell each go through the
runner's `y/N` prompt ([run_agent.py:118-123](../run_agent.py#L118-L123)). A
decline raises a `ToolError` phrased *at the model*: "the user declined the
{action}. Do not retry it; choose another approach." `--yolo` passes
`confirm=None`, which makes `_ask()` return `True` unconditionally.

Output is clipped throughout — 200 KB read cap, 4,000-character observations,
300 directory entries, 60-second command timeout.

## Clock switch

`--root` also swaps the fixed benchmark clock for the real system date
([run_agent.py:155-157](../run_agent.py#L155-L157)) — a real-file agent should
reason about today, not about 2026-07-20. This is the one place real mode gives
up [[Determinism|reproducibility]], deliberately.

## Budget

Root mode lifts the [[Harness Profiles|profile]] budget to a floor of **40**,
so a model given a tight budget for the simulated office gets room to look
before it writes. The 8B already carries 50 and keeps it. At 8B on CPU that is
a long wall-clock commitment either way.

## Related

- [[Flags]] · [[Tools]] · [[MCP Bridge]] · [[Determinism]]
