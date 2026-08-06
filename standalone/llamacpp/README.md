# llama.cpp on Snapdragon X Elite — Lenovo Yoga, 32 GB

A build and runtime configuration for llama.cpp tuned to this laptop, plus a
shim that lets the existing 8B agent use it without touching `harness/`.

To be explicit about what this is: llama.cpp is a ~250k-line project and nobody
should rewrite it per chip. Everything that makes a Snapdragon fast is already
upstream — it is reached through the toolchain, the build flags, the
quantization format and the runtime flags. That is what is configured here, and
every choice below traces to a source in §7.

---

## 1. The chip

Snapdragon X Elite (X1E-78-100 / X1E-80-100), the part in the Yoga Slim 7x
Gen 9:

| | |
|---|---|
| CPU | 12× Qualcomm Oryon, 3 clusters of 4, up to 3.4 GHz |
| ISA | **ARMv8.7-A** |
| Cache | 2.3 MB L1 · 12 MB L2 · 6 MB L3 |
| Memory | LPDDR5x-8448, 8 × 16-bit channels — **135 GB/s** |
| GPU | Adreno X1-85, 3.8 TFLOPS |
| NPU | Hexagon, 45 TOPS INT8 |
| TDP | 35 W (45 W PL2) |

Two consequences fall straight out of "ARMv8.7-A", and they decide the whole
build:

- **`i8mm` and `bf16` are present.** Both are mandatory from ARMv8.6-A, and
  `dotprod` from ARMv8.4-A. These are exactly the features the fast integer
  matmul kernels need.
- **`SVE`, `SVE2`, `SME` and `SME2` are absent.** Oryon v1 does vector work on
  NEON only. Any guide telling you to build with `+sve` or to chase SME
  microkernels is describing a different chip — those flags will at best do
  nothing and at worst fail to build.

There are **no efficiency cores**. All 12 Oryon cores are the same, so the
usual "pin to the P-cores" tuning does not apply here.

> One note on the hardware: the current Yoga Slim 7x (Gen 11) ships the
> **Snapdragon X2 Elite** — Oryon v3, 18 cores, ~228 GB/s, 80 TOPS NPU. You said
> X Elite, so everything here targets X1E. If your machine turns out to be X2,
> the build flags stay valid (still ARM64 + NEON) but the thread counts and the
> bandwidth arithmetic in §3 need redoing.

---

## 2. Backend choice: the CPU wins

This is the counterintuitive part, and it is why this directory does not chase
the NPU.

