"""Assert the safety guarantees of the MCP wiring, without credentials.

Runs the real mcp_bridge against mcp/selftest_server.py, so it exercises the
actual subprocess, the actual JSON-RPC handshake and the actual classifier —
not a mock of them.

    python3 -m mcp.test_bridge        (from the standalone/ directory)

Each check is a claim made in mcp/README.md. If one fails, the README is lying.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import mcp_bridge, mcp_config          # noqa: E402
from harness.tools import TOOLS                     # noqa: E402
from harness.world import ToolError, World          # noqa: E402

FAILURES = []


def check(label, condition):
    print(f"  {'pass' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)


def reset():
    """Tear the bridge down between modes — it mutates a process-global registry."""
    mcp_bridge.shutdown()
    for name in list(mcp_bridge._INJECTED):
        TOOLS.pop(name, None)
    mcp_bridge._INJECTED.clear()
    mcp_bridge.WRITE_TOOLS.clear()


def start(mode, confirm=None):
    servers = mcp_config.names_to_servers(["selftest"], mode=mode)
    return mcp_bridge.enable(servers, confirm=confirm, mode=mode)


def main():
    print("draft mode")
    denied = []
    start("draft", confirm=lambda a, d: denied.append(d) or False)

    check("send_mail is dropped (transmits)", "mail_send_mail" not in TOOLS)
    check("reply_mail is dropped (transmits)", "mail_reply_mail" not in TOOLS)
    check("login is dropped (registry drop list)", "mail_login" not in TOOLS)
    check("draft_mail survives (composing is not sending)", "mail_draft_mail" in TOOLS)
    check("list_mail survives", "mail_list_mail" in TOOLS)
    check("modify_mail is a WRITE via the registry override",
          "mail_modify_mail" in mcp_bridge.WRITE_TOOLS)
    check("list_mail is NOT a write", "mail_list_mail" not in mcp_bridge.WRITE_TOOLS)

    world = World(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "_testworkspace"), persistent=False)

    # A read reaches the server and returns its content, unconfirmed.
    out = TOOLS["mail_list_mail"]["run"](world, None, {})
    check("a read call returns real server content", "Q3 budget review" in out)
    check("a read call asked for no confirmation", not denied)

    # A write is confirmed, and a decline is terminal rather than retried.
    try:
        TOOLS["mail_draft_mail"]["run"](world, None, {"to": "a@b.c", "body": "hi"})
        check("a declined write raises ToolError", False)
    except ToolError as e:
        check("a declined write raises ToolError", True)
        check("the decline tells the model not to retry", "not retry" in str(e).lower())
    check("the write was actually put to the user", len(denied) == 1)

    # restrict_to_mcp removes the simulated inbox so the model can't confuse them.
    had_sim = "list_emails" in TOOLS
    mcp_bridge.restrict_to_mcp()
    check("the simulated office inbox is dropped", "list_emails" not in TOOLS)
    check("  (it existed before restriction)", had_sim)
    check("memory/think/done survive restriction",
          {"think", "done", "save_memory"} <= set(TOOLS))

    reset()
    print("\nlive mode")
    start("live", confirm=lambda a, d: True)
    check("send_mail is exposed", "mail_send_mail" in TOOLS)
    check("send_mail is a write, so it is confirmed",
          "mail_send_mail" in mcp_bridge.WRITE_TOOLS)

    reset()
    print("\nread_only mode")
    start("read_only", confirm=lambda a, d: True)
    check("draft_mail is dropped", "mail_draft_mail" not in TOOLS)
    check("list_mail survives", "mail_list_mail" in TOOLS)

    reset()
    print("\nconfig")
    check("an unknown server name fails loudly", _raises_config_error())
    check("the tool-count guard fires over budget",
          bool(mcp_config.count_warnings([{"id": "x", "tools": ["t"] * 40,
                                           "writes": []}])))

    print(f"\n{'ALL CHECKS PASSED' if not FAILURES else str(len(FAILURES)) + ' FAILED'}")
    return 1 if FAILURES else 0


def _raises_config_error():
    try:
        mcp_config.names_to_servers(["nope-not-real"])
        return False
    except mcp_config.ConfigError:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
