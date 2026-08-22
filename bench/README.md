# bench/

The instrument. Four graded tasks, six arms, one number per cell.

```sh
python -m bench.run --list                       # arms and tasks, run nothing
python -m bench.run --model llama3.2:1b          # everything, once
python -m bench.run --arms raw harness --repeat 3
python -m bench.run --tasks receipts_sheet --out results.json
```

## What an arm is

`raw` is a model wired to tools with no scaffolding. `harness` is the full
loop. `harness-no-<guard>` is the full loop with exactly one cross-check
removed, one arm per registered guard.

That last shape is the point. Until the guards became a named list they were
inline statements, and "did that guard help?" could only be answered by
reading. It is a number now, and an arm appears automatically for any guard
someone adds.

## What a grader reads

**The final world, never the transcript.** The transcript is what the model
claims it did; the world is what happened. Every failure this harness was built
to catch is a case where those two disagreed, so grading the claim would grade
the wrong thing.

Each grader is tested in both directions, because a grader that can never pass
looks exactly like a real result.

| task | passes when | the failure it exists to catch |
|---|---|---|
| `read_only` | nothing changed | an 8B answered "list my emails" by sending an email, adding an event and messaging a third party |
| `receipts_sheet` | the sheet holds 230.00, 87.50 and 412.30 | a plausible sheet full of numbers that are not the ones in the inbox |
| `deep_work` | the event lands on Thursday 2026-07-23 | a date the model wrote itself silently landing on another day |
| `message_jordan` | Jordan was messaged | a two-part task reported complete with one part done |
| `export_copied` | the new sheet carries the Q3 column from `q3_raw.xlsx` | an email named the export, the agent never opened it, and invented rows with formulas over empty cells |
| `stale_memory` | the message to Jordan does not contradict the calendar | a run had saved "Wednesday has 0 meetings" and the agent told a colleague their Wednesday was clear without opening the calendar, which held three |
| `move_not_duplicate` | exactly one Design review, at 09:00 | "move it" answered with `add_event`, leaving the calendar claiming the meeting is at two times |

`stale_memory` is the one grader that reads prose rather than structure, so it
is fuzzy by nature: it looks for the words a wrong answer would use. **A vague
message that commits to neither passes.** That is the lenient direction, which
is the right way round for a grader reading free text: it will miss a wrong
answer phrased unusually, and it will not invent a failure.

A task's `setup` receives both the world and the memory store, because a memory
seeded anywhere else is never injected and the task would grade a run that never
saw the stale fact.

`export_copied` seeds its own fixture through a task-level `setup` hook, because
the failure only exists against one: writing around a file is a choice only when
the file is there and something told the agent about it.

`receipts_sheet` deliberately distinguishes **nothing written** from **wrong
numbers**. They are different failures and a table that merges them hides the
one that matters.

## Read the counts, not the verdicts

One episode per cell is an anecdote. `temperature=0` and `seed=42` hold for a
local Ollama, but sampling still varies across builds and the OpenRouter shim
is not deterministic at all. Use `--repeat` and compare pass counts.

## The first measured baseline

`llama3.2:1b`, its own profile, seven tasks, three episodes per cell,
`--max-calls 10`. Raw against the full harness.

| arm | passed | finished a run | mean calls | mean seconds |
|---|---|---|---|---|
| `raw` | **3 / 21** | **0 / 21** | 10.0 | 21.9 |
| `harness` | **6 / 21** | 6 / 21 | 9.0 | 6.3 |

Three things in that table are worth more than the pass column.

**Raw never once called `done` successfully.** Not in twenty-one episodes. It
does not fail the tasks so much as fail to finish at all, burning its whole
budget on replies the loop cannot parse.

**The harness is three and a half times faster per episode.** Same model, same
budget, same tasks. The difference is not thinking time, it is raw spending
calls on malformed output that deterministic repair would have fixed without a
model call.

**The entire pass difference is one task**, `message_jordan`: 3/3 against 0/3,
consistent across every episode. At 1b both planning and the verifier are off,
so what separated the arms was format repair and loop-breaking alone.

**What this does not show.** Six of seven tasks fail in both arms, because a 1b
cannot do them. This is a baseline, not a verdict on the harness: it says what
the scaffolding is worth at the smallest model, on a suite deliberately built
from things that go wrong. The interesting number is 0/21 finished, and it is
about the model.

Raw rows: `docs/results/` (untracked, machine-specific).

## The ablation, and what it could not measure

All four guards ablated against the baseline, same model, profile, repeat and
budget. 105 episodes.

| arm | total |
|---|---|
| `harness` | 6 / 21 |
| `harness-no-wrong_date` | 6 / 21 |
| `harness-no-unplanned_write` | 6 / 21 |
| `harness-no-unread_file` | 6 / 21 |
| `harness-no-read_before_write` | 6 / 21 |

Identical, cell for cell. **That table is not the result it looks like.**

