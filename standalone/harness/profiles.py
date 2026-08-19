"""Per-model harness profiles — a different harness for each model.

The harness engine in agent.py is one codebase, but its behaviour is governed by
a handful of knobs: whether to plan, how long a plan may be, how many verifier
rounds to spend before accepting done(), whether to suppress repeated calls, how
many think() calls in a row to tolerate, how long a driver reply may run, how
many memories to inject, the context window, and the call budget.

One setting is never right for all five sizes, because the models fail and
succeed differently:

  - A 1B model's mistakes are almost all *mechanical* — broken JSON, wrong
    parameter names — and it falls into repetition loops. It cannot follow a
    plan or judge whether a task is done, so spending calls on planning and
    verification just starves the part of the budget that does real work. Its
    profile pours everything into format repair + loop-breaking, drops planning
    and the verifier, keeps replies short so the JSON survives, and gets a
    bigger budget (each call is cheap and fast).

  - A 3B follows a SHORT plan and survives ONE verify pass; a second verify
    round tends to false-negative and send it back into a loop.

  - An 8B (Llama 3.1) has solid instruction-following and JSON, so the full
    harness — real planning, two verify rounds — pays for itself.

  - Qwen 2.5 14B / 32B are strong at structured output, tool calls and math and
    reason well, so they get richer outputs (longer decks/sheets), longer plans,
    more room to think, and a wider context to read before writing. The 32B is
    also the slowest and the most reliable, so it trades the second verify round
    and a couple of budget slots for fewer, higher-quality steps — when a call
    costs minutes, flailing is the expensive failure, not stopping early.

IMPORTANT: the benchmark does NOT use these. bench/ runs run_harness with the
DEFAULT profile, so the raw-vs-harness comparison stays byte-identical to runs
already on disk. Only the on-device agents (agents/, webui/) select a per-model
profile — the same pattern as EXTRA_RULES / SIM_TODAY in agent.py.
"""
import re
from dataclasses import asdict, dataclass, fields, replace


@dataclass(frozen=True)
class Profile:
    label: str = "default"
    rationale: str = ""

    # planning: ask for a tool-grounded plan up front, cap its length
    plan: bool = True
    plan_max_steps: int = 6

    # verification: how many times a done() may be sent back by the verifier
    verify_rounds: int = 2

    # loop-breaking: suppress an identical call against an unchanged world
    loop_break: bool = True

    # How many times the SAME call (same tool, same arguments) may execute while
    # the world is unchanged. 1 is the original behaviour: one execution, every
    # repeat suppressed. Higher lets a model look at something a second time
    # before it commits — a real pattern (read the email, think, read it again)
    # that a hard one-shot rule blocks. The counter resets whenever the world
    # changes, so this only ever bounds genuinely redundant calls.
    repeat_limit: int = 1

    # The same budget for world-CHANGING tools (send_email, add_event,
    # write_file, ...). Deliberately separate and left at 1: a successful write
    # always bumps the world, so an identical write on top of its own result is
    # a duplicate (two invites, doubled appended text), not a retry. Raise it
    # only if duplicate side effects are acceptable.
    repeat_limit_write: int = 1

    # nudge "take a concrete action" after this many think() calls in a row
    think_streak_cap: int = 2

    # driver reply length cap (tokens) — shorter keeps small-model JSON intact,
    # longer lets strong models write full decks / spreadsheets in one call
    num_predict: int = 700

    # long-term memories auto-injected into the system prompt
    memory_k: int = 3

    # model context window
    num_ctx: int = 8192

    # Ceiling on LLM calls in one run, not a target: an agent that finishes in
    # four calls costs four. A tight number on a small model is a loop-brake; on
    # a model that can actually follow a plan it is just a premature cut-off, so
    # the 8B carries real headroom. webui.runner.call_budget applies it.
    max_calls: int = 14

    def to_dict(self):
        return asdict(self)


# Reproduces the benchmark harness exactly. Unknown models fall back to this.
DEFAULT = Profile()


