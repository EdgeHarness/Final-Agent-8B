"""Ollama-API shim in front of llama-server, so the harness needs zero changes.

harness/llm.py hardcodes OLLAMA_URL = http://127.0.0.1:11434 and speaks Ollama's
/api/chat. llama-server speaks OpenAI's /v1/chat/completions. This translates
between them, listening on 11434 so the agent cannot tell the difference.

    # 1. stop Ollama first — it owns port 11434
    # 2. .\serve-xelite.ps1 -Bin ... -Model ...        (llama-server on :8080)
    # 3. python ollama_shim.py                          (shim on :11434)
    # 4. cd ..\agents\8b ; python run_agent.py "..."

Translated per call:
    options.temperature  -> temperature
    options.seed         -> seed
    options.num_predict  -> max_tokens
    format: "json"       -> response_format {"type": "json_object"}
    stream: true         -> SSE upstream, re-emitted as Ollama's NDJSON
    prompt_eval_count / eval_count  <- usage.prompt_tokens / completion_tokens

options.num_ctx is NOT forwarded: llama-server fixes the context at startup
(-c). Set it there instead. Everything else the harness sends (keep_alive,
model) is accepted and ignored — one server, one resident model.

Stdlib only.
"""
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "http://127.0.0.1:8080"
LISTEN = ("127.0.0.1", 11434)
TIMEOUT = 900


def to_openai(req):
    """Ollama /api/chat body -> OpenAI /v1/chat/completions body."""
    opts = req.get("options") or {}
    body = {
        "model": req.get("model", "local"),
        "messages": req.get("messages", []),
        "stream": bool(req.get("stream")),
    }
    if "temperature" in opts:
        body["temperature"] = opts["temperature"]
    if "seed" in opts:
        body["seed"] = opts["seed"]
    if opts.get("num_predict"):
        body["max_tokens"] = opts["num_predict"]
    if req.get("format") == "json":
        body["response_format"] = {"type": "json_object"}
    if body["stream"]:
        # ask llama-server for a trailing usage chunk so token counts survive
        body["stream_options"] = {"include_usage": True}
    return body


def post_upstream(body):
    data = json.dumps(body).encode()
    r = urllib.request.Request(f"{UPSTREAM}/v1/chat/completions", data=data,
                               headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(r, timeout=TIMEOUT)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # the agent prints its own progress; keep the console clean

    def _send(self, code, payload, ctype="application/json"):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        # enough for anything that probes whether "Ollama" is up
        if self.path.startswith("/api/tags"):
            self._send(200, {"models": [{"name": "local", "model": "local"}]})
        elif self.path in ("/", "/api/version"):
            self._send(200, {"version": "llama.cpp-shim"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/api/chat"):
            self._send(404, {"error": f"shim only implements /api/chat, got {self.path}"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            self._send(400, {"error": f"bad JSON: {e}"})
            return

        body = to_openai(req)
        try:
            resp = post_upstream(body)
        except urllib.error.URLError as e:
            self._send(502, {"error": f"llama-server unreachable at {UPSTREAM}: {e}"})
            return

        if body["stream"]:
            self._relay_stream(resp, req.get("model", "local"))
        else:
            data = json.loads(resp.read())
            usage = data.get("usage") or {}
            self._send(200, {
                "model": req.get("model", "local"),
                "message": {"role": "assistant",
                            "content": data["choices"][0]["message"]["content"]},
                "done": True,
                "done_reason": data["choices"][0].get("finish_reason", "stop"),
                "prompt_eval_count": usage.get("prompt_tokens", 0),
                "eval_count": usage.get("completion_tokens", 0),
            })

    def _relay_stream(self, resp, model):
        """SSE in, Ollama NDJSON out — one JSON object per line, `done` last.

        harness/llm.py._chat_streamed json.loads() every non-empty line and
        stops at the object whose "done" is true, so the shapes must match.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        # The body length is unknown up front, and we do not frame it as
        # chunked. Under HTTP/1.1 that leaves connection-close as the only
        # legal terminator — without it the client blocks forever on a
        # keep-alive socket waiting for a body end that never arrives.
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        usage = {}
        try:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    usage = chunk["usage"]  # final include_usage chunk
                choices = chunk.get("choices") or []
                piece = choices[0].get("delta", {}).get("content", "") if choices else ""
                if piece:
                    self._line({"model": model,
                                "message": {"role": "assistant", "content": piece},
                                "done": False})
            self._line({"model": model, "message": {"role": "assistant", "content": ""},
                        "done": True, "done_reason": "stop",
                        "prompt_eval_count": usage.get("prompt_tokens", 0),
                        "eval_count": usage.get("completion_tokens", 0)})
        except (BrokenPipeError, ConnectionResetError):
            pass  # agent hung up mid-stream

    def _line(self, obj):
        self.wfile.write(json.dumps(obj).encode() + b"\n")
        self.wfile.flush()


def main():
    global UPSTREAM
    if len(sys.argv) > 1:
        UPSTREAM = sys.argv[1].rstrip("/")
    try:
        with urllib.request.urlopen(f"{UPSTREAM}/health", timeout=5):
            up = "reachable"
    except Exception as e:
        up = f"NOT reachable ({e}) — start serve-xelite.ps1 first"
    print(f"  upstream llama-server : {UPSTREAM}  [{up}]")
    print(f"  listening as Ollama   : http://{LISTEN[0]}:{LISTEN[1]}/api/chat")
    print("  (stop the real Ollama first, or this port is already taken)")
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()


if __name__ == "__main__":
    main()
