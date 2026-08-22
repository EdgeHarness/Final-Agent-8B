"""MCP tool bridge — let the on-device agent use real MCP servers as tools.

This is how the agent reaches real Gmail / Outlook (and anything else with an MCP
server) without the harness reimplementing Graph or the Gmail API. It speaks the
Model Context Protocol's stdio transport directly — newline-delimited JSON-RPC
2.0 over a child process's stdin/stdout — so it needs no `mcp` SDK and stays
synchronous, matching the rest of the harness. (Same subprocess-over-stdio shape
webui/runner.py already uses.)

What it does, mirroring fs_tools.py exactly:
    enable(servers, ...)  launches each MCP server, lists its tools, adapts every
                          tool into the harness TOOLS spec, and injects it into
                          the shared registry *in this process only*.
    WRITE_TOOLS           the injected tools that change the world, for the loop's
                          repeat-suppression and the agent's EXTRA_WRITE_TOOLS.
    shutdown()            terminate the server subprocesses (also atexit).

The benchmark never imports this, so bench/ keeps its 14-tool simulated registry
and raw-vs-harness stays comparable.

SAFETY. These tools act on real accounts. Three guards, all on by default:
  - mode="draft" drops send/forward/transmit tools, keeping create-draft, read,
    list, and tentative-event tools. The model composes; a human sends. Flip to
    mode="live" to allow real sends (still confirmed).
  - every world-changing call goes through the same confirm(action, detail)
    callback fs_tools uses — a decline raises a ToolError telling the model not
    to retry.
  - per-server allow/drop lists override the heuristics when a server names its
    tools in a way the name-based classifier gets wrong.

NOTE ON "nothing leaves the machine": model inference still never leaves — the
Ollama loopback assertion in the runners still holds. It is the *tools* that now
reach a provider's cloud (Google / Microsoft). That is a deliberate, flagged
departure; keep it out of bench/.
"""
import atexit
import itertools
import json
import os
import queue
import re
import subprocess
import threading
import time

from . import tools
from .tools import TOOLS
from .world import ToolError

PROTOCOL_VERSION = "2025-06-18"   # we send this; we accept whatever the server negotiates back
CLIENT_INFO = {"name": "sail-harness", "version": "0.1"}
CALL_TIMEOUT = 120                # seconds to wait for one tools/call result
INIT_TIMEOUT = 60                 # seconds to wait for the initialize handshake
OBS_CLIP = 4000                   # clip a tool result before it enters the transcript

# Populated by enable(); consumed by the runner (agent_mod.EXTRA_WRITE_TOOLS) and
# used to decide which repeated calls may be suppressed.
WRITE_TOOLS = set()

_CLIENTS = []                     # live MCPClient processes, terminated on shutdown
_CONFIRM = None                   # callable(action, detail) -> bool, or None
_INJECTED = set()                 # harness tool names this module added, for a clean teardown

# A world-changing verb anywhere in the tool name. Heuristic; overridable per server.
_WRITE_RE = re.compile(
    r"(send|create|add|update|patch|delete|remove|trash|archive|move|reply|"
    r"forward|draft|schedule|accept|decline|cancel|mark|write|post|put|set)",
    re.I)
# Tools that actually TRANSMIT to another person. Dropped in draft mode.
_TRANSMIT_RE = re.compile(r"(send|forward|reply)", re.I)
# Tools that COMPOSE something a person must release. These are the point of
# draft mode: the model writes, a human sends.
_DRAFT_RE = re.compile(r"draft", re.I)


# --------------------------------------------------------------- JSON-RPC ----