PROFILES = {
    # --- Llama 3.2 1B -------------------------------------------------------
    "llama3.2:1b": Profile(
        label="format-survival",
        rationale="A 1B's errors are mechanical (broken JSON, wrong keys) and it "
                  "loops hard. Everything goes into format repair + loop-breaking; "
                  "planning and the verifier are dropped — it can't follow a plan or "
                  "judge completion, and both only burn its tiny budget. Replies are "
                  "kept short so the JSON stays intact, with extra calls to compensate.",
        plan=False, plan_max_steps=0, verify_rounds=0, loop_break=True,
        repeat_limit=2, think_streak_cap=1, num_predict=350, memory_k=2,
        num_ctx=8192, max_calls=18),

    # --- Llama 3.2 3B -------------------------------------------------------
    "llama3.2:3b": Profile(
        label="guided-guarded",
        rationale="Small but usable: it follows a SHORT plan and survives one verify "
                  "pass, but a second round tends to false-negative and loop. Keep "
                  "aggressive loop-breaking; moderate output length.",
        plan=True, plan_max_steps=3, verify_rounds=1, loop_break=True,
        repeat_limit=2, think_streak_cap=2, num_predict=500, memory_k=3,
        num_ctx=8192, max_calls=14),

    # --- Llama 3.1 8B -------------------------------------------------------
    "llama3.1:8b": Profile(
        label="balanced",
        rationale="A strong general 8B with good instruction-following and JSON. The "
                  "full harness pays off: real planning, two verify rounds, standard "
                  "budget and output length.",
        plan=True, plan_max_steps=5, verify_rounds=2, loop_break=True,
        repeat_limit=3, think_streak_cap=2, num_predict=700, memory_k=3,
        num_ctx=8192, max_calls=50),

    # --- The Hexagon NPU, served by GenieX -----------------------------------
    # GenieX reports its own model ids (`ai-hub-models/...`), and npu/ollama_shim
    # substitutes that id for the config.json tag on every call, so these keys
    # must match what `geniex serve` lists — not an Ollama tag.
    #
    # NEITHER is re-tuned. AI Hub quantisation is not Q4_0, so before trusting
    # them check parse_failures and invalid_calls in the run log — the signal
    # notes/NPU Serving.md calls out for exactly this step.
    #
    # Llama 3.1 8B is the same weights the balanced profile was tuned against on
    # Ollama, so the NPU run stays a backend comparison rather than a model
    # change, and Phase 2's measurement means something.
    "ai-hub-models/Llama-v3.1-8B-Instruct": Profile(
        label="balanced (NPU)",
        rationale="Llama 3.1 8B on the Hexagon NPU via GenieX — the same model the "
                  "Ollama profile was tuned for, so the full harness applies "
                  "unchanged: real planning, two verify rounds, standard budget. "
                  "Only the backend differs, which is the point of the comparison.",
        plan=True, plan_max_steps=5, verify_rounds=2, loop_break=True,
        repeat_limit=3, think_streak_cap=2, num_predict=700, memory_k=3,
        num_ctx=8192, max_calls=50),

    # Fallback if the Llama bundle is licence-gated on this machine: Qwen 2.5 7B
    # is pullable without a grant. Same class of model, so it inherits the same
    # profile — but it is a different model, so a run measured on it is NOT a
    # like-for-like comparison against the Ollama baseline.
    "ai-hub-models/Qwen2.5-7B-Instruct": Profile(
        label="balanced (NPU)",
        rationale="Qwen 2.5 7B Instruct on the Hexagon NPU via GenieX. Good "
                  "instruction-following, JSON and tool calls, so the full harness "
                  "pays off as it does for the 8B: real planning, two verify "
                  "rounds, standard budget.",
        plan=True, plan_max_steps=5, verify_rounds=2, loop_break=True,
        repeat_limit=3, think_streak_cap=2, num_predict=700, memory_k=3,
        num_ctx=8192, max_calls=50),

    # --- Qwen 2.5 14B -------------------------------------------------------
    "qwen2.5:14b": Profile(
        label="structured-reasoner",
        rationale="Qwen 2.5 14B is excellent at structured output, tool calls and "
                  "math. Let it write richer arguments (longer decks/sheets), follow "
                  "longer plans, reason a little more before acting, and use a wider "
                  "context to read before it writes.",
        plan=True, plan_max_steps=6, verify_rounds=2, loop_break=True,
        repeat_limit=3, think_streak_cap=3, num_predict=900, memory_k=4,
        num_ctx=12288, max_calls=14),

    # --- Qwen 2.5 32B -------------------------------------------------------
    "qwen2.5:32b": Profile(
        label="few-precise-steps",
        rationale="Qwen 2.5 32B is the most reliable and the slowest. It rarely "
                  "flails, so trust it: one verify pass instead of two, a tight budget "
                  "of high-quality steps, the longest structured outputs and the "
                  "widest context. When each call costs minutes, fewer better calls "
                  "beat more calls.",
        plan=True, plan_max_steps=6, verify_rounds=1, loop_break=True,
        repeat_limit=3, think_streak_cap=3, num_predict=1000, memory_k=4,
        num_ctx=16384, max_calls=12),
}


