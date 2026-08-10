"""Agent Lab as a desktop window instead of a browser tab.

    python3 -m webui.app

Starts the same loopback server webui/server.py starts, then opens it in a
native window — own dock/taskbar icon, no URL bar, no tab strip. The server runs
on a daemon thread in this process, so closing the window ends everything,
including any run in flight.

pywebview is OPTIONAL. Without it this falls back to the browser, which is the
existing behaviour, and prints how to get the window:

    pip install pywebview

It uses the OS webview — WebKit on macOS, WebView2 on Windows — so there is no
bundled Chromium and nothing to build for arm64. That matters on the Snapdragon
box, where an Electron shell would mean shipping a second browser.
"""
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

from webui import server as srv  # noqa: E402

WINDOW = {"width": 1440, "height": 940, "min_size": (1060, 680)}


def serve(port):
    """The server, minus the console banner and the browser launch."""
    srv.Server(("127.0.0.1", port), srv.Handler).serve_forever()


def wait_until_up(url, timeout=15):
    """Don't point the window at a socket that isn't listening yet — a webview
    that loads a connection error does not retry, it just sits there empty."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def main():
    port = srv.free_port(int(os.environ.get("AGENT_LAB_PORT", srv.DEFAULT_PORT)))
    url = f"http://127.0.0.1:{port}"

    try:
        import webview
    except ImportError:
        print("  pywebview not installed — opening in your browser instead.")
        print("  For a real app window:  pip install pywebview\n")
        os.environ.pop("AGENT_LAB_NO_BROWSER", None)
        os.environ["AGENT_LAB_PORT"] = str(port)
        return srv.main()

    threading.Thread(target=serve, args=(port,), daemon=True).start()
    if not wait_until_up(url):
        print(f"  server did not come up on {url}")
        return

    tags = srv.installed_tags()
    print(f"\n  Agent Lab  →  {url}  (app window)")
    if tags is None:
        print("  ollama     NOT RUNNING — start it, then reload the window")
    else:
        print(f"  ollama     up, {len(tags)} model(s) installed")
    print("  Close the window to stop.\n")

    webview.create_window("Agent Lab", url, **WINDOW)
    webview.start()          # blocks until the window closes

    if srv.RUNS.current:
        srv.RUNS.current.stop()
    print("  stopped.\n")


if __name__ == "__main__":
    main()
