"""Tool registry shared by BOTH conditions (raw and harness).

Each tool: name, effect class, signature params {name: (type_desc, required)},
description, an example call (shown only in the harness prompt), and an executor.
Tool behavior and error messages are identical across conditions - the
experiment varies only the scaffolding around the model.
"""
import json

from . import office
from .world import ToolError


def _fmt(result):
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


# Effect classes. The vocabulary is from the system-boundary argument in the
# Cordis paper (section 6.1): an operation reaching outside the boundary
# acquires a revertible record and then EMITS, and the emission is what cannot
# be taken back. So the split the loop cares about is not "read vs write", it
# is whether an inverse exists at all.
#
#   read                    - observes, changes nothing
#   revertible_write        - changes state this system owns and can restore
#   withheld_emission       - composes something a human must release (MCP draft
#                             mode: the model writes, a person sends)
#   unrecoverable_emission  - data leaves to another party; no inverse exists
#
# Deliberately NOT a class: "compensable" (an emission with an application
# supplied undo, e.g. delete the file you created, refund the charge). Draft
# mode covers every emission our connectors currently reach, and one more class
# with one speculative user is the abstraction not to build. Revive it the day
# a connector offers a real undo we would actually call.
EFFECTS = ("read", "revertible_write", "withheld_emission", "unrecoverable_emission")

# Everything that is not a read changes the world. This is the predicate the
# loop used to spell as a literal set of nine office tool names, which meant a
# new domain's writes were invisible to the repeat check, the date guard and
# the unrequested report until somebody remembered to edit that set.
WORLD_CHANGING = frozenset(EFFECTS) - {"read"}