class MCPClient:
    """One MCP server subprocess, spoken to over stdio JSON-RPC 2.0.

    Synchronous: the harness loop issues one tool call at a time. A reader thread
    drains stdout into a queue so a request can wait for its matching id without
    blocking on interleaved notifications or log lines."""

    def __init__(self, server_id, command, args=None, env=None, cwd=None):
        self.id = server_id
        self.name = server_id
        self._ids = itertools.count(1)
        self._inbox = queue.Queue()
        self._write_lock = threading.Lock()
        full_env = dict(os.environ)
        full_env.update(env or {})
        try:
            self.proc = subprocess.Popen(
                [command, *(args or [])],
                cwd=cwd, env=full_env, text=True, encoding="utf-8",
                errors="replace", bufsize=1,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise ToolError(f"MCP server {server_id!r}: command {command!r} not found. "
                            f"Is it installed / on PATH?")
        self._stderr_tail = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._initialize()

    def _read_stdout(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._inbox.put(json.loads(line))
            except ValueError:
                pass  # non-JSON banner/log line on stdout — ignore, not our protocol
        self._inbox.put({"__eof__": True})

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self._stderr_tail.append(line)
            del self._stderr_tail[:-40]  # keep only the last 40 lines for error context

    def _send(self, msg):
        with self._write_lock:
            if self.proc.poll() is not None:
                raise ToolError(f"MCP server {self.id!r} has exited "
                                f"({''.join(self._stderr_tail)[-400:].strip()})")
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def _request(self, method, params, timeout):
        rid = next(self._ids)
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        end = time.time() + timeout
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                raise ToolError(f"MCP server {self.id!r}: no response to {method} within {timeout}s")
            try:
                msg = self._inbox.get(timeout=remaining)
            except queue.Empty:
                raise ToolError(f"MCP server {self.id!r}: no response to {method} within {timeout}s")
            if msg.get("__eof__"):
                raise ToolError(f"MCP server {self.id!r} closed the connection "
                                f"({''.join(self._stderr_tail)[-400:].strip()})")
            if msg.get("id") != rid:
                continue  # a notification or an out-of-order reply — not ours
            if "error" in msg:
                err = msg["error"]
                raise ToolError(f"{method} failed: {err.get('message', err)}")
            return msg.get("result", {})

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _initialize(self):
        self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        }, timeout=INIT_TIMEOUT)
        self._notify("notifications/initialized")

    def list_tools(self):
        tools, cursor = [], None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self._request("tools/list", params, timeout=INIT_TIMEOUT)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name, arguments):
        """Return (is_error, text). Text is the joined text content blocks."""
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}},
                               timeout=CALL_TIMEOUT)
        blocks = result.get("content", [])
        parts = []
        for b in blocks:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                else:
                    parts.append(json.dumps(b, ensure_ascii=False, default=str))
        text = "\n".join(p for p in parts if p) or "(no content)"
        return bool(result.get("isError")), text

    def close(self):
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception:
            pass


# -------------------------------------------------------------- adapting ----

def _clip(text, limit=OBS_CLIP):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


# Read-only / derived fields every Graph entity carries. Rendering them wastes
# the context an 8B does not have, and no model should ever set them.
_SCHEMA_NOISE = {"id", "createdDateTime", "lastModifiedDateTime", "changeKey",
                 "etag", "@odata.etag", "@odata.type", "categories"}
_TYPE_DESC_CLIP = 300


def _deref(node, root, seen=()):
    """Follow a local $ref, e.g. '#/$defs/def1'.

    Not optional: ms-365-mcp-server puts every recipient and every start/end
    behind $defs, so without this `toRecipients` and `start` render as bare
    'array'/'any' and the model invents a shape. Measured, not guessed — that
    is where the create-draft-email failures came from."""
    for _ in range(8):
        if not isinstance(node, dict):
            return {}
        ref = node.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return node
        if ref in seen:
            return {}                      # cyclic $ref — stop rather than recurse
        seen = (*seen, ref)
        target = root
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            target = (target or {}).get(part) if isinstance(target, dict) else None
            if target is None:
                return {}
        node = target
    return node if isinstance(node, dict) else {}


def _type_desc(node, root, depth=0, max_depth=2, max_keys=6):
    """Compact one-line type: enum values and nested keys, not just 'object'.

    A bare 'object' tells the model nothing, so it guesses the nesting and the
    server rejects it. Depth and key count are capped because this lands in the
    system prompt of a model with an 8k context."""
    node = _deref(node, root)
    for branch in (node.get("anyOf") or node.get("oneOf") or []):
        b = _deref(branch, root)
        if b.get("type") != "null":
            return _type_desc(b, root, depth, max_depth, max_keys)
    if node.get("enum"):
        return "|".join(json.dumps(v, ensure_ascii=False) for v in node["enum"][:6])
    t = node.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "any")
    if not t:
        t = "object" if node.get("properties") else "any"
    if t == "object" and depth < max_depth:
        props = {k: v for k, v in (node.get("properties") or {}).items()
                 if k not in _SCHEMA_NOISE}
        keys = list(props)[:max_keys]
        if keys:
            inner = ", ".join(f"{k}: {_type_desc(props[k], root, depth + 1, max_depth, max_keys)}"
                              for k in keys)
            return "{" + inner + (", ..." if len(props) > len(keys) else "") + "}"
    if t == "array":
        # The array wrapper does NOT consume a depth level: charging one made
        # `toRecipients` render as '[object]', hiding the very shape the model
        # gets wrong. It is a container, not a level of nesting.
        return "[" + _type_desc(node.get("items"), root, depth, max_depth, max_keys) + "]"
    return t