# Parameter count out of a tag: "llama3.2:1b-instruct-q4_K_M" -> 1.0,
# "phi4-mini:3.8b" -> 3.8. Anchored after ':' or '-' so a family version number
# ("llama3.2") is never read as a size.
_SIZE_RE = re.compile(r"[:\-](\d+(?:\.\d+)?)b\b", re.I)


def size_of(tag):
    """Billions of parameters named by a model tag, or None if it doesn't say."""
    m = _SIZE_RE.search(str(tag or ""))
    return float(m.group(1)) if m else None


# Upper bound (exclusive) -> whose tuning a model of that size inherits. Size,
# not family, is what predicts the failure mode these knobs answer to: a 1B
# breaks JSON and loops whoever made it, and a 14B follows a plan whoever made
# it. The tuning is borrowed; the label says so, so a banner never claims a
# gemma is a tuned Llama.
_SIZE_BANDS = [(2, "llama3.2:1b"), (5, "llama3.2:3b"), (11, "llama3.1:8b"),
               (20, "qwen2.5:14b"), (float("inf"), "qwen2.5:32b")]


def _by_size(tag):
    """The profile for a tag with no entry of its own, chosen by parameter count.

    Family alone used to decide this, taking the FIRST listed profile of a
    matching family: llama3.2 lists 1b first, so a llama3.2:11b was handed the
    1B's format-survival tuning - planning off, verifier off, replies capped at
    350 tokens - which is exactly wrong for a model that size. Same-family
    entries still win, but only when the size matches too.
    """
    size = size_of(tag)
    if size is None:
        return None
    base = str(tag).split(":")[0]
    same = next((p for k, p in PROFILES.items()
                 if k.split(":")[0] == base and size_of(k) == size), None)
    if same:
        return same
    for ceiling, key in _SIZE_BANDS:
        if size < ceiling:
            src = PROFILES[key]
            return replace(src, label=f"{src.label} (by size)",
                           rationale=f"No profile for this model. Tuned like {key}, "
                                     f"the closest size the harness has measured. "
                                     + src.rationale)
    return None


def for_model(tag, override=None):
    """Resolve the harness profile for a model tag.

    Exact tag first, then by parameter count (see _by_size), else DEFAULT so any
    new model still runs. `override` is an optional dict (e.g. a config.json
    "harness" block) that patches individual fields on top of the chosen profile.
    """
    prof = PROFILES.get(tag) or _by_size(tag) or DEFAULT
    if isinstance(override, dict) and override:
        known = {f.name for f in fields(Profile)}
        prof = replace(prof, **{k: v for k, v in override.items() if k in known})
    return prof