TOOLS = {
    "list_emails": {
        "effect": "read",
        "simulated_connector": True,
        "desc": "List all emails in the inbox (id, from, date, subject). Newest first.",
        "params": {},
        "example": {"tool": "list_emails", "args": {}},
        "run": lambda w, m, a: w.list_emails(),
    },
    "read_email": {
        "effect": "read",
        "simulated_connector": True,
        "desc": "Read the full body of one email by its id.",
        "params": {"id": ("string, an email id like 'e3'", True)},
        "example": {"tool": "read_email", "args": {"id": "e2"}},
        "run": lambda w, m, a: w.read_email(a["id"]),
    },
    "send_email": {
        "effect": "unrecoverable_emission",
        "simulated_connector": True,
        "desc": "Send an email.",
        "params": {"to": ("string, recipient address", True),
                   "subject": ("string", True),
                   "body": ("string", True)},
        "example": {"tool": "send_email", "args": {"to": "dana@corp.com", "subject": "Re: numbers",
                                                   "body": "Got it, thanks!"}},
        "run": lambda w, m, a: w.send_email(a["to"], a.get("subject", ""), a.get("body", "")),
    },
    "list_events": {
        "effect": "read",
        "simulated_connector": True,
        "desc": "List calendar events, optionally only for one date.",
        "params": {"date": ("string YYYY-MM-DD, optional - omit for all events", False)},
        "example": {"tool": "list_events", "args": {"date": "2026-07-22"}},
        "run": lambda w, m, a: w.list_events(a.get("date")),
    },
    "add_event": {
        "effect": "revertible_write",
        "simulated_connector": True,
        "desc": "Add an event to the calendar.",
        "params": {"title": ("string", True),
                   "date": ("string YYYY-MM-DD", True),
                   "start_time": ("string 24h HH:MM", True),
                   "end_time": ("string 24h HH:MM", True),
                   "attendees": ("list of email strings, optional", False),
                   "location": ("string, optional", False)},
        "example": {"tool": "add_event", "args": {"title": "Budget review", "date": "2026-07-21",
                                                  "start_time": "13:00", "end_time": "14:00",
                                                  "attendees": ["sam@corp.com"]}},
        "run": lambda w, m, a: w.add_event(a["title"], a["date"], a["start_time"], a["end_time"],
                                           a.get("attendees"), a.get("location")),
    },
    "update_event": {
        "effect": "revertible_write",
        "simulated_connector": True,
        "desc": "Change an existing calendar event: move it, rename it, or change who is "
                "coming. Give only the fields you are changing. Use this to move or "
                "reschedule a meeting - adding a new event leaves the old one in place.",
        "params": {"id": ("string, an event id like 'c2' from list_events", True),
                   "title": ("string, optional", False),
                   "date": ("string YYYY-MM-DD, optional", False),
                   "start_time": ("string 24h HH:MM, optional", False),
                   "end_time": ("string 24h HH:MM, optional", False),
                   "attendees": ("list of email strings, optional", False),
                   "location": ("string, optional", False)},
        "example": {"tool": "update_event", "args": {"id": "c2", "date": "2026-07-23",
                                                     "start_time": "09:00", "end_time": "10:00"}},
        "run": lambda w, m, a: w.update_event(a["id"], a.get("title"), a.get("date"),
                                              a.get("start_time"), a.get("end_time"),
                                              a.get("location"), a.get("attendees")),
    },
    "cancel_event": {
        "effect": "revertible_write",
        "simulated_connector": True,
        "desc": "Remove an event from the calendar.",
        "params": {"id": ("string, an event id like 'c2' from list_events", True)},
        "example": {"tool": "cancel_event", "args": {"id": "c4"}},
        "run": lambda w, m, a: w.cancel_event(a["id"]),
    },
    "send_message": {
        "effect": "unrecoverable_emission",
        "simulated_connector": True,
        "desc": "Send a chat/instant message to a person.",
        "params": {"to": ("string, contact name", True),
                   "text": ("string, the message", True)},
        "example": {"tool": "send_message", "args": {"to": "sam", "text": "Running 5 min late."}},
        "run": lambda w, m, a: w.send_message(a["to"], a["text"]),
    },
    "set_reminder": {
        "effect": "revertible_write",
        "simulated_connector": True,
        "desc": "Set a reminder for yourself at a specific date and time.",
        "params": {"text": ("string, what to be reminded of", True),
                   "date": ("string YYYY-MM-DD", True),
                   "time": ("string 24h HH:MM", True)},
        "example": {"tool": "set_reminder", "args": {"text": "send invoice", "date": "2026-07-22",
                                                     "time": "09:00"}},
        "run": lambda w, m, a: w.set_reminder(a["text"], a["date"], a["time"]),
    },
    "create_presentation": {
        "effect": "revertible_write",
        "writes_file": True,
        "desc": "Create a real .pptx PowerPoint file. Each slide is an object with a "
                "'title' and an optional 'bullets' list. A first slide without bullets "
                "becomes a title slide.",
        "params": {"filename": ("string ending in .pptx", True),
                   "slides": ("list of {\"title\": str, \"bullets\": [str, ...]}", True)},
        "example": {"tool": "create_presentation",
                    "args": {"filename": "plan.pptx",
                             "slides": [{"title": "2027 Plan"},
                                        {"title": "Goals", "bullets": ["Grow 20%", "Ship v2", "Hire 3"]}]}},
        "run": lambda w, m, a: office.create_presentation(w.files_dir, a["filename"], a["slides"]),
    },
    "create_spreadsheet": {
        "effect": "revertible_write",
        "writes_file": True,
        "desc": "Create a real .xlsx Excel file from a list of rows (first row is usually "
                "headers). A cell string starting with '=' becomes a formula.",
        "params": {"filename": ("string ending in .xlsx", True),
                   "rows": ("list of rows, each row a list of cell values", True),
                   "sheet_name": ("string, optional", False)},
        "example": {"tool": "create_spreadsheet",
                    "args": {"filename": "costs.xlsx",
                             "rows": [["Item", "Cost"], ["Chairs", 400], ["Desks", 900],
                                      ["Total", "=SUM(B2:B3)"]]}},
        "run": lambda w, m, a: office.create_spreadsheet(w.files_dir, a["filename"], a["rows"],
                                                         a.get("sheet_name")),
    },
    "list_files": {
        "effect": "read",
        # A listing is not a mention. The loop harvests filenames out of read
        # results so it can tell a file the task pointed at from one the model
        # invented, and without this flag enumerating the workspace would mark
        # every file in it as something the task named - so the next document
        # write would be questioned about an arbitrary file nobody asked for.
        "lists_files": True,
        "desc": "List the files in the workspace, with size and when each was "
                "last changed. Use it to find out what is here before you "
                "assume a file does or does not exist.",
        "params": {},
        "example": {"tool": "list_files", "args": {}},
        "run": lambda w, m, a: w.list_files(),
    },
    "read_spreadsheet": {
        "effect": "read",
        "opens": (".xlsx",),
        "desc": "Read back the cell contents of an existing .xlsx file.",
        "params": {"filename": ("string ending in .xlsx", True)},
        "example": {"tool": "read_spreadsheet", "args": {"filename": "costs.xlsx"}},
        "run": lambda w, m, a: office.read_spreadsheet(w.files_dir, a["filename"]),
    },
    "think": {
        "effect": "read",
        "desc": "Think out loud about the task. Use this to reason before acting. "
                "Has no external effect.",
        "params": {"thought": ("string", True)},
        "example": {"tool": "think", "args": {"thought": "Wednesday has 3 meetings; I should list them in time order."}},
        "run": lambda w, m, a: "Noted. Continue with your next action.",
    },
    "save_memory": {
        "effect": "revertible_write",
        "desc": "Save a lasting preference or fact about the user and the people they "
                "work with, so it persists across future tasks. Only things that stay "
                "true: who someone is, how the user likes to work. NEVER the current "
                "contents of the inbox or calendar - those change, and a saved copy "
                "becomes wrong without ever being corrected.",
        "params": {"fact": ("string, something that will still be true next month", True)},
        "example": {"tool": "save_memory", "args": {"fact": "User's manager is Sam."}},
        "run": lambda w, m, a: m.save(a["fact"]),
    },
    "recall_memories": {
        "effect": "read",
        "desc": "Search long-term memory for saved facts relevant to a query.",
        "params": {"query": ("string", True)},
        "example": {"tool": "recall_memories", "args": {"query": "meeting preferences"}},
        "run": lambda w, m, a: (m.search(a["query"], k=5) or "no matching memories"),
    },
    "done": {
        "effect": "read",
        "desc": "Call this exactly once, when the entire task is finished, with a short summary.",
        "params": {"summary": ("string", True)},
        "example": {"tool": "done", "args": {"summary": "Booked the meeting and messaged Sam."}},
        "run": None,  # handled by the agent loop
    },
}


