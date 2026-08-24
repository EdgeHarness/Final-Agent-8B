# Agent 8B

> **Shipping instance.** Engine development moved to
> [Brick-Agent-Harness](https://github.com/EdgeHarness/Brick-Agent-Harness)
> on 2026-08-23; this repository is its Snapdragon deployment. See
> [UPSTREAM.md](UPSTREAM.md) for what moved where and what stays here.

A local agent harness. An 8B model runs on this machine, drives a set of tools,
and is checked by a loop that plans before it acts and verifies before it stops.
Inference, files, memory and state stay on the device; the runner asserts its
model endpoint is loopback and refuses anything else.

The claim the project exists to test:

> The model is not the agent. The model is one component inside a loop that
> supplies the structure, the checking, and the memory.

`harness/agent.py` holds two loops over the same tools and the same call budget
— `run_raw()`, which is what you get wiring a model to tools naively, and
`run_harness()`, the same skeleton plus the scaffolding below. The experiment
varies only the scaffolding around the model. That constraint is why parts of
this codebase look over-careful.

---

## Start it

Two backends. **Both own port 11434, so never run both.**

### macOS and Linux

```sh
pip install requests python-pptx openpyxl   # the harness will not import without them
python3 -m webui.server                     # Agent Lab at http://127.0.0.1:8765
```

Or double-click `Agent Lab.command`, which installs those packages on first
run, starts Ollama if it is not already up, and opens the lab.

Headless:

```sh
python3 -m bench.run --list                 # the graded tasks and arms
python3 -m tests.test_harness               # the suite; stdlib only, no pytest
```

`make` is **not** an option here: the Makefile sets `SHELL := powershell.exe`
and its `doctor` target reads Snapdragon hardware through CIM. It is for the
lab machine.

### Windows, on the X Elite

```powershell
winget install --id ezwinports.make    # make is not installed by default

make doctor        # toolchain, hardware, and what is currently listening
make ollama-up     # CPU backend
make lab           # Agent Lab in a window
```

Or headless, and without make:

```powershell
cd agents\8b
.\run.ps1 "Find a free hour on Thursday and book it as Deep work"
```

On the Hexagon NPU instead, through Qualcomm's GenieX runtime:

```powershell
make npu-pull      # fetch the model bundle, pre-compiled for X Elite
make npu-up        # geniex serve on :18181, OpenAI API
make shim          # Ollama-API shim on :11434, so the harness is unchanged
make lab
```

The shim is the whole NPU integration: the harness only ever talks to
`OLLAMA_URL /api/chat`, so translating that to `/v1` is the entire job. No agent
code, no loop behaviour, no UI changes. See
[notes/NPU Serving.md](notes/NPU%20Serving.md).

**Prerequisites are not optional.** `requests`, `python-pptx` and `openpyxl`
are imported at module scope by `harness/office.py`, which every other module
reaches through `harness/tools.py`, so without them nothing imports at all,
including the test suite. `make pydeps` installs them on Windows; elsewhere use
the pip line above. Both launchers (`Agent Lab.ps1`, `Agent Lab.command`)
install them on first run and start the backend for you.

Python 3.9 is enough: the sources compile clean on stock macOS Python.

---

## What is here

| path | what |
|---|---|
| `harness/` | the loop, the tool registry, the safety layers — the only place loop behaviour is defined |
| `bench/` | the evaluation rig: graded tasks, and one arm per guard so an ablation is a number |
| `agents/8b/` | the agent: its config, runner, workspace, memory and run logs |
| `webui/` | Agent Lab, a loopback console that shows the loop working |
| `mcp/` | the real-account server registry, and a self-test that needs no credentials |
| `npu/` | the Ollama-API shim in front of GenieX |
| `tests/` | the harness test suite |
| `notes/` | the working vault: design reasoning, written for Obsidian |

```powershell
python -m tests.test_harness    # the harness suite; stdlib unittest, no pytest
python -m mcp.test_bridge       # the MCP safety guarantees, no credentials needed
```

---

## The loop

One tool call per model reply, JSON only.

```mermaid
flowchart TD
    T([task]) --> MEM["inject matching long-term<br/>memories into the prompt"]
    MEM --> PLAN["plan: tool names only<br/>invalid names dropped"]
    PLAN --> CALL["model reply<br/>format=json, one tool call"]
    CALL --> PARSE{parses?}
    PARSE -- no --> FB["corrective feedback<br/>(a repeated bad reply is<br/>deleted from context)"]
    FB --> CALL
    PARSE -- yes --> ISDONE{"done()?"}

    ISDONE -- no --> REPAIR["repair and normalize args:<br/>near-miss names renamed,<br/>unknown dropped,<br/>tomorrow -> YYYY-MM-DD"]
    REPAIR --> CHECKS["cross-checks, in order:<br/>params valid<br/>date agrees with the task (writes only)<br/>write named by the plan<br/>a named file was opened first<br/>planned read before writing<br/>no identical call vs an unchanged world"]
    CHECKS -- "unplanned write,<br/>after a read" --> REPLAN["revise the plan once:<br/>a plan written before<br/>reading cannot name<br/>what the data requires"]
    REPLAN --> CALL
    CHECKS -- questioned --> FB
    CHECKS -- ok --> EXEC["execute the tool<br/>OBSERVATION into context"]
    EXEC --> CALL

    ISDONE -- yes --> ECHO{"summary repeats an<br/>earlier answer?"}
    ECHO -- yes, once --> FB
    ECHO -- no --> VERIFY{"verifier: requirements vs<br/>actions and their results"}
    VERIFY -- "incomplete:<br/>gap quoted" --> FB
    VERIFY -- "complete, or<br/>errored: fail open" --> FIN(["episode ends<br/>world snapshotted<br/>(even on crash or Stop)<br/>unrequested side effects reported"])
```

Every box above is paid out of the same call budget as the work itself, and
every arrow into *corrective feedback* is a question, not a block: a call the
model repeats after being questioned is allowed to run.

**Plan.** One call asks for a tool-grounded plan. Steps naming a tool that does
not exist are dropped, and the plan re-enters as short numbered guidance. The
plan *request* is popped from the context, so the model never sees its own
planning prose again — free-form prose is never allowed to become an instruction
the model then obeys.

**Act.** Decode under `format=json`, parse strictly, then repair: near-miss
parameter names are renamed onto the required ones, unknown parameters dropped,
dates and times normalized against the clock. Arguments are validated *before*
execution, and the failure message quotes the tool's own worked example rather
than describing a schema — showing a small model the right shape beats telling
it. Then the cross-checks: a date the model wrote itself is compared against the
date the task names, so "Wednesday" cannot become a Monday unnoticed (on writes
only — a read with a mismatched date is the model looking around). A write the
plan never proposed is questioned once. And a document write is questioned once
when something the agent *read* names a file that exists here and it never
opened it: writing from memory while the task's own data sits on disk is the
failure this harness exists to catch.

**Replan.** The plan is written before the agent has read anything, so on a task
whose requirements live in the data ("read this email and do what it asks") it
cannot name the work. Once a read has landed, an unplanned write spends one call
revising the plan instead of being held to it. Only once: a model that could
replan on every surprise could rewrite its way to anything.

**Finish.** When the model calls `done`, a verifier re-reads the task against
the actions actually taken *and their results* — so it can see that the file it
is about to demand already exists — and answers
`{"complete": bool, "missing": str, "unrequested": str}`. If incomplete, `done`
is rejected and the gap is quoted back. On a verifier error it fails open rather
than trapping the agent. At 8B this is the single highest-value piece of
scaffolding: the model will happily call `done` with the last clause of a
three-part task unaddressed.

`unrequested` names any write the task never asked for. Nothing is undone — a
sent message cannot be unsent, and auto-reverting would be a larger side effect
than the one reported — so it is surfaced for the person who asked to judge.
Before the verifier runs, a `done` summary that copies an eight-word span out of
an earlier turn in the same conversation is questioned once: left alone it
compounds, because the summary is stored and becomes the next turn's context.

**Repetition.** A repeated exchange sitting in the context is itself the
attractor pulling the model back into a loop, so the harness deletes the older
copy of the exchange before restating the task.

**Budget honesty.** Plan, verify and every repair round are paid out of the same
call counter as ordinary tool calls. The scaffolding does not get free turns.

**What a tool declares.** The loop asks the registry rather than carrying lists
of tool names, so a domain gets the cross-checks by declaring facts about its
own tools:

| key | means |
|---|---|
| `effect` | `read`, `revertible_write`, `withheld_emission` or `unrecoverable_emission`. Required; an undeclared tool counts as world-changing |
| `opens` | extensions this tool can read, e.g. `(".xlsx",)` |
| `writes_file` | this tool produces a file |
| `lists_files` | this tool enumerates a directory, so its result is not the task naming a file |
| `simulated_connector` | this tool stands in for something a real account replaces, so MCP mode drops it |

**What a new domain has to provide.** The loop needs four things from a world:
`actions`, `file_names()`, `snapshot()` and `log()`. That list is measured
rather than designed — they are the only members `harness/agent.py` and the
execution layer touch — and `harness/world.py` names it as `WORLD_CONTRACT`.
Everything else on `World` is the simulated office, reached only by that
domain's tools. A test drives a real episode against a world implementing the
four and nothing else, so the claim is checked by running rather than by
reading.

Detail: [notes/Agent Loop.md](notes/Agent%20Loop.md) ·
[notes/Harness Repair.md](notes/Harness%20Repair.md) ·
[notes/Raw vs Harness.md](notes/Raw%20vs%20Harness.md) ·
[notes/Defensive Patterns.md](notes/Defensive%20Patterns.md)

---

## Per-model tuning

One setting is never right for every model size, because models fail
differently. `harness/profiles.py` carries one frozen profile per size, and the
curve is not monotonic — a 1B and a 32B both get *less* scaffolding than an 8B,
for opposite reasons. At 1B the mistakes are mechanical, so planning and
verification only starve the budget. At 32B a call costs minutes, so flailing is
the expensive failure, not stopping early.

| model | calls | ctx | plan | verify |
|---|---|---|---|---|
| `llama3.2:1b` | 18 | 8k | no | 0 |
| `llama3.2:3b` | 14 | 8k | yes | 1 |
| `llama3.1:8b` | 50 | 8k | yes | 2 |
| `qwen2.5:14b` | 14 | 12k | yes | 2 |
| `qwen2.5:32b` | 12 | 16k | yes | 1 |

The call number is a ceiling, not a target: an agent that finishes in four calls
costs four. A tight number on a small model is a loop-brake; on a model that can
follow a plan it is only a premature cut-off, which is why the 8B carries real
headroom. The GenieX NPU bundles resolve to the same profile as their Ollama
equivalents, by parameter count parsed from the tag rather than by family.

The benchmark never sets a profile; it runs the default.

**It no longer follows that graded runs are comparable with runs recorded before
2026-08-22.** Making the loop domain-neutral meant taking three office sentences
out of the system prompt, so the graded prompt is not byte-identical to what
older numbers were produced against. That was a deliberate trade, made because
those sentences were instructing every model in every domain, and it is stated
here because the previous wording promised a comparability the change removed.

Detail: [notes/Harness Profiles.md](notes/Harness%20Profiles.md)

---

## Acting on real things

Three layers, all on by default.

**Real files** (`--root PATH`) swap the simulated office for a real folder. Every
path is resolved against the root and must stay inside it; a deny-list keeps
system directories, the interpreter and the model blobs unwritable even if the
root is a drive root; overwrite, delete, move and shell each prompt for
confirmation, and a declined action returns an error telling the model not to
retry it.

**Real accounts** (`--mcp`) reach Gmail, Outlook and Teams over the Model Context
Protocol, so the harness never reimplements Graph. The default mode is `draft`:
send and forward tools are dropped by name, leaving create-draft, read and list.
**The model composes; a human sends.** Every world-changing call is still
confirmed, and per-server allow/drop lists override the name heuristic where it
guesses wrong.

`make mcp-test` asserts these guarantees without needing any credentials.

Detail: [notes/Real-Computer Mode.md](notes/Real-Computer%20Mode.md) ·
[notes/MCP Bridge.md](notes/MCP%20Bridge.md)

---

## Determinism

`temperature=0`, `seed=42`, and a simulated clock fixed at Monday 2026-07-20, so
date reasoning is reproducible. Two runs of the same task against the same state
produce the same trajectory. Real-file and real-account modes switch to the
actual date, because real mail has real dates.

Detail: [notes/Determinism.md](notes/Determinism.md)

---

## Reading further

**This README is the front door, and the source is the authority.** Where a
document and the code disagree, the code is right.

[agents/8b/README.md](agents/8b/README.md) has the agent-level detail: the
registry, what persists between runs, model tiers, every flag. It says 16 tools;
there are 17 since `list_files` was added, and the count is deliberately not
repeated here so there is only one place for it to go stale.

`notes/` is a working Obsidian vault, kept because it holds the reasoning behind
decisions the code cannot state. It is written for Obsidian, so most notes use
`[[wikilinks]]` that do not resolve on GitHub; read it in Obsidian, or follow
the direct links from the sections above.
