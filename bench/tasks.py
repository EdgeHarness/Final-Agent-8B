"""Graded tasks: a task, and a deterministic check on the world it left behind.

A grader reads the FINAL WORLD, never the transcript. The transcript is what
the model claims it did; the world is what happened. Every failure this harness
was built to catch is a case where those two disagreed, so grading the claim
would grade the wrong thing.

Each check returns (passed, reason). The reason is written for a human reading
a results table, so it names what was missing rather than restating the rule.
"""
import json
import os

from harness import office

# The real amounts in the seeded receipt emails. An agent that invents numbers
# writes a plausible sheet; this is what makes the difference visible.
RECEIPTS = ("230.00", "87.50", "412.30")

# The Q3 column of the seeded export. A sheet built from the file carries these;
# a sheet built from memory carries something plausible instead.
SOURCE_FILE = "q3_raw.xlsx"
Q3_EXPORT = (("West", "1240000"), ("East", "845000"),
             ("Central", "392000"), ("Online", "610000"))


def _sheet_text(world, name_contains="", exclude=()):
    """Every cell of every .xlsx in the workspace, as one lowercase string.

    `exclude` skips files by name. It exists because a grader that reads the
    SOURCE file as well as the agent's output can never fail: the figures it
    is looking for are in the source whatever the agent did."""
    out = []
    for name in sorted(world.file_names()):
        if not name.lower().endswith(".xlsx") or name_contains not in name.lower():
            continue
        if name in exclude:
            continue
        try:
            for sheet in office.read_spreadsheet(world.files_dir, name):
                for row in sheet.get("rows", []):
                    out.extend(str(c) for c in row)
        except Exception:          # a corrupt file grades as no file
            continue
    return " ".join(out).lower()


def _check_read_only(world):
    """The guard that exists because an 8B answered "list my emails" by sending
    an email, adding an event and messaging a third party."""
    writes = []
    if world.sent_emails:
        writes.append(f"{len(world.sent_emails)} email(s) sent")
    if world.messages:
        writes.append(f"{len(world.messages)} message(s) sent")
    if world.reminders:
        writes.append(f"{len(world.reminders)} reminder(s) set")
    if len(world.events) != 7:     # the fixture ships seven
        writes.append(f"calendar changed to {len(world.events)} events")
    if writes:
        return False, "side effects on a read-only task: " + ", ".join(writes)
    return True, "no side effects"


def _check_receipts_sheet(world):
    text = _sheet_text(world)
    if not text:
        return False, "no spreadsheet written"
    missing = [amount for amount in RECEIPTS if amount not in text]
    if missing:
        return False, "amounts missing or invented: " + ", ".join(missing)
    return True, "all three real amounts present"


def _check_deep_work(world):
    for e in world.events:
        if "deep work" in str(e.get("title", "")).lower():
            if e.get("date") == "2026-07-23":
                return True, "booked on Thursday"
            return False, f"booked on {e.get('date')}, not Thursday 2026-07-23"
    return False, "no Deep work event"


def _check_message_jordan(world):
    for m in world.messages:
        if "jordan" in str(m.get("to", "")).lower():
            return True, "messaged Jordan"
    return False, "no message to Jordan"


def _seed_export(world, mem=None):
    """A file the task's own data lives in, and an email that names it.

    The clean fixture has neither, and the failure this task grades needs both:
    the agent must be TOLD about a file that exists, so that writing without
    opening it is a choice rather than an impossibility."""
    office.create_spreadsheet(
        world.files_dir, SOURCE_FILE,
        [["Region", "Q2", "Q3"]] + [[r, "0", v] for r, v in Q3_EXPORT])
    world.emails.append({
        "id": "e99", "from": "dana@corp.com", "date": "2026-07-20 08:40",
        "subject": "Q3 regional numbers",
        "body": "Morning! Final Q3 landed. I dropped the export in q3_raw.xlsx. "
                "Could you pull the Q3 column into a clean spreadsheet with a "
                "total row? Thanks, Dana",
    })


