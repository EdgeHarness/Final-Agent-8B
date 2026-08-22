---
tags: [architecture, explainer]
cssclasses: [topic-core]
---

# Defensive Patterns

Bug classes that actually shipped here, each stated as the rule that prevents
the next one. Read this before changing the tool registry, the guards, or the
web UI's view of either.

The provenance comments scattered through [[Agent Loop]] and `harness/agent.py`
record individual failures. This note records the **shapes** those failures
share, because the same shape has now produced four separate defects and would
have produced more.

## A property of a tool belongs on the tool

**The rule.** When a mechanism needs to know something about a tool, the tool
declares it. A list of tool names maintained beside the mechanism is a copy,
and copies drift silently.

Four instances, all found by adding something and watching what failed to
notice it:

| the copy | what it broke |
|---|---|
| `BASE_WRITE_TOOLS` in `agent.py` | a new domain's writes were invisible to four guards |
| the unread-file guard's trigger set | the guard was blind to any document type but two |
| `_KEEP_ALWAYS` in `mcp_bridge.py` | every base-layer tool added later vanished under MCP |
| `MUTATORS` in `app.js` | calendar edits, and every real-account write, drawn as reads |

The last is the clearest case for the rule. It was a client-side literal, so it
could not name MCP tools at all, because those do not exist until a run
registers them. With real accounts on, creating a draft in a live mailbox
rendered exactly like listing mail. Nobody had to make a mistake for that to be
wrong; it was wrong the moment the tool set stopped being fixed.

The declarations that replaced them are `effect`, `opens`, `writes_file`,
`lists_files` and `simulated_connector`, and the mechanisms derive from those.
The banner ships the effect map to the browser so the UI reads the same answer
the loop does.

**Corollary: an undeclared tool is world-changing, not a read.** Absence of a
declaration is not permission. A tool that arrives without saying what it does
is treated as the most dangerous thing it could be.

## Repair before you reject, at every layer

**The rule.** A near miss the harness can fix is not an error worth a model
call. Rejecting one spends a turn teaching the model something the harness
already knew.

This is applied at JSON, parameters, values, documents and verifier output. The
plan step was the one layer that did not, and the cost was invisible: a model
writing `create_sheet` lost that step entirely, and **losing a plan step
silently changes which guards arm.** A write the plan no longer names arms the
unplanned-write guard; a read it no longer names disarms the read-before-write
guard. A spelling mistake moved the safety checks.

**The boundary: repair, never invent.** A name that is not a near miss for any
real tool is still dropped. Free prose must never enter the context as a plan
step.

## Derive rather than mutate, and the inverse is free

**The rule.** If a change can be made by producing a new value instead of
altering a shared one, produce the new value. A derived change needs no undo,
because recovery is discarding it.

Reach for a tracked inverse only when the thing being changed is genuinely
shared. The tool registry is: one dict, many readers, so
`tools.edit_registry` returns a real disposer and they run LIFO. A run's
configuration is not: `RunConfig.without_guard` returns a fresh value and
nothing has to be restored.

The evaluation rig got this wrong first. Ablating a guard meant patching
`agent.GUARDS` and putting it back, which is an in-place change to something
that wanted to be a derived one. It cost a save-and-restore helper and a test
asserting the helper worked, both deleted once the config became a value.

**The precondition on the other half.** A tracked inverse is only sound while
nothing else moves the shared thing between the moment the inverse is built and
the moment it runs. Single-threaded LIFO satisfies that. Concurrency does not,
automatically, and the failure is silent: teardown restores a state that was
never current.

## Question once, never forbid, and the wording is load-bearing

**The rule.** Every guard fires one corrective message and lets the model
through if it insists. A guard that leaves the model no way forward is a block
wearing a question's clothes.

The wording is part of the mechanism, not decoration. The unplanned-write nudge
once ended *"Only do what the task requires - nothing extra"*, and an 8B obeyed
that instead of insisting: it abandoned the actual job and sent a message
claiming it had built a spreadsheet that did not exist. Every downstream check
passed. **The question had become a block in practice while the code still read
like a question.**

Two tests exist only to hold this: one asserts that clause cannot return, one
asserts every guard message contains a way through.

## Denial is monotonic

**The rule.** Once a guard has questioned a call, no later guard is consulted,
so nothing downstream can turn a question back into permission.

This used to hold by accident, because of where the `continue` statements sat.
It holds by construction now, and there is a test for it. Accidental
correctness is not correctness; it is a property nobody knows they can break.

## An unhandled kind falls through silently

**The rule.** A renderer or dispatcher that ignores what it does not recognise
will ignore your new thing too, and it will look like nothing happened rather
than like an error.

`onNote` in `app.js` returns without drawing for any note kind it lacks a branch
for. When the loop started emitting the name of the guard that fired, the UI
dropped it and there was no symptom to notice. The name reached the run log, so
the only clue was its absence from a screen nobody was comparing against a
transcript.

## A working tree is not the artifact

**The rule.** Verify against a clean clone, not against the directory you have
been editing in. Yours holds untracked files, a virtualenv, generated state and
local config that nobody who clones this repository receives.

The link checker written to protect the repository **passed here and failed on a
clean clone**, because its oracle was `os.path.exists` and the file it was
looking for is git-excluded. The fix is to ask `git ls-files` what a cloner
actually gets, and to check against that.

Cloning again immediately found a second fault: the test guarding itself with an
assertion that a local-only directory exists **failed** in the clone, where the
right verdict was skip. A precondition that cannot hold is a reason not to run,
not a reason to report failure.

Both were invisible from a working tree, and neither would ever have surfaced
without cloning and running.

## A rename breaks every reference and nothing tells you

**The rule.** If a document can point at a file, something automated has to
check that the file is there. Otherwise the only check is a person remembering,
and people remember for about a week.

Flattening `standalone/` into the root broke roughly **ninety links across
eighteen notes** in a single commit. The vault stayed un-navigable for
twenty-seven iterations. Nobody was careless: the change was correct, the tests
were green, and the suite had no opinion about documents at all.

`TestDocumentLinks` now walks every tracked `.md`, resolves each relative link
against its own directory, and reports all the broken ones rather than the
first. It reads tracked files only, because a stale link in untracked working
material is nobody's problem and a stale link in something that ships is.

Anchors are deliberately unchecked. Heading anchors are far more fragile than
paths, and a test nobody can keep green gets deleted, which costs more than the
anchors were worth.

## A token you invented resolves to nothing

**The rule.** Before using a CSS variable, grep that it is defined. An undefined
`var(--x)` does not fail; it inherits, and it usually looks almost right.

The guard tag was first written against `var(--ink-soft)`, which does not exist
anywhere in the stylesheet. The real tokens are `--ink`, `--ink-dim` and
`--ink-faint`. Caught by grep, not by looking, because looking is exactly what
this defect defeats. Verify the computed colour in **both** themes: the token
must be defined in the dark block, the light block, and the media query.

## A test that greps source is a proxy

**The rule.** Assert the behaviour, not the text that currently implements it.

`test_both_editors_count_as_writes_for_the_loop` asserted that `agent.py`
contained the string `"update_event"`. It passed for as long as the write set
was a literal in that file and failed the moment the set was derived from
declarations, which is the change that made the behaviour *more* correct. A
test that breaks when the implementation improves is testing the wrong thing.

## Run it and look

Every defect above was found by running the app and watching the screen, or by
grepping for a name. **None of them were found by reading the code that
contained them.** The suite is fast on purpose so this stays cheap; it is not a
substitute for the two minutes it takes to open the UI and press Run.
