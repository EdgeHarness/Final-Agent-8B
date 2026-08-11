"""A fake mail MCP server, so the bridge can be tested without credentials.

Everything about the real integration — OAuth, Node, a network — is someone
else's dependency, which makes "is our wiring correct?" impossible to answer on
a fresh machine. This server answers it: it speaks the same stdio JSON-RPC an
npx server speaks, and its tool names are chosen to exercise every branch of
mcp_bridge's classifier.

    python3 -m mcp.selftest_server            # spoken to over stdin/stdout
    python3 agents/8b/run_agent.py --mcp selftest --mcp-list

Expected in draft mode:
    list_mail       read      exposed, no confirmation
    read_mail       read      exposed, no confirmation
    draft_mail      write     exposed, confirmed      (composing is not sending)
    modify_mail     write     exposed, confirmed      (ONLY via the registry's
                                                       write_tools override —
                                                       "modify" is not a verb
                                                       mcp_bridge._WRITE_RE knows)
    send_mail       —         DROPPED (transmits to a person)
    reply_mail      —         DROPPED (transmits to a person)
    login           —         DROPPED (registry drop list)

Nothing here touches a real account; the "mailbox" is three dicts.
"""
import json
import sys

MAILBOX = [
    {"id": "m1", "from": "jordan@example.com", "subject": "Q3 budget review",
     "body": "Can you send the updated figures before Thursday?"},
    {"id": "m2", "from": "sam@example.com", "subject": "Lunch?",
     "body": "Free at 12:30 tomorrow?"},
    {"id": "m3", "from": "noreply@example.com", "subject": "Your receipt",
     "body": "Order #4471 confirmed."},
]

TOOLS = [
    {"name": "list_mail", "description": "List messages in the inbox.",
     "inputSchema": {"type": "object", "properties": {
         "limit": {"type": "integer", "description": "how many to return"}}}},
    {"name": "read_mail", "description": "Read one message by id.",
     "inputSchema": {"type": "object",
                     "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "draft_mail", "description": "Create a draft reply. Does not send.",
     "inputSchema": {"type": "object", "properties": {
         "to": {"type": "string"}, "subject": {"type": "string"},
         "body": {"type": "string"}}, "required": ["to", "body"]}},
    {"name": "modify_mail", "description": "Add or remove labels on a message.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "string"}, "add": {"type": "array"}}, "required": ["id"]}},
    {"name": "send_mail", "description": "Send a message immediately.",
     "inputSchema": {"type": "object", "properties": {
         "to": {"type": "string"}, "body": {"type": "string"}},
         "required": ["to", "body"]}},
    {"name": "reply_mail", "description": "Reply to a message immediately.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "string"}, "body": {"type": "string"}},
         "required": ["id", "body"]}},
    {"name": "login", "description": "Start the device-code flow. Blocks.",
     "inputSchema": {"type": "object", "properties": {}}},
]

DRAFTS = []


def call(name, args):
    if name == "list_mail":
        limit = args.get("limit") or len(MAILBOX)
        return "\n".join(f"{m['id']}  {m['from']}  {m['subject']}"
                         for m in MAILBOX[:limit])
    if name == "read_mail":
        for m in MAILBOX:
            if m["id"] == args.get("id"):
                return f"from: {m['from']}\nsubject: {m['subject']}\n\n{m['body']}"
        raise KeyError(f"no message {args.get('id')!r}")
    if name == "draft_mail":
        DRAFTS.append(args)
        return f"draft {len(DRAFTS)} saved to {args.get('to')} (not sent)"
    if name == "modify_mail":
        return f"labels updated on {args.get('id')}"
    if name in ("send_mail", "reply_mail"):
        return "SENT — if you are reading this in draft mode, the bridge leaked."
    if name == "login":
        return "LOGIN — if the model reached this, the drop list failed."
    raise KeyError(f"unknown tool {name!r}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, rid = msg.get("method"), msg.get("id")
        if rid is None:
            continue                      # a notification; nothing to answer
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "selftest-mail", "version": "1.0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg.get("params") or {}
            try:
                text = call(params.get("name"), params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": text}]}
            except Exception as e:
                result = {"content": [{"type": "text", "text": str(e)}],
                          "isError": True}
        else:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"no method {method}"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
