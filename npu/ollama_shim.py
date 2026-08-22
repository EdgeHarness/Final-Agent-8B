"""Ollama-API shim in front of GenieX, so the harness needs zero changes.

harness/llm.py hardcodes OLLAMA_URL = http://127.0.0.1:11434 and speaks Ollama's
/api/chat. GenieX — Qualcomm's on-device runtime, which reaches the Hexagon NPU
through AI Engine Direct (QNN) — speaks OpenAI's /v1/chat/completions instead.
This translates between them, listening on 11434 so the agent cannot tell the
difference, and so Ollama is never involved.

    # 1. make sure Ollama is not running — it owns port 11434
    # 2. geniex pull ai-hub-models/Llama-v3.1-8B-Instruct
    # 3. geniex serve --compute npu --nctx 8192      (:18181, OpenAI API)
    # 4. python -m npu.ollama_shim                   (:11434, auto-discovers)
    # 5. python agents/8b/run_agent.py "..."

Upstream discovery, in order: argv[1], AGENT_NPU_UPSTREAM, GENIEX_HOST, then
GenieX's documented default. Each candidate is probed with /v1/models and the
first that answers wins — cheaper and more honest than shelling out to the CLI,
because a reply proves the server is actually up, not merely installed.

Translated per call:
    options.temperature  -> temperature
    options.seed         -> seed
    options.num_predict  -> max_tokens
    format: "json"       -> response_format {"type": "json_object"}
    stream: true         -> SSE upstream, re-emitted as Ollama's NDJSON
    prompt_eval_count / eval_count  <- usage.prompt_tokens / completion_tokens

The model name the harness sends is REPLACED with the model actually served.
The agent asks for the tag in its config.json; GenieX knows only its own model
ids (`ai-hub-models/...`) and 404s on anything else.

options.num_ctx is NOT forwarded — context is fixed when the model loads. On the
QNN route it is baked into the context binary; on the GGUF route it is `geniex
serve --nctx`, which DEFAULTS TO 4096, i.e. half of what every profile in
harness/profiles.py asks for. Pass --nctx to match the profile or long runs
silently truncate.

Stdlib only.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = None      # resolved at startup by discover()
MODEL = None         # the model id the upstream actually serves
LISTEN = ("127.0.0.1", 11434)
GENIEX_DEFAULT = "http://127.0.0.1:18181"
TIMEOUT = 900


def _normalise(raw):
    """GENIEX_HOST is a bare host:port; arguments usually carry a scheme."""
    raw = (raw or "").strip().rstrip("/")
    if not raw:
        return None
    if not raw.startswith("http"):
        raw = "http://" + raw
    return raw.removesuffix("/v1")   # tolerate the /v1 geniex prints on startup


def models_at(upstream):
    """Model ids GenieX reports, or None if nothing is listening there."""
    try:
        with urllib.request.urlopen(f"{upstream}/v1/models", timeout=5) as r:
            data = json.load(r)
        return [m["id"] for m in (data.get("data") or []) if m.get("id")]
    except Exception:
        return None


def discover():
    """First candidate endpoint that answers -> (upstream, model id).

    GenieX holds a single model in memory at a time (edge devices cannot afford
    more), so the first id it lists is the one that will serve, and the shim
    does not need to choose.
    """
    candidates = [sys.argv[1] if len(sys.argv) > 1 else None,
                  os.environ.get("AGENT_NPU_UPSTREAM"),
                  os.environ.get("GENIEX_HOST"),
                  GENIEX_DEFAULT]
    for raw in candidates:
        upstream = _normalise(raw)
        if not upstream:
            continue
        ids = models_at(upstream)
        if ids is not None:
            return upstream, (ids[0] if ids else None)
    return None, None


def to_openai(req):
    """Ollama /api/chat body -> OpenAI /v1/chat/completions body."""
    opts = req.get("options") or {}
    body = {
        # Not req["model"]: the agent asks for its config.json tag, which
        # GenieX has never heard of and answers with a 404.
        "model": MODEL or req.get("model", "local"),
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
        # ask GenieX for a trailing usage chunk so token counts survive
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
        # The webui probes /api/tags to decide whether a backend is up and to
        # mark the agent's model "installed". Report the served model under BOTH
        # its real id and the tag the agent config asks for, or the dashboard
        # shows "not pulled" for a model that is loaded and working.
        if self.path.startswith("/api/tags"):
            names = {MODEL or "local", os.environ.get("AGENT_NPU_ALIAS", "")} - {""}
            self._send(200, {"models": [{"name": n, "model": n, "size": 0}
                                        for n in sorted(names)]})
        elif self.path.startswith("/api/ps"):
            self._send(200, {"models": [{"name": MODEL or "local", "size_vram": 0}]})
        elif self.path in ("/", "/api/version"):
            self._send(200, {"version": "npu-shim"})
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
            self._send(502, {"error": f"GenieX unreachable at {UPSTREAM}: {e}"})
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


class Server(ThreadingHTTPServer):
    # ThreadingHTTPServer sets allow_reuse_address = 1, and on Windows that lets
    # a second process bind a port another process already holds. The shim would
    # then start, print "listening", and quietly lose every request to the Ollama
    # already on 11434 — an NPU run that is really a CPU run, with plausible
    # output and no error. Refuse the bind instead and say so.
    allow_reuse_address = False


def main():
    global UPSTREAM, MODEL
    UPSTREAM, MODEL = discover()
    if not UPSTREAM:
        sys.exit(f"  no GenieX server answered (tried {GENIEX_DEFAULT}). Start one:\n"
                 "      geniex serve --compute npu --nctx 8192\n"
                 "  or pass its endpoint:  python -m npu.ollama_shim http://127.0.0.1:PORT")
    if not MODEL:
        sys.exit(f"  {UPSTREAM} is up but has no model. Pull one first:\n"
                 "      geniex pull ai-hub-models/Llama-v3.1-8B-Instruct")

    alias = os.environ.get("AGENT_NPU_ALIAS", "")
    print(f"\n  GenieX       : {UPSTREAM}")
    print(f"  serving      : {MODEL}" + (f"  (also announced as {alias})" if alias else ""))
    print(f"  listening as : http://{LISTEN[0]}:{LISTEN[1]}  (Ollama API)")
    print("\n  Ctrl-C to stop.\n")
    try:
        Server(LISTEN, Handler).serve_forever()
    except OSError as e:
        sys.exit(f"  cannot bind {LISTEN[1]}: {e}\n"
                 "  Ollama is probably still running. Stop it — this replaces it.")


if __name__ == "__main__":
    main()