Measured on Snapdragon X Elite, Llama-7B Q4_0 ([llama.cpp discussion #8336](https://github.com/ggml-org/llama.cpp/discussions/8336)):

| backend | prefill (pp512) | decode (tg128) |
|---|---|---|
| **CPU, 12 threads** | **177.7 tok/s** | **24.8 tok/s** |
| Adreno via OpenCL | 100.7 tok/s | 18.0 tok/s |

And on the Hexagon NPU, from the one project that has it working on Windows
ARM64 ([ara142/llama-cpp-hexagon-npu](https://github.com/ara142/llama-cpp-hexagon-npu)), Qwen3.5 0.8B:

| backend | prefill | decode |
|---|---|---|
| **CPU** | **795 tok/s** | **64.4 tok/s** |
| NPU forced | 31.6 tok/s | 2.0 tok/s |

The NPU is ~30× slower at decode, and the reason is structural rather than a
tuning miss: llama.cpp dispatches each op individually to the DSP over FastRPC,
around 230 calls at ~75 µs each — ~17 ms of dispatch overhead per token against
~55 ms of actual compute. Getting there also costs you a Hexagon SDK install,
a self-signed HTP driver, **test-signing mode**, and **Secure Boot disabled**.

The NPU's real advantage is power draw, not speed. For an agent that runs for
minutes at a time on a plugged-in laptop, that is the wrong thing to optimize.

**Decision: build for the CPU.** OpenCL is included as a second preset so you
can verify the gap yourself; the Hexagon path is deliberately not scripted.

---

## 3. What sets the ceiling

Decode is memory-bandwidth-bound. Every generated token reads the entire weight
set once, so:

```
decode ceiling (tok/s)  ≈  135 GB/s  ÷  model file size (GB)
```

The 7B Q4_0 measurement above (3.82 GB → 35.3 tok/s ceiling, 24.8 achieved)
puts real efficiency at ~70%. Applying that:

| model (Q4_0) | size | ceiling | realistic |
|---|---|---|---|
| Llama 3.2 3B | ~1.9 GB | 71 tok/s | ~50 tok/s |
| **Llama 3.1 8B** | ~4.7 GB | 29 tok/s | **~20 tok/s** |
| Qwen 2.5 14B | ~8.2 GB | 16 tok/s | ~11 tok/s |
| Qwen 2.5 32B | ~18.5 GB | 7 tok/s | ~5 tok/s |

Two things follow.

**32 GB buys context and headroom, not speed.** A 32B model fits comfortably in
RAM and still decodes at ~5 tok/s, because bandwidth — not capacity — is the
wall. The 8B is the right size for this chip.

**This matches what the agent already expects.** The 8B profile budgets 14 LLM
calls at ≤700 output tokens; 700 tokens at 20 tok/s is ~35 s per step, which is
the "tens of seconds per step on CPU" the agent's own README predicts.

---

## 4. The optimizations, and why each one

**Toolchain — already correct.** llama.cpp's stock
[`cmake/arm64-windows-llvm.cmake`](https://github.com/ggml-org/llama.cpp/blob/master/cmake/arm64-windows-llvm.cmake)
compiles with `-march=armv8.7-a -fvectorize -ffp-model=fast`. That is precisely
the Oryon ISA level, so the `arm64-windows-llvm-release` preset needs no `-march`
override. Verified against the file, not assumed. Use **clang, not MSVC**.

**`GGML_CPU_KLEIDIAI=ON`** — Arm's KleidiAI matmul microkernels, selected at
runtime from detected CPU features. On Oryon that resolves to the **i8mm and
dotprod** paths. Leave `GGML_KLEIDIAI_SME` unset; there is no SME here and the
runtime check will correctly skip those kernels.

**`GGML_OPENMP=OFF`** — the explicit upstream recommendation for Windows on Arm;
llama.cpp's own threadpool behaves better than OMP here.

**`GGML_LTO=ON`** — cheap, and these are small hot kernels.

**Q4_0, not Q4_K_M.** The X Elite-specific call. Q4_0 (and IQ4_NL) get
**runtime repacking**: on load, weights are rewritten into the interleaved
layout the i8mm kernels want. Q4_K_M is the better format on most hardware for
quality-per-byte, but it does not get that treatment. Take the Q4_0 build of
whatever you run. The old `Q4_0_4_4` / `Q4_0_4_8` pre-repacked files are
deprecated — plain Q4_0 now repacks itself, so do not go hunting for them.

**`--no-mmap`** — with repacking on load, mmap can leave you paying for both the
mapped file and the repacked copy. Turning it off reduces resident memory.

**Split thread counts, `-t 8 -tb 12`** — prefill is compute-bound and wants all
12 cores; decode is bandwidth-bound and frequently peaks *below* 12, where extra
threads add contention but no bandwidth. This is the single most machine-specific
number here, which is why `bench-xelite.ps1` sweeps it. Treat 8 as a hypothesis.

**`--mlock`** — 32 GB against a 4.7 GB model. Pin it; never let it page.

**`-ctk q8_0 -ctv q8_0`** — halves KV-cache traffic on a bandwidth-bound decode,
at close to no quality cost. Requires flash attention (`-fa on`), which is on.

**Plug the laptop in, set Windows power mode to Best Performance.** Oryon clocks
down hard on battery. This will move your numbers more than any flag above.

---

## 5. Files

| file | what it does |
|---|---|
| `CMakeUserPresets.json` | `xelite-cpu` and `xelite-opencl` presets, inheriting llama.cpp's `arm64-windows-llvm-release` |
| `build-xelite.ps1` | clones llama.cpp, drops the presets in, configures and builds |
| `bench-xelite.ps1` | sweeps threads / KV type / mmap and writes `bench-results.md` |
| `serve-xelite.ps1` | starts `llama-server` with the §4 flags |
| `ollama_shim.py` | *optional* — Ollama `/api/chat` on :11434 → llama-server `/v1` on :8080, so `agents/8b` runs unmodified |

---

## 6. End to end

```powershell
# build (on the Yoga, ARM64 native shell)
.\build-xelite.ps1

# confirm the features — expect DOTPROD 1, MATMUL_INT8 1, SVE 0, SME 0
& ..\llama.cpp\build-xelite-cpu\bin\Release\llama-cli.exe --version

# get the Q4_0 weights the 8B agent's config.json asks for
huggingface-cli download bartowski/Meta-Llama-3.1-8B-Instruct-GGUF `
    Meta-Llama-3.1-8B-Instruct-Q4_0.gguf --local-dir C:\models

# measure, then edit the defaults in serve-xelite.ps1 to match
.\bench-xelite.ps1 -Bin ..\llama.cpp\build-xelite-cpu\bin\Release `
                   -Model C:\models\Meta-Llama-3.1-8B-Instruct-Q4_0.gguf

# serve
.\serve-xelite.ps1 -Bin ..\llama.cpp\build-xelite-cpu\bin\Release `
                   -Model C:\models\Meta-Llama-3.1-8B-Instruct-Q4_0.gguf
```

To drive the existing agent with it — stop Ollama first, it owns port 11434:

```powershell
python ollama_shim.py                       # :11434 -> :8080
cd ..\agents\8b ; python run_agent.py "Find a free hour Thursday and book it"
```

`harness/llm.py` hardcodes `OLLAMA_URL`, which is why the shim takes that port
rather than the harness taking a flag.

---

## 7. Verification status

Verified by reading the source or a primary doc:

- `arm64-windows-llvm-release` preset exists; its toolchain sets `-march=armv8.7-a`
- `GGML_CPU_KLEIDIAI`, `GGML_OPENMP`, `GGML_OPENCL` are real CMake options
- `GGML_OPENMP=OFF` is the documented Windows-on-Arm recommendation
- X Elite is ARMv8.7-A, NEON-only, no SVE/SVE2; 135 GB/s over 8 LPDDR5x-8448 channels
- Q4_0 and IQ4_NL are the runtime-repacking formats

Reasoned, not measured — **check these against `bench-xelite.ps1` before
trusting them**:

- `-t 8 -tb 12`. A starting hypothesis from "decode is bandwidth-bound", nothing more.
- `-b 2048 -ub 512`, and q8_0 KV being a net win at this size.
- The ~20 tok/s figure for 8B Q4_0, extrapolated from a 7B measurement at 70% of roofline.

Tested locally — `ollama_shim.py` only. It was run against a real
OpenAI-compatible endpoint (Ollama's own `/v1`) with the actual
`harness/llm.py` client in front of it, covering both paths the agent uses:

- non-streamed `/api/chat` → correct content, `prompt_eval_count` 39 and
  `eval_count` 10 mapped from `usage`
- streamed with `STREAM_HOOK` installed → 1 `start`, 9 `token`, 1 `end` event,
  content reassembled intact
- `format: "json"` → `response_format` produced valid JSON: `{"tool":"done","args":{}}`

That test caught one real bug, now fixed: the streamed response carried neither
`Content-Length` nor chunked framing, so on an HTTP/1.1 keep-alive socket the
client blocked forever. It now sends `Connection: close`.

**Untested: everything Windows.** The three PowerShell scripts and both CMake
presets have never been executed — this was written on macOS/arm64, with no
Snapdragon and no Windows on Arm available. The flags and preset names are
verified against llama.cpp's own source (above), but expect to fix a path or a
flag spelling on first run.

## Sources

- [llama.cpp discussion #8336 — Accelerating llama.cpp for Copilot+ PCs / Snapdragon X](https://github.com/ggml-org/llama.cpp/discussions/8336)
- [llama.cpp discussion #8273 — Performance on Snapdragon X Elite/Plus](https://github.com/ggml-org/llama.cpp/discussions/8273)
- [llama.cpp — Snapdragon backend docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/README.md)
- [llama.cpp — build.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
- [Qualcomm — Big Performance Boost for llama.cpp with Windows on Snapdragon](https://www.qualcomm.com/developer/blog/2024/04/big-performance-boost-llama-cpp-chatglm-cpp-with-windows-on-snapdragon)
- [Qualcomm — OpenCL GPU backend in llama.cpp for Adreno](https://proandroiddev.com/introducing-the-new-opencl-gpu-backend-in-llama-cpp-for-qualcomm-adreno-gpus-4093655d334c)
- [Qualcomm — Snapdragon X Elite product brief](https://docs.qualcomm.com/bundle/publicresource/87-71417-1_REV_F_Snapdragon_X_Elite_Product_Brief.pdf)
- [Arm — KleidiAI + llama.cpp learning path](https://learn.arm.com/learning-paths/mobile-graphics-and-gaming/performance_llama_cpp_sme2/build_llama_cpp/)
- [ara142/llama-cpp-hexagon-npu — Hexagon NPU on Windows ARM64](https://github.com/ara142/llama-cpp-hexagon-npu)
- [HWCooling — Oryon architecture analysis (SVE absence)](https://www.hwcooling.net/en/oryon-arm-core-in-snapdragon-x-cpus-architecture-analysis/)
- [Notebookcheck — X1E-78-100 specifications](https://www.notebookcheck.net/Qualcomm-Snapdragon-X-Elite-X1E-78-100-Processor-Benchmarks-and-Specs.838568.0.html)
