---
tags: [hardware, performance, plan]
cssclasses: [topic-runtime]
---

# NPU Serving

Plan for running the agent's model on the **Hexagon NPU** instead of Ollama on
the CPU. Nothing here is built yet.

## 1. What the NPU actually is

The Hexagon on X Elite is not one accelerator, it is three units behind a
scheduler, and knowing which one runs what explains every constraint below.

| unit | what it is | what it runs |
|---|---|---|
| **scalar** | 6–8 VLIW hardware threads | control flow, issue |
| **HVX** | 4–6 SIMD vector units, 1024-bit registers | elementwise, activations, norms |
| **HMX** | 1–2 systolic matrix arrays | the matmuls — this is where the TOPS live |
| **VTCM** | 8 MiB tightly-coupled scratchpad | working set staged by DMA |

45 TOPS INT8 (X Elite) / 80 TOPS (X2 Elite). Matrix FP16 throughput reaches
~12 TFLOPS.

Two properties drive the whole design:

- **VTCM is 8 MiB.** An 8B model at 4-bit is ~4.5 GB, so weights cannot live on
  the NPU. They stream from LPDDR5x through DMA, tile by tile.
- **Memory is shared with the CPU.** ~135 GB/s on X Elite, ~228 GB/s on X2.
  The NPU has no private bandwidth.