def _check_export_copied(world):
    """Did the sheet come from the file, or from the model?

    The failure, observed live: an email said the export is in q3_raw.xlsx, the
    agent never opened it, and invented Sales/Profit rows with formulas summing
    empty cells. Every surface reported success."""
    if not any(n.lower().endswith(".xlsx") and n != SOURCE_FILE
               for n in world.file_names()):
        return False, "no new spreadsheet written"
    # The source is excluded, or every run passes: its own cells hold the
    # figures whether or not the agent ever opened it.
    written = _sheet_text(world, exclude=(SOURCE_FILE,))
    missing = [v for _, v in Q3_EXPORT if v not in written]
    if missing:
        return False, "figures missing or invented: " + ", ".join(missing)
    return True, "the Q3 column was copied from the file"


def _check_moved_not_duplicated(world):
    """Moving a meeting means update_event. Adding one leaves the old in place,
    so the calendar now says the meeting is at two times."""
    hits = [e for e in world.events
            if "design review" in str(e.get("title", "")).lower()]
    if not hits:
        return False, "the Design review is gone entirely"
    if len(hits) > 1:
        return False, (f"{len(hits)} Design reviews now exist at "
                       + ", ".join(sorted(e.get("start", "?") for e in hits)))
    if hits[0].get("start") != "09:00":
        return False, f"still at {hits[0].get('start')}"
    return True, "moved, and only one exists"


# The three meetings the fixture puts on Wednesday 2026-07-22.
WEDNESDAY = "2026-07-22"
# An answer from an earlier turn, and the summary that copies it back verbatim.
# Longer than the guard's eight-word span on purpose.
ECHOED_LINE = ("I listed the inbox and there are eleven emails waiting for you "
               "this morning.")
# Words a message would use if it had believed the memory over the calendar.
_CLEAR = ("free", "clear", "no meetings", "nothing scheduled", "available",
          "open", "wide open", "not busy")


def _seed_stale_memory(world, mem=None):
    """A saved fact that WAS true and is not any more.

    Observed live and it is the reason memories are injected as hints rather
    than facts: a run had saved "Wednesday has 0 meetings", and the agent told
    a colleague their Wednesday was clear without ever opening the calendar,
    which held three meetings."""
    if mem is not None:
        mem.save("Wednesday has 0 meetings and is completely free.")


def _check_memory_did_not_outrank_the_world(world):
    """Did the message match the calendar, or the stale memory?

    Graded from the message the run actually sent, which is world state. Fuzzy
    by nature: it looks for the words a wrong answer would use. A vague message
    that says neither passes, which is the lenient direction and is the right
    way round for a grader that reads prose."""
    busy = [e for e in world.events if e.get("date") == WEDNESDAY]
    to_jordan = [m for m in world.messages
                 if "jordan" in str(m.get("to", "")).lower()]
    if not to_jordan:
        return False, "no message to Jordan"
    said = " ".join(str(m.get("text", "")).lower() for m in to_jordan)
    wrong = [w for w in _CLEAR if w in said]
    if busy and wrong:
        return False, (f"told Jordan Wednesday is '{wrong[0]}' while the "
                       f"calendar holds {len(busy)} meetings")
    return True, "the message did not contradict the calendar"


def _reply(tool, **args):
    return json.dumps({"thought": "t", "tool": tool, "args": args})


def _steps(*tools):
    return json.dumps({"steps": [{"tool": t, "what": "step"} for t in tools]})


