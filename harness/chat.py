"""Conversation threads — what turns a one-shot agent into something you talk to.

The harness runs one task and stops. Nothing carries from one run to the next
except the world and long-term memory, so asking "and what about Thursday?"
after a run lands on an agent with no idea what Thursday refers to.

This stores the turns. A thread is a list of {role, text} plus the run id that
produced each assistant turn, so the transcript of *how* an answer was reached
stays available without living in the conversation itself.

    threads(folder)              -> [{id, title, updated, n}]  newest first
    create(folder, first_task)   -> id
    messages(folder, tid)        -> [{role, text, ts, run}]
    append(folder, tid, role, text, run=None)
    delete(folder, tid)
    prompt_block(msgs, k)        -> text injected into the system prompt

Stored as one JSON file per agent at <folder>/chat/threads.json. One file
because this is a single-user local app: the whole history of a laptop's worth
of conversations is smaller than one of the .pptx files in workspace/, and one
file means no half-written thread if the process dies mid-append.

NOT in workspace/ on purpose — a factory reset clears the simulated inbox and
the files, and losing the conversation with them would be surprising.
"""
import json
import os
import time
import uuid

# Enough turns for a follow-up to make sense, few enough that the block cannot
# crowd out the tool docs in an 8k context. Older turns fall off the top.
DEFAULT_TURNS = 6
TITLE_CHARS = 60


def _path(folder):
    return os.path.join(folder, "chat", "threads.json")


def _load(folder):
    try:
        with open(_path(folder), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"threads": []}
    return data if isinstance(data, dict) and "threads" in data else {"threads": []}


def _save(folder, data):
    p = _path(folder)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, p)          # atomic: a crash leaves the old file, not half of one


def _find(data, tid):
    for t in data["threads"]:
        if t["id"] == tid:
            return t
    return None


def threads(folder):
    """Sidebar rows, newest first. Deliberately without message bodies — the
    list is rendered on every poll and the bodies can be large."""
    out = []
    for t in _load(folder)["threads"]:
        out.append({"id": t["id"], "title": t.get("title") or "New chat",
                    "updated": t.get("updated", 0), "n": len(t.get("messages", []))})
    return sorted(out, key=lambda t: t["updated"], reverse=True)


def create(folder, first_task=""):
    data = _load(folder)
    tid = uuid.uuid4().hex[:12]
    title = (first_task or "").strip().replace("\n", " ")
    if len(title) > TITLE_CHARS:
        title = title[:TITLE_CHARS - 1] + "…"
    data["threads"].append({"id": tid, "title": title or "New chat",
                            "created": time.time(), "updated": time.time(),
                            "messages": []})
    _save(folder, data)
    return tid


def messages(folder, tid):
    t = _find(_load(folder), tid)
    return list(t.get("messages", [])) if t else []


def append(folder, tid, role, text, run=None):
    data = _load(folder)
    t = _find(data, tid)
    if not t:
        return False
    t["messages"].append({"role": role, "text": text, "ts": time.time(), "run": run})
    t["updated"] = time.time()
    # A thread created before its first task was known gets its name from it.
    if role == "user" and t.get("title") in (None, "", "New chat"):
        title = text.strip().replace("\n", " ")
        t["title"] = title[:TITLE_CHARS - 1] + "…" if len(title) > TITLE_CHARS else title
    _save(folder, data)
    return True


def delete(folder, tid):
    data = _load(folder)
    before = len(data["threads"])
    data["threads"] = [t for t in data["threads"] if t["id"] != tid]
    _save(folder, data)
    return len(data["threads"]) != before


def prompt_block(msgs, k=DEFAULT_TURNS):
    """The earlier turns, as text for the system prompt.

    Deliberately NOT replayed as real chat messages. The harness contract is
    "reply with exactly one JSON object", and a run of prior assistant prose in
    the message list is the strongest possible cue for a small model to reply
    with prose too. As a block it reads as context; as messages it reads as a
    pattern to continue.

    Prior answers are labelled as a record ("Assistant did:"), never as "You:".
    First person is itself a pattern to continue: observed live on a 1B, each
    new done summary opened with the previous turn's summary and appended to it,
    so by the third turn the answer described the second turn's work plus spam
    text from an unrelated email. agent.echoes_history catches what survives
    this, but removing the cue is cheaper than catching every copy downstream.
    """
    msgs = [m for m in msgs if m.get("text")][-k:]
    if not msgs:
        return ""
    lines = []
    for m in msgs:
        who = "User" if m["role"] == "user" else "Assistant did"
        text = " ".join(str(m["text"]).split())
        if len(text) > 300:
            text = text[:299] + "…"
        lines.append(f"{who}: {text}")
    return ("\n\nEARLIER IN THIS CONVERSATION (for context; the task below is what "
            "you must do now):\n" + "\n".join(lines))