def _placeholder(schema, root=None, depth=0):
    node = _deref(schema, root if root is not None else {})
    for branch in (node.get("anyOf") or node.get("oneOf") or []):
        b = _deref(branch, root or {})
        if b.get("type") != "null":
            node = b
            break
    if node.get("enum"):
        return node["enum"][0]
    t = node.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if not t:
        t = "object" if node.get("properties") else None
    if t == "object" and depth < 2:
        props = {k: v for k, v in (node.get("properties") or {}).items()
                 if k not in _SCHEMA_NOISE}
        return {k: _placeholder(props[k], root, depth + 1) for k in list(props)[:3]}
    if t == "array" and depth < 2:
        item = _placeholder(node.get("items"), root, depth + 1)
        return [item] if item != "..." else []
    return {"string": "...", "number": 0, "integer": 0,
            "boolean": True, "array": [], "object": {}}.get(t, "...")


def _params_from_schema(schema, root=None, hint=None, hide=()):
    """MCP inputSchema (JSON Schema) -> harness params {name: (type_desc, required)}.

    Every character here lands in the system prompt of a model with an 8k
    context, so a parameter already demonstrated by the example renders as a
    pointer instead of a second, longer copy of the same shape."""
    root = schema if root is None else root
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    hinted = set(hint or ())
    hidden = {h.lower() for h in hide}
    out = {}
    for pname, pschema in props.items():
        pschema = pschema or {}
        if pname.lower() in hidden and pname not in required:
            continue          # server plumbing: costs context, never set by a model
        if pname in hinted:
            t = "object — use the shape in the example exactly"
        else:
            t = _type_desc(pschema, root)
            if len(t) > _TYPE_DESC_CLIP:
                t = t[:_TYPE_DESC_CLIP - 3] + "..."
        desc = str(pschema.get("description", "")).strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "..."
        tdesc = f"{t}" + (f" — {desc}" if desc else "")
        out[pname] = (tdesc, pname in required)
    return out


def _example_for(harness_name, schema, hint=None):
    """A correct call the model can copy.

    A registry `arg_hints` entry wins over anything derived from the schema:
    these servers expose the whole Graph entity (25 top-level keys on a draft),
    so a generated example picks the first few keys, not the ones a human
    actually needs. The hint is the measured, working shape."""
    if hint:
        return {"tool": harness_name, "args": hint}
    props = (schema or {}).get("properties") or {}
    required = (schema or {}).get("required") or list(props)[:2]
    args = {r: _placeholder(props.get(r), schema) for r in list(required)[:3]}
    return {"tool": harness_name, "args": args}


def _is_write(name, server_cfg):
    keep_read = {k.lower() for k in server_cfg.get("read_tools", [])}
    force_write = {k.lower() for k in server_cfg.get("write_tools", [])}
    n = name.lower()
    if n in force_write:
        return True
    if n in keep_read:
        return False
    return bool(_WRITE_RE.search(name))


def _effect_class(mcp_name, is_write):
    """The effect class a real-account tool gets, from its name.

    A read observes. A draft tool composes something a person must release, so
    it is a withheld emission. Everything else that changes a real account is
    called an unrecoverable emission, deliberately: from a name alone we cannot
    tell whether a write reaches another party, and a calendar invite or a
    shared-file edit does. Guessing revertible_write here would be guessing in
    the one direction that costs something. Override the read/write split per
    server with read_tools and write_tools when the heuristic is wrong.
    """
    if not is_write:
        return "read"
    if _DRAFT_RE.search(mcp_name) and not _TRANSMIT_RE.search(mcp_name):
        return "withheld_emission"
    return "unrecoverable_emission"


def _make_executor(client, mcp_name, is_write):
    """The TOOLS 'run' callable. Confirms writes, raises ToolError on MCP error."""
    def run(world, mem, args):
        if is_write and _CONFIRM is not None:
            detail = f"{client.id}: {mcp_name} {json.dumps(args, ensure_ascii=False, default=str)[:240]}"
            if not _CONFIRM("call the tool", detail):
                raise ToolError(f"the user declined the {mcp_name} call. "
                                f"Do not retry it; choose another approach.")
        is_error, text = client.call_tool(mcp_name, args)
        if is_error:
            raise ToolError(_clip(text))
        return _clip(text)
    return run