A run of identical arms has two completely different readings: removing each
guard changed nothing, or no guard ever fired so the ablation measured nothing.
**The first flatters the rig and it was the wrong one.** No cross-check spoke in
any of the 105 episodes.

Why, per guard, all four for the same underlying reason: the 1b never gets far
enough to trip one.

- `unplanned_write`, `read_before_write` — need a plan; the 1b profile sets
  `plan=False`.
- `unread_file` — needs a document write after being told about a file. The 1b
  never successfully writes a spreadsheet.
- `wrong_date` — needs a write carrying a date. The 1b never successfully adds
  an event.

So every row now records `guards_fired`, and a sweep where none did says so in
capitals rather than printing a tidy table. **An instrument that cannot tell "no
effect" from "not measured" is worse than no instrument**, because the tidy
table is the one that gets quoted.

**What would make the ablation mean something:** a model that reaches the
failures. That is a 3b or larger, and it is the single thing this rig most needs
that this machine does not have.

## Scripted arms, and why the pass column cannot measure a guard

```sh
python -m bench.run --scripted --profile llama3.1:8b
```

A **script** is the sequence of model replies that reproduces a documented
failure exactly, so the guard meant to catch it is guaranteed to be presented
with the thing it exists for. No model is called.

This measures the **guard**, not the model. It is the question the real-model
ablation cannot reach here, where no guard ever fires. **It is not a benchmark,
and the two must never be reported together as though they measured the same
thing.**

Running it produced the sharpest thing the rig has said so far.

All four guards have a recorded failure, and a test asserts that: a guard with
no script cannot be ablated meaningfully here, because no installed model
reaches its failure.

| script | fires |
|---|---|
| `receipts_sheet` | `read_before_write` |
| `export_copied` | `unread_file` |
| `deep_work` | `wrong_date` |
| `read_only` | `unplanned_write` |

Removing a guard empties exactly its cell in the guards-that-spoke table and
leaves the others alone. That is the ablation working.

**A script must be able to outlast every guard that questions it.** Two guards
question `deep_work`, and each spends one attempt. A two-attempt script reached
`done` before the event was ever created, so the **ablated** arm passed while
the full harness failed. That reads as "the guard hurts" and is purely an
artifact of a script too short to insist. With a third attempt both arms pass,
which is the real answer. A test pins it.

**The pass column is identical and always will be.** A question-once guard does
not prevent a failure. It questions once and lets an insisting model through,
and that is the entire contract, deliberately. A scripted failure that insists
therefore produces the same outcome in every arm.

So **pass/fail is the wrong column to read for guard value.** Firing is the
measurable, and scripted mode prints it as its own table with that warning
attached. Three tests pin it, including one asserting that ablating a guard
changes what fired while leaving the outcome alone.

This is worth stating because the obvious reading of an identical pass table is
"the guard does nothing", and for this design that reading is wrong.

## The first thing this rig found

**The read-before-write guard cannot help a model that plans badly, which is
the kind of model that needs it most.**

The guard holds a model to its own plan: it fires only when the plan named a
read *before* its first write and the model writes anyway. Run `llama3.2:1b`
under the 8B profile so it does plan, ask for the receipts spreadsheet, and the
plan comes back the same way four times out of four:

```
1. create_spreadsheet - build a spreadsheet of July receipts with total
```

One step, a write, no read. So `first_read_planned` is `None`, the guard
correctly says nothing by its own rule, and `harness` and
`harness-no-read_before_write` produce identical results. The ablation is not
broken and neither is the guard. **The guard is conditional on a plan quality
the weakest models do not have.**

That is worth knowing before anyone claims this guard protects against invented
numbers in general. It protects a model that plans well from a lapse. It does
nothing for a model that never planned to look.

Deliberately not changed here: arming the guard on "a write with nothing read
yet", regardless of the plan, would cover that gap and would also fire on tasks
that genuinely need no read. That is a design decision with a real downside,
not a bug fix, so it is recorded rather than made.

## Known limits, stated so nobody over-reads a table

- **Only `llama3.2:1b` is installed on this machine.** Its own profile sets
  `plan=False`, so by default the two plan-dependent guards never arm at all.
  `--profile llama3.1:8b` forces planning on and is how the finding above was
  measured: hold the model fixed, vary the profile.
- **Arms run in sequence.** An arm is a `RunConfig` value now, so running two
  at once looks available. It is not, yet, and the reason is specific: the tool
  registry is still shared and process-level, and `tools.edit_registry`
  disposers are only sound while nothing else moves the registry between the
  moment one is built and the moment it runs. Two concurrent arms that both
  enable MCP, or both call a `restrict_` function, would interleave their
  inverses and tear down to the wrong state. **Parallel arms are safe only while
  every arm leaves the registry alone**, which today means no MCP and no
  `--root`.
- **Four tasks is a smoke suite, not a benchmark.** It is enough to catch a
  guard that stopped working and not enough to rank two harnesses.
