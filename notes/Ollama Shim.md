---
tags: [architecture, backend]
cssclasses: [topic-runtime]
---

# Ollama Shim

`llamacpp/ollama_shim.py` — ~150 lines of stdlib Python that speaks Ollama's
wire protocol in front of `llama-server`, so `agents/8b` runs against
[[llama.cpp Backend|llama.cpp]] **unmodified**.

> [!note] Not linked, because it is not in the repository
> `llamacpp/` is git-excluded in full: it also holds the OpenRouter shim and
> its key. The file is on the lab machine, not in a clone, so this names the
> path rather than offering a link nobody else can follow.

It exists only because [llm.py:7](../harness/llm.py#L7) hardcodes
`OLLAMA_URL` as a module constant with no env override, and
[[Agent Loop|the loop]] reads Ollama's response shape. The shim takes port
11434 so the harness cannot tell the difference.

## Does this remove Ollama?

**Yes, completely.** Ollama is itself a wrapper around llama.cpp; running
`llama-server` directly cuts out the wrapper. The shim needs no Ollama install
— it *impersonates* the API, it does not call it. Ollama must in fact be
**stopped**, because it owns port 11434.

Inference is then a native ARM64 binary compiled `-march=armv8.7-a`, executing
on the Oryon cores with no VM, no container and no Python in the hot path. The
Python that remains — the shim, `run_agent.py`, the harness — does JSON
handling between calls that each take seconds, so it costs nothing measurable.

> Watch for x64 emulation. Windows on Arm will happily run an x64 Python or an
> x64 build under Prism, and performance collapses. `build-xelite.ps1` warns
> when `PROCESSOR_ARCHITECTURE` is not `ARM64`.

## What it translates

| Ollama (in) | OpenAI (out) |
|---|---|
| `options.temperature` | `temperature` |
| `options.seed` | `seed` |
| `options.num_predict` | `max_tokens` |
| `format: "json"` | `response_format: {"type": "json_object"}` |
| `stream: true` | SSE upstream, re-emitted as Ollama's NDJSON |
| `prompt_eval_count` / `eval_count` | ← `usage.prompt_tokens` / `completion_tokens` |

`options.num_ctx` is **not** forwarded — `llama-server` fixes context at startup
with `-c`, so set it there. `keep_alive` and `model` are accepted and ignored.

## The sharp edge: tiers collapse

One `llama-server` process serves **one** loaded model and ignores the `model`
field in the request. The shim forwards it, but nothing acts on it — so
[[Model Tiers]] does not work as documented.

The default `--tiers` lineup is unaffected — `driver`, `router` and `verifier`
already share one base tag, and `deep` is never invoked automatically. But:

```powershell
.\run.ps1 --tiers --small llama3.2:3b "..."
```

...will **use the 8B for everything** while the banner claims two resident
models and `logs/model_calls.jsonl` records `model: llama3.2:3b` against every
router and verifier call. Wrong, and silent — the accounting looks clean.

Same for `--deep`. And `keep_alive: "0"`, the mechanism behind
[[Model Tiers#One model resident|"evicted immediately after use"]], is an
Ollama concept with no llama-server equivalent, so the on-demand RAM
optimisation simply does not exist here.

To keep real tiers, run a second `llama-server` on another port and route by
model name in the shim. Otherwise avoid `--small` / `--deep` on this backend.

## Tested

The only piece of the [[llama.cpp Backend]] work that has actually been run.
Exercised against a real OpenAI-compatible endpoint with the real
`harness/llm.py` client in front:

- non-streamed `/api/chat` → correct content; `prompt_eval_count` 39 and
  `eval_count` 10 mapped from `usage`
- streamed with `STREAM_HOOK` installed → 1 `start`, 9 `token`, 1 `end`;
  content reassembled intact
- `format: "json"` → valid JSON back: `{"tool":"done","args":{}}`

That test caught a real bug, since fixed: the streamed response carried neither
`Content-Length` nor chunked framing, so on an HTTP/1.1 keep-alive socket the
client blocked forever waiting for a body end that never came. It now sends
`Connection: close`.

## Dropping the shim entirely

The shim is one option of three:

1. **Shim on 11434** — zero harness changes. What is built.
2. **Point the harness at llama-server directly** — rewrite `chat()` in
   [llm.py](../harness/llm.py) for `/v1/chat/completions`, ~30 lines
   in one file. One less process; breaks compatibility with Ollama.
3. **`llama-cpp-python` in-process** — no HTTP at all, the agent loads the model
   itself. Maximally direct; loses the server's slot management and needs the
   bindings built for ARM64 with the same flags.

## Related

- [[llama.cpp Backend]] · [[Snapdragon X Elite]] · [[Model Tiers]] · [[Determinism]]
