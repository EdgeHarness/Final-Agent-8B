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
[ NPU runtime ]  --OpenAI-->  [ shim ]  --Ollama-->  [ harness, unchanged ]
                                :11434
```

**The shim is the whole integration.** No agent code changes, no profile
changes, no webui changes. That adapter used to exist as `ollama_shim.py` and
was deleted in `0af900a`; restore it as the first step rather than writing it
again:

```bash
git checkout b3c948f -- standalone/llamacpp/ollama_shim.py
git mv standalone/llamacpp/ollama_shim.py standalone/npu/ollama_shim.py
```

It already handles the translation the harness needs: `options.num_predict` →
`max_tokens`, `format: "json"` → `response_format`, SSE → Ollama's NDJSON,
`prompt_eval_count`/`eval_count` from `usage`.

## 3. Three routes

### Route A — Foundry Local (recommended first)

Microsoft's on-device runtime. GA since April 2026. It detects the Snapdragon
NPU, picks the QNN execution provider automatically, and **already exposes an
OpenAI-compatible REST API** — so there is no model export step and no SDK
install.

```powershell
winget install Microsoft.FoundryLocal
foundry model run phi-4-mini      # or another QNN-optimised model
foundry service status            # prints the local OpenAI endpoint
```

Then point the shim at that endpoint. **This is the shortest path to a working
NPU-served agent** — plausibly a single afternoon.

Cost: you run whatever models Foundry ships QNN variants of, not necessarily
`llama3.1:8b`. That changes which [[Harness Profiles|profile]] applies.

### Route B — Qualcomm AI Hub → Genie (most control)

Qualcomm's own stack. Compile the model to QNN context binaries ahead of time,
then serve with Genie from the QAIRT SDK. This is what Qualcomm's published
numbers use.

```powershell
pip install qai-hub-models
qai-hub configure --api_token <token>

python -m qai_hub_models.models.llama_v3_1_8b_instruct.export `
  --device "Snapdragon X Elite CRD" `
  --skip-inferencing --skip-profiling `
  --output-dir genie_bundle
```

Produces context binaries split across five parts. Serve with `genie-t2t-run`
from QAIRT, or use **GenieX**, the community build that adds an
OpenAI-compatible server — which removes the need to write a Genie HTTP wrapper
by hand.

Cost: an AI Hub account, a Hugging Face licence grant for Llama weights,
compilation on Qualcomm's cloud (not local), and a large download.

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

**Phase 1 — Foundry Local.** Install, serve a QNN model, point the shim at it,
run `run_agent.py` with no flags changed. Success = a run finishes cleanly.

**Phase 2 — measure.** Same task, three backends: Ollama/CPU, Foundry/NPU, and
(if built) Genie/NPU. Record prefill and decode separately — they behave very
differently here — plus wall time, and CPU utilisation during the run.

**Phase 3 — Genie, only if Phase 2 justifies it.** Export Llama 3.1 8B, serve
via GenieX, re-measure. This is the route that gets the exact model the
[[Harness Profiles|balanced profile]] was tuned for.

**Phase 4 — re-tune.** NPU quantisation is not Q4_0. Re-check JSON validity and
tool-call reliability before trusting the profile; `parse_failures` and
`invalid_calls` in the run log are the signal.

## 5. Known constraints

- **Context length is baked into the context binary** on the Genie route. The
  harness's `num_ctx 8192` becomes a compile-time decision, not a flag — a
  harder version of the constraint `ollama_shim.py` already documents for
  `llama-server`.
- **Quantisation tooling is x86_64-only.** ONNX quantisation utilities do not
  install cleanly on ARM64, so Route C needs a separate x64 Python or a
  different machine to prepare assets.
- **Llama weights are restricted** — no direct download, you export them
  yourself through AI Hub with a Hugging Face grant.
- **Model choice narrows.** Only models with QNN variants run on the NPU. The
  agent's `--tiers` router, which assumes several interchangeable Ollama tags,
  will not have them.
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

- [Qualcomm AI Hub — Llama-v3.1-8B-Instruct](https://aihub.qualcomm.com/models/llama_v3_1_8b_instruct)
- [ai-hub-apps — llm_on_genie tutorial](https://github.com/qualcomm/ai-hub-apps/tree/main/tutorials/llm_on_genie)
- [Foundry Local — get started](https://learn.microsoft.com/en-us/windows/ai/foundry-local/get-started)
- [ONNX Runtime — run on Snapdragon](https://onnxruntime.ai/docs/genai/tutorials/snapdragon.html)
- [ONNX Runtime — build model assets for Snapdragon NPU](https://onnxruntime.ai/docs/genai/howto/build-models-for-snapdragon.html)
- [QNN Execution Provider](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html)
- [Chips and Cheese — Qualcomm's Hexagon DSP, and now, NPU](https://chipsandcheese.com/p/qualcomms-hexagon-dsp-and-now-npu)
- [quic/ai-engine-direct-helper](https://github.com/quic/ai-engine-direct-helper)