The consequence to plan around: the NPU's advantage is **compute density and
perf/watt**, which lands on prefill and on leaving the 12 Oryon cores free. See
[[#6. What to expect]] for the numbers.

## 2. The integration point

The harness talks to exactly one thing:

```
harness/llm.py  →  OLLAMA_URL = http://127.0.0.1:11434  →  /api/chat
```

Every NPU runtime below speaks **OpenAI's** `/v1/chat/completions`, not
Ollama's. So the work splits cleanly:

```
[ GenieX :18181 ]  --OpenAI-->  [ shim ]  --Ollama-->  [ harness, unchanged ]
                                  :11434
```

**The shim is the whole integration.** No agent code changes, no webui changes.
It lives at `standalone/npu/ollama_shim.py` — recovered from `b3c948f`, where it
had been deleted in `0af900a`, then repointed at GenieX. It handles the
translation the harness needs: `options.num_predict` → `max_tokens`,
`format: "json"` → `response_format`, SSE → Ollama's NDJSON,
`prompt_eval_count`/`eval_count` from `usage`.

The one thing that is not zero-change is the model tag: GenieX serves
`ai-hub-models/...` ids, so `agents/8b/config.json` and
[[Harness Profiles|profiles.py]] name that id, and the shim substitutes it on
every call.

## 3. Three routes

### Route A — GenieX (chosen)

Qualcomm's own runtime, and the route this repo now implements. GenieX is the
open build of Genie: it reaches the Hexagon NPU through AI Engine Direct (QNN),
and it ships **both** an installer and an OpenAI-compatible server, so neither
the export step nor the HTTP wrapper this note used to budget for exists any
more.

```powershell
# installer from github.com/qualcomm/GenieX (Windows ARM64), then:
geniex pull ai-hub-models/Llama-v3.1-8B-Instruct
geniex serve --compute npu --nctx 8192      # http://127.0.0.1:18181/v1
```

Models published to AI Hub are **pre-compiled per chipset**, so `geniex pull`
fetches a binary already built for X Elite. That removes the three costs this
note previously attributed to the Genie route — no AI Hub account, no
compilation on Qualcomm's cloud, no `qai_hub_models.export` — for any model in
the bundle catalogue.

What survives: **Llama weights are still licence-gated.** If the pull is
refused, either clear the grant or fall back to
`ai-hub-models/Qwen2.5-7B-Instruct`, which has a profile registered for exactly
this case. Prefer Llama where possible — it is the model the balanced profile
was tuned on, so the NPU run stays a backend comparison rather than a model
change.

`--compute` also takes `hybrid` (per-tensor HTP+CPU scheduler) against `npu`
(pinned to one HTP session). Measure both in Phase 2; on a 7–8B the scheduler
sometimes wins.

### Route B — Foundry Local (fallback)

Microsoft's on-device runtime. GA since April 2026, detects the NPU, picks the
QNN execution provider itself, also OpenAI-compatible.

```powershell
winget install Microsoft.FoundryLocal
foundry model run phi-4-mini
foundry server status -o json     # ephemeral port, so always ask
```

Comparable effort to Route A now, but a worse fit here: you run whatever models
Microsoft ships QNN variants of, which does not include `llama3.1:8b`, so every
run becomes a model change *and* a backend change at once. Keep it as the
fallback if GenieX will not serve on this machine.

### Route C — ONNX Runtime GenAI + QNN EP (most work)

Build the model assets yourself and run through ORT's QNN execution provider.
Most control over quantisation, most moving parts: nightly `onnxruntime` builds
are currently required for LLM QNN support, plus cmake and VS 2022.

Take this only if A and B both fail to produce a usable model.

## 4. Phased plan

**Phase 0 — restore the adapter.** Recover `ollama_shim.py` into
`standalone/npu/`. Verify against Ollama itself first: point the shim at a
dummy OpenAI endpoint and confirm the harness still completes a run. *This
phase is testable with no NPU involved.*

**Phase 1 — GenieX.** Install, `geniex pull` the Llama 3.1 8B bundle, `geniex
serve --compute npu --nctx 8192`, start the shim, run `run_agent.py` with no
flags changed. Success = a run finishes cleanly.

**Phase 2 — measure.** Same task, same model, three backends: Ollama/CPU,
GenieX `--compute npu`, GenieX `--compute hybrid`. Record prefill and decode
separately — they behave very differently here — plus wall time, and CPU
utilisation during the run. Because the model is identical across all three,
any difference is the backend.

**Phase 3 — re-tune.** AI Hub quantisation is not Q4_0. Re-check JSON validity and
tool-call reliability before trusting the profile; `parse_failures` and
`invalid_calls` in the run log are the signal.

## 5. Known constraints

- **Context is fixed at load, and the default is wrong for us.** `geniex serve`
  defaults to `--nctx 4096`; every profile in `profiles.py` asks for 8192 or
  more. The shim cannot fix this — it deliberately does not forward `num_ctx`,
  because the runtime decides it. Pass `--nctx` to match the profile or long
  runs truncate silently. On a pre-compiled QNN bundle the ceiling is baked into
  the binary, so this is a hard limit, not a flag.
- **One model in memory at a time.** GenieX evicts on load, and after
  `--keepalive` seconds idle (default 300). Fine within a run; it means the
  `--tiers` router cannot hold several models resident the way Ollama does.
- **Quantisation tooling is x86_64-only.** ONNX quantisation utilities do not
  install cleanly on ARM64, so Route C needs a separate x64 Python or a
  different machine to prepare assets.
- **Llama weights are licence-gated.** Pre-compiled bundles remove the export
  step but not the grant. See Route A for the fallback.
- **Model choice narrows.** Only models in the AI Hub bundle catalogue (or GGUF
  at Q4_0, which has the best Hexagon support on the llama.cpp runtime) reach
  the NPU. The agent's `--tiers` router assumes several interchangeable Ollama
  tags and will not have them.
- **Which chip.** The tuning assumed X1E (12 cores, ~135 GB/s). If the Yoga is
  actually X2 Elite (18 cores, ~228 GB/s, 80 TOPS), every roofline figure and
  thread count changes. Confirm before measuring — see [[Open Questions]].

## 6. What to expect

Qualcomm's published figure for **Llama 3.1 8B on X Elite via Genie is ~9.4
tok/s** decode. For reference, llama.cpp on the Oryon CPU measured ~20 tok/s
realistic for the same model class.

So plan for decode being **comparable at best, likely slower**, and target the
NPU for what it does win:

- **prefill**, which is compute-bound and where the HMX applies — this matters
  because the harness re-sends a growing transcript on every one of 14–40 calls
- **perf/watt**, i.e. battery and thermals
- **12 CPU cores freed** — increasingly relevant now the agent also runs Node
  MCP servers and writes .pptx/.xlsx mid-run

Decode is bandwidth-bound and the NPU shares the same LPDDR5x, so no runtime
choice moves that ceiling. Measure prefill and decode separately in Phase 2 or
the result will look like a regression when it is a trade.

## 7. Success criteria

1. `run_agent.py` completes a run with **zero agent-code changes**
2. Prefill tok/s beats the CPU baseline
3. CPU utilisation during a run drops materially
4. `parse_failures` / `invalid_calls` no worse than the Ollama baseline

## Related

- [[Harness Profiles]] — what needs re-tuning if quantisation changes
- [[Model Tiers]] — the router assumes interchangeable tags; the NPU will not have them
- [[Open Questions]] · [[Determinism]]

## Sources

- [qualcomm/GenieX](https://github.com/qualcomm/GenieX) — install, `pull`, `serve`
- [GenieX — local OpenAI-compatible server](https://deepwiki.com/qualcomm/GenieX/3.3-local-openai-compatible-server) — `serve` flags, endpoints, single-model constraint
- [GenieX — what it is](https://geniex.aihub.qualcomm.com/en/get-started/what-is-geniex)
- [Qualcomm AI Hub — Llama-v3.1-8B-Instruct](https://aihub.qualcomm.com/models/llama_v3_1_8b_instruct)
- [ai-hub-apps — llm_on_genie tutorial](https://github.com/quic/ai-hub-apps/tree/main/tutorials/llm_on_genie) — the manual export route, if a bundle is unavailable
- [Foundry Local — get started](https://learn.microsoft.com/en-us/windows/ai/foundry-local/get-started)
- [ONNX Runtime — run on Snapdragon](https://onnxruntime.ai/docs/genai/tutorials/snapdragon.html)
- [ONNX Runtime — build model assets for Snapdragon NPU](https://onnxruntime.ai/docs/genai/howto/build-models-for-snapdragon.html)
- [QNN Execution Provider](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html)
- [Chips and Cheese — Qualcomm's Hexagon DSP, and now, NPU](https://chipsandcheese.com/p/qualcomms-hexagon-dsp-and-now-npu)
- [quic/ai-engine-direct-helper](https://github.com/quic/ai-engine-direct-helper)
