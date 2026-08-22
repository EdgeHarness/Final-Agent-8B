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

`receipts_sheet` deliberately distinguishes **nothing written** from **wrong
numbers**. They are different failures and a table that merges them hides the
one that matters.

## Read the counts, not the verdicts

One episode per cell is an anecdote. `temperature=0` and `seed=42` hold for a
local Ollama, but sampling still varies across builds and the OpenRouter shim
is not deterministic at all. Use `--repeat` and compare pass counts.

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
- **Arms run in sequence, never in parallel**, because the loop still keeps one
  configuration in module globals. The ablation switch saves and restores that
  global. This rig is the concrete reason to thread a config object instead.
- **Four tasks is a smoke suite, not a benchmark.** It is enough to catch a
  guard that stopped working and not enough to rank two harnesses.