# Fail at import, not at the first call that needed the answer. A tool with no
# effect class would silently read as a read, which is the one wrong default:
# absence of a declaration is not permission to change the world.
for _name, _spec in TOOLS.items():
    if _spec.get("effect") not in EFFECTS:
        raise ValueError(f"tool {_name!r} declares effect {_spec.get('effect')!r}; "
                         f"must be one of {', '.join(EFFECTS)}")
del _name, _spec


# Two more optional per-tool declarations, both domain-neutral:
#   "opens": (".ext", ...)  this tool reads a file of that type
#   "writes_file": True     this tool produces a file
# The loop used to spell both as office tool names and an .xlsx regex, which
# meant the unread-file guard only ever fired for spreadsheets and decks.


def openable_extensions(registry=None):
    """Every file extension some registered tool can open."""
    reg = registry if registry is not None else TOOLS
    out = set()
    for spec in reg.values():
        out.update(spec.get("opens") or ())
    return frozenset(out)


def opener_for(path, registry=None):
    """The name of a tool that can open this file, or None."""
    reg = registry if registry is not None else TOOLS
    low = str(path).lower()
    for name, spec in reg.items():
        if any(low.endswith(ext.lower()) for ext in (spec.get("opens") or ())):
            return name
    return None


# --------------------------------------------------- registry mutation ----
#
# Every change to the shared registry goes through one primitive that returns
# its own inverse. Three modules mutate TOOLS - the MCP bridge, the real-file
# tools, and the two restrict_* helpers - and each used to do it by hand with a
# partial undo or none at all: mcp_bridge.shutdown() closed its subprocesses
# but left their tools in the registry forever, and neither restrict_ function
# could be reversed at all.
#
# This is the paper's revertible-effect idea at the only scale we need it:
# registration and its undo are written in one place, so "did we clean up
# completely" stops being a question a reviewer has to answer by reading.

_ABSENT = object()


def edit_registry(changes, registry=None):
    """Apply {name: spec, other: None} and return a callable restoring exactly
    the previous state. None removes. The undo is idempotent and restores what
    was shadowed, not merely what was added."""
    reg = registry if registry is not None else TOOLS
    before = {n: reg.get(n, _ABSENT) for n in changes}
    for name, spec in changes.items():
        if spec is None:
            reg.pop(name, None)
        else:
            reg[name] = spec

    def undo():
        for name, prev in before.items():
            if prev is _ABSENT:
                reg.pop(name, None)
            else:
                reg[name] = prev
    return undo


def register(name, spec, registry=None):
    """Add one tool. Returns the disposer that removes it again."""
    return edit_registry({name: spec}, registry)