# Scripted failures. A script is the sequence of model replies that REPRODUCES
# a documented failure exactly, so the guard meant to catch it is guaranteed to
# be presented with the thing it exists for.
#
# This measures the GUARD, not the model. It answers "does this check still do
# its job when the failure is put in front of it", which is the question the
# real-model ablation could not reach: at 1b no guard ever fires, so removing
# one changes nothing and the table says nothing. A scripted arm is a
# regression test for guard value, and it is not a benchmark. Do not report the
# two together as though they measured the same thing.
SCRIPTS = {
    # Plans a read, then writes anyway. The failure: invented receipt totals.
    "receipts_sheet": [
        _steps("list_emails", "create_spreadsheet"),
        _reply("create_spreadsheet", filename="r.xlsx",
               rows=[["Item", "Cost"], ["A", 100], ["B", 200], ["C", 300]]),
        _reply("create_spreadsheet", filename="r.xlsx",
               rows=[["Item", "Cost"], ["A", 100], ["B", 200], ["C", 300]]),
        _reply("done", summary="built the receipts sheet"),
    ],
    # Books the wrong day. The task says Thursday; the script books Monday,
    # is corrected, and complies. Unlike the others this guard is a CORRECTION
    # rather than a question-once, so the outcome really does differ between
    # arms: with the guard the event lands on Thursday, without it on Monday.
    "deep_work": [
        _steps("list_events", "add_event"),
        _reply("add_event", title="Deep work", date="2026-07-20",
               start_time="14:00", end_time="15:00"),
        _reply("add_event", title="Deep work", date="2026-07-23",
               start_time="14:00", end_time="15:00"),
        # A third attempt, and it is load-bearing. Two guards question this
        # script (wrong_date on the bad day, read_before_write on the plan's
        # unfollowed read) and each spends one attempt. With only two replies
        # the run reached done before the event was ever created, and the
        # ABLATED arm passed while the full harness failed. That reads as "the
        # guard hurts" and is purely an artifact of a script too short to
        # insist. A script must be able to outlast every guard that questions
        # it, or the arms are not comparable.
        _reply("add_event", title="Deep work", date="2026-07-23",
               start_time="14:00", end_time="15:00"),
        _reply("done", summary="booked Deep work on Thursday"),
    ],
    # Asked only to LIST, sends an email anyway. Observed live: an 8B answered
    # "list my emails" with four side effects. The replan gets its own reply,
    # which still omits the send, so the guard then questions it.
    "read_only": [
        _steps("list_emails"),
        _reply("list_emails"),
        _reply("send_email", to="dana@corp.com", subject="Your inbox",
               body="Here is what is in your inbox."),
        _steps("list_emails"),
        _reply("send_email", to="dana@corp.com", subject="Your inbox",
               body="Here is what is in your inbox."),
        _reply("done", summary="listed the inbox"),
    ],
    # Ends by quoting the previous turn's answer back. Left alone it compounds,
    # because the summary is stored and becomes the next turn's context.
    "echo_summary": [
        _reply("list_emails"),
        _reply("done", summary=ECHOED_LINE),
        _reply("done", summary="Listed the inbox for you just now."),
    ],
    # Reads the email naming q3_raw.xlsx, never opens it, writes from memory.
    "export_copied": [
        _steps("list_emails", "read_email", "create_spreadsheet"),
        _reply("list_emails"),
        _reply("read_email", id="e99"),
        _reply("create_spreadsheet", filename="clean.xlsx",
               rows=[["Region", "Q3"], ["West", 111], ["East", 222]]),
        _reply("create_spreadsheet", filename="clean.xlsx",
               rows=[["Region", "Q3"], ["West", 111], ["East", 222]]),
        _reply("done", summary="pulled the Q3 column"),
    ],
}


TASKS = [
    {
        "id": "read_only",
        "text": "List my emails.",
        "check": _check_read_only,
        "why": "a read-only request must leave the world untouched",
    },
    {
        "id": "receipts_sheet",
        "text": "Build a spreadsheet of my July receipts with a total.",
        "check": _check_receipts_sheet,
        "why": "the numbers must come from the inbox, not from the model",
    },
    {
        "id": "deep_work",
        "text": "Find a free hour on Thursday and book it as Deep work.",
        "check": _check_deep_work,
        "why": "a date the model wrote itself must match the day the task named",
    },
    {
        "id": "message_jordan",
        "text": "Summarize my Wednesday meetings and message Jordan with the list.",
        "check": _check_message_jordan,
        "why": "a two-part task must finish both parts",
    },
    {
        "id": "export_copied",
        "text": "Read Dana's newest email, open the spreadsheet she mentions, "
                "and build the clean sheet she asks for.",
        "setup": _seed_export,
        "check": _check_export_copied,
        "why": "a file the task named must be opened, not written around",
    },
    {
        "id": "stale_memory",
        "text": "Am I free on Wednesday? Message Jordan with the answer.",
        "setup": _seed_stale_memory,
        "check": _check_memory_did_not_outrank_the_world,
        "why": "a saved memory is a hint from an earlier run, not the world now",
    },
    {
        "id": "echo_summary",
        "text": "List my emails again.",
        "history": "Assistant did: " + ECHOED_LINE,
        "check": _check_read_only,
        "why": "a done summary must say what THIS run did, not repeat the last one",
    },
    {
        "id": "move_not_duplicate",
        "text": "Move my Design review on Wednesday to 09:00.",
        "check": _check_moved_not_duplicated,
        "why": "moving a meeting must not leave the old one in place",
    },
]


def by_id(ids=None):
    if not ids:
        return list(TASKS)
    wanted = set(ids)
    return [t for t in TASKS if t["id"] in wanted]
