"""Minimal Chrome DevTools driver: evaluate JS in the demo window."""
import asyncio, json, sys, urllib.request
import websockets

def page_ws(port=9222):
    d = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
    for t in d:
        if t["type"] == "page" and "8765" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    raise SystemExit("demo page not found on CDP")

async def _run(exprs):
    out = []
    async with websockets.connect(page_ws(), max_size=None) as ws:
        i = 0
        for e in exprs:
            i += 1
            await ws.send(json.dumps({"id": i, "method": "Runtime.evaluate",
                                      "params": {"expression": e, "awaitPromise": True,
                                                 "returnByValue": True}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == i:
                    r = msg.get("result", {}).get("result", {})
                    out.append(r.get("value", r.get("description")))
                    break
    return out

def run(*exprs):
    return asyncio.run(_run(list(exprs)))

if __name__ == "__main__":
    for v in run(*sys.argv[1:]):
        print(v)