def suppress(names, registry=None):
    """Hide tools without destroying them. Returns the disposer that restores
    every one that was actually present."""
    return edit_registry({n: None for n in names}, registry)


def simulated_connector_tools(registry=None):
    """Tools that simulate a connector a real account would replace.

    A run with real mail wired in should not also carry a fake inbox: two
    list-mail tools is a coin flip for a small model. Declared per tool so the
    MCP bridge can drop exactly these and leave everything else standing.
    """
    reg = registry if registry is not None else TOOLS
    return frozenset(n for n, s in reg.items() if s.get("simulated_connector"))


def document_tools(registry=None):
    """Tools that read or write a document file, either direction."""
    reg = registry if registry is not None else TOOLS
    return frozenset(n for n, s in reg.items()
                     if s.get("writes_file") or s.get("opens"))


def file_writing_tools(registry=None):
    """Every registered tool that produces a file."""
    reg = registry if registry is not None else TOOLS
    return frozenset(n for n, s in reg.items() if s.get("writes_file"))


def effect_of(name, registry=None):
    """The effect class of one tool. Unknown tools are treated as world-changing,
    for the same reason the check above exists."""
    spec = (registry or TOOLS).get(name)
    return spec.get("effect", "unrecoverable_emission") if spec else "unrecoverable_emission"


def write_tool_names(registry=None):
    """Every registered tool that changes the world. Derived, never a literal:
    a domain that registers its own tools gets the guards for free."""
    reg = registry if registry is not None else TOOLS
    return frozenset(n for n, s in reg.items()
                     if s.get("effect", "unrecoverable_emission") in WORLD_CHANGING)


def read_tool_names(registry=None):
    """Every registered tool that only observes."""
    reg = registry if registry is not None else TOOLS
    return frozenset(n for n, s in reg.items() if s.get("effect") == "read")


def tool_docs(with_examples):
    """Render the tool documentation block for a system prompt."""
    lines = []
    for name, spec in TOOLS.items():
        lines.append(f"- {name}: {spec['desc']}")
        for p, (tdesc, req) in spec["params"].items():
            lines.append(f"    {p} ({'required' if req else 'optional'}): {tdesc}")
        if with_examples:
            lines.append(f"    example: {json.dumps(spec['example'], ensure_ascii=False)}")
    return "\n".join(lines)


def validate_call(name, args):
    """Return a list of problems with a proposed call (harness uses this to give
    corrective feedback BEFORE execution; raw condition executes directly)."""
    problems = []
    if name not in TOOLS:
        return [f"unknown tool {name!r}; valid tools: {', '.join(TOOLS)}"]
    if not isinstance(args, dict):
        return ["'args' must be a JSON object"]
    spec = TOOLS[name]
    for p, (tdesc, req) in spec["params"].items():
        if req and (p not in args or args[p] in (None, "")):
            problems.append(f"missing required parameter '{p}' ({tdesc})")
    for p in args:
        if p not in spec["params"]:
            problems.append(f"unknown parameter '{p}' (valid: {', '.join(spec['params']) or 'none'})")
    return problems


# Optional observation hook (the web UI sets it): hook(name, args, ok, obs)
# after every executed call, with the arguments as actually run - i.e. after the
# harness repaired and normalized them. None for the benchmark.
TOOL_HOOK = None


def execute(name, args, world, mem):
    """Execute a tool call. Returns (ok, observation_string). Identical in both
    conditions - errors come back as readable messages the model can react to."""
    ok, obs = _execute(name, args, world, mem)
    if TOOL_HOOK:
        TOOL_HOOK(name, args, ok, obs)
    return ok, obs


def _execute(name, args, world, mem):
    if name not in TOOLS:
        return False, f"ERROR: unknown tool {name!r}. Valid tools: {', '.join(TOOLS)}"
    spec = TOOLS[name]
    if not isinstance(args, dict):
        args = {}
    try:
        result = spec["run"](world, mem, args)
        obs = _fmt(result)
        world.log(name, args, True, obs)
        return True, obs
    except ToolError as e:
        world.log(name, args, False, str(e))
        return False, f"ERROR: {e}"
    except KeyError as e:
        msg = f"missing required parameter {e.args[0]!r}"
        world.log(name, args, False, msg)
        return False, f"ERROR: {msg}"
    except Exception as e:  # keep the episode alive on any tool bug
        world.log(name, args, False, repr(e))
        return False, f"ERROR: {type(e).__name__}: {e}"