def _register(client, tool, server_cfg, prefix, draft_only, seen_names):
    mcp_name = tool.get("name")
    if not mcp_name:
        return None
    is_write = _is_write(mcp_name, server_cfg)
    if draft_only and is_write and _TRANSMIT_RE.search(mcp_name) \
            and mcp_name.lower() not in {k.lower() for k in server_cfg.get("write_tools", [])}:
        return None  # draft mode: never expose a tool that transmits to a person
    if mcp_name.lower() in {d.lower() for d in server_cfg.get("drop", [])}:
        return None
    allow = server_cfg.get("allow")
    if allow and mcp_name.lower() not in {a.lower() for a in allow}:
        return None

    harness_name = f"{prefix}{mcp_name}" if prefix else mcp_name
    if harness_name in TOOLS or harness_name in seen_names:
        harness_name = f"{client.id}_{mcp_name}"   # collision: qualify with server id
    schema = tool.get("inputSchema") or {}
    desc = str(tool.get("description", "")).strip().replace("\n", " ")
    tag = "[real, needs confirmation] " if is_write else "[real, read-only] "
    hint = (server_cfg.get("arg_hints") or {}).get(mcp_name)
    TOOLS[harness_name] = {
        "effect": _effect_class(mcp_name, is_write),
        "desc": tag + (desc or mcp_name),
        "params": _params_from_schema(schema, hint=hint,
                                      hide=server_cfg.get("hide_params") or ()),
        "example": _example_for(harness_name, schema, hint),
        "run": _make_executor(client, mcp_name, is_write),
    }
    seen_names.add(harness_name)
    _INJECTED.add(harness_name)
    if is_write:
        WRITE_TOOLS.add(harness_name)
    return harness_name


# ---------------------------------------------------------------- enable ----

def restrict_to_mcp(keep_office_docs=True, keep_extra=()):
    """Drop the simulated-connector tools (fake inbox, calendar, messages) so a
    real-account agent is not carrying both list_emails and a real Gmail list
    tool. Two list-mail tools is a coin flip for a small model.
    Process-local; bench/ is unaffected.

    This used to be an ALLOW-list naming the seven tools that survived, which
    meant every base-layer tool added afterwards silently vanished the moment
    MCP was on. Found by adding list_files and watching the model be told
    'unknown tool list_files' in a real run. It is a DROP-list now, derived
    from what each tool declares, so a new tool survives unless it says it is
    simulating something a real account replaces.

    keep_extra spares tools another module injected. It is no longer strictly
    needed, since a dropped tool must now opt in to being dropped, but it is
    kept so a caller can protect a tool that does declare itself."""
    drop = tools.simulated_connector_tools() - set(_INJECTED) - set(keep_extra)
    if not keep_office_docs:
        drop |= tools.document_tools() - set(_INJECTED) - set(keep_extra)
    for name in drop:
        TOOLS.pop(name, None)


def enable(servers, confirm=None, mode="draft"):
    """Launch each MCP server, list its tools, and inject them into TOOLS.

    servers: list of dicts, each:
        {"id": "gmail", "command": "npx", "args": [...], "env": {...},
         "cwd": "...", "prefix": "gmail_",         # optional name prefix
         "allow": [...], "drop": [...],            # optional tool filters
         "read_tools": [...], "write_tools": [...],# override the write classifier
         "mode": "draft"|"live"|"read_only"}       # per-server, overrides the arg

    mode:
        "draft"     (default) real reads + draft/tentative writes; transmit tools dropped
        "live"      also expose send/forward/reply (still confirmed)
        "read_only" drop every world-changing tool

    Returns a summary list [{id, tools:[...], writes:[...]}], one per server.
    Call once at process start, before run_harness(). Never called by bench/.
    """
    global _CONFIRM
    _CONFIRM = confirm
    summary = []
    for cfg in servers:
        sid = cfg.get("id") or cfg.get("command", "mcp")
        server_mode = cfg.get("mode", mode)
        draft_only = server_mode == "draft"
        read_only = server_mode == "read_only"
        client = MCPClient(sid, cfg["command"], cfg.get("args"), cfg.get("env"), cfg.get("cwd"))
        _CLIENTS.append(client)
        prefix = cfg.get("prefix", "")
        added, writes, seen = [], [], set()
        for tool in client.list_tools():
            if read_only and _is_write(tool.get("name", ""), cfg):
                continue
            name = _register(client, tool, cfg, prefix, draft_only, seen)
            if name:
                added.append(name)
                if name in WRITE_TOOLS:
                    writes.append(name)
        summary.append({"id": sid, "mode": server_mode, "tools": added, "writes": writes})
    return summary


def mail_rules(mode="draft"):
    """Text appended to the harness system prompt (agent_mod.EXTRA_RULES) so the
    model treats the real tools correctly."""
    base = ("\n\nYou also have REAL tools that act on live email/calendar accounts. "
            "Tools tagged [real, ...] touch a real account.\n"
            "- Look before you write: list/read before you create or reply.\n"
            "- Use the exact addresses, dates and times the task gives you; never invent recipients.\n"
            "- A write tool asks the user to confirm. If a call is declined, do not retry it.")
    if mode == "draft":
        base += ("\n- You are in DRAFT mode: create email DRAFTS and TENTATIVE calendar events. "
                 "You cannot send mail or send invitations — a human reviews and sends. "
                 "Creating the draft/tentative event IS completing the task.")
    return base


def shutdown():
    for c in _CLIENTS:
        c.close()
    _CLIENTS.clear()


atexit.register(shutdown)
