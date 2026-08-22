"""Run the graded tasks across arms and print what each arm was worth.

    python -m bench.run --model llama3.2:1b
    python -m bench.run --model llama3.2:1b --repeat 3 --arms raw harness
    python -m bench.run --list

An ARM is one configuration of the loop. "raw" is a model wired to tools with
no scaffolding; "harness" is the full loop; "harness-no-<guard>" is the full
loop with exactly one cross-check removed. That last shape is the point: it is
the only way to answer "did that guard help?" with a number instead of an
anecdote, and it only became possible when the guards stopped being inline
statements and became a list.

WHAT THIS DOES NOT DO. It does not make one run deterministic. temperature=0
and seed=42 hold for a local Ollama, but sampling still varies across builds
and the OpenRouter shim is not deterministic at all, so a single run of a
single arm proves nothing. Use --repeat and read the pass counts, not the
verdicts. An arm that wins 3 of 3 is worth something; an arm that wins 1 of 1
is worth nothing.
"""
import argparse
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench import tasks as task_mod                       # noqa: E402
from harness import agent, profiles                       # noqa: E402
from harness.llm import LLM                               # noqa: E402
from harness.memory import MemoryStore                    # noqa: E402
from harness.world import World                           # noqa: E402


def config_for(arm, max_calls, profile):
    """The RunConfig one arm runs under.

    This used to patch agent.GUARDS and put it back, because the loop kept its
    configuration in module globals. An arm is a value now, so two arms can
    exist at once and nothing has to be restored.
    """
    cfg = agent.RunConfig(max_calls=max_calls, profile=profile)
    if arm.startswith("harness-no-"):
        cfg = cfg.without_guard(arm[len("harness-no-"):])
    return cfg


def arms_for(names=None):
    """raw, harness, and one ablation per registered guard."""
    all_arms = ["raw", "harness"] + [f"harness-no-{n}" for n, _ in agent.GUARDS]
    if not names:
        return all_arms
    unknown = [n for n in names if n not in all_arms]
    if unknown:
        raise SystemExit(f"unknown arm(s): {', '.join(unknown)}\n"
                         f"available: {', '.join(all_arms)}")
    return list(names)


def run_one(arm, task, model, max_calls, profile):
    """One episode. Returns a dict; never raises, because an arm that crashes
    is a result and losing the whole sweep to it is not."""
    tmp = tempfile.mkdtemp(prefix="bench-")
    world = World(tmp)                       # fresh fixtures, not persistent
    mem = MemoryStore(os.path.join(tmp, "memory.jsonl"))
    cfg = config_for(arm, max_calls, profile)
    llm = LLM(model, num_ctx=cfg.profile.num_ctx)
    started = time.time()
    error = ""
    try:
        if arm == "raw":
            ep = agent.run_raw(llm, world, mem, task["text"], cfg=cfg)
        else:
            ep = agent.run_harness(llm, world, mem, task["text"], cfg=cfg)
    except Exception as exc:                 # noqa: BLE001 - a crash is a datum
        ep, error = None, f"{type(exc).__name__}: {exc}"
    passed, reason = task["check"](world)
    return {
        "arm": arm, "task": task["id"], "passed": passed, "reason": reason,
        "calls": llm.calls, "seconds": round(time.time() - started, 1),
        "finished": bool(ep and ep.finished), "error": error,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model", default="llama3.2:1b")
    p.add_argument("--profile", default=None, metavar="TAG",
                   help="run under another model's harness profile, e.g. "
                        "--model llama3.2:1b --profile llama3.1:8b. Holding the "
                        "model fixed and varying the profile is how the "
                        "plan-dependent guards get measured at all on a machine "
                        "where only a small model is installed: their profile "
                        "switches planning off, so their ablation arms are "
                        "identical to the full harness and measure nothing.")
    p.add_argument("--arms", nargs="*", default=None)
    p.add_argument("--tasks", nargs="*", default=None)
    p.add_argument("--repeat", type=int, default=1,
                   help="episodes per (arm, task). One proves nothing.")
    p.add_argument("--max-calls", type=int, default=20)
    p.add_argument("--out", default=None, help="write the raw rows as JSON")
    p.add_argument("--list", action="store_true", help="show arms and tasks, run nothing")
    args = p.parse_args()

    profile = profiles.for_model(args.profile or args.model)
    arms, chosen = arms_for(args.arms), task_mod.by_id(args.tasks)
    if args.list:
        print("arms :", ", ".join(arms_for(None)))
        print(f"profile: {args.profile or args.model} "
              f"(plan={profile.plan}, verify={profile.verify_rounds}, "
              f"calls={profile.max_calls})")
        print("tasks:")
        for t in task_mod.TASKS:
            print(f"  {t['id']:16} {t['why']}")
        return 0

    rows = []
    for arm in arms:
        for task in chosen:
            for _ in range(args.repeat):
                row = run_one(arm, task, args.model, args.max_calls, profile)
                rows.append(row)
                mark = "pass" if row["passed"] else "FAIL"
                note = row["error"] or row["reason"]
                print(f"  {mark}  {arm:28} {task['id']:16} "
                      f"{row['calls']:3} calls  {row['seconds']:6.1f}s  {note}")

    print("\n" + "=" * 78)
    print(f"model {args.model}   profile {args.profile or args.model}   "
          f"plan={profile.plan}   repeat={args.repeat}")
    print(f"{'arm':28} " + "  ".join(f"{t['id'][:14]:>14}" for t in chosen) + "   total")
    for arm in arms:
        cells, won, ran = [], 0, 0
        for t in chosen:
            hits = [r for r in rows if r["arm"] == arm and r["task"] == t["id"]]
            ok = sum(1 for r in hits if r["passed"])
            won += ok
            ran += len(hits)
            cells.append(f"{ok}/{len(hits)}".rjust(14))
        print(f"{arm:28} " + "  ".join(cells) + f"   {won}/{ran}")
    print("=" * 78)
    print("Read the counts, not the verdicts. Sampling varies run to run, so a\n"
          "single episode per cell is an anecdote. Use --repeat.")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"model": args.model,
                       "profile": args.profile or args.model,
                       "plan": profile.plan, "repeat": args.repeat,
                       "rows": rows}, fh, indent=2)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
