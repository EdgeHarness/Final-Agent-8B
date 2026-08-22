---
tags: [hardware, performance, backend]
cssclasses: [topic-runtime]
---

# llama.cpp Backend

Running the agent on [[Snapdragon X Elite|the Yoga]] without Ollama.

> [!warning] Not in the repository
> This note used to link to `standalone/llamacpp/` and a README inside it.
> Neither is reachable: the flatten removed the `standalone/` prefix, and
> `llamacpp/` is git-excluded in full, so nothing there is tracked and the
> README does not exist anywhere. The config is local to the lab machine, by
> design, because that directory also holds the OpenRouter shim and its key.
> Read the shim sources on the machine itself.

Nothing here forks llama.cpp. Everything that makes a Snapdragon fast is
already upstream — it is reached through the toolchain, the build flags, the
quantization format and the runtime flags.

## The CPU beats both accelerators

The counterintuitive result, and the reason this setup ignores the 45-TOPS NPU.

Snapdragon X Elite, Llama-7B Q4_0:

| backend | prefill (pp512) | decode (tg128) |
|---|---|---|
| **CPU, 12 threads** | **177.7 tok/s** | **24.8 tok/s** |
| Adreno via OpenCL | 100.7 tok/s | 18.0 tok/s |

Hexagon NPU, Qwen3.5 0.8B, from the one project with it working on Windows
ARM64:

| backend | prefill | decode |
|---|---|---|
| **CPU** | **795 tok/s** | **64.4 tok/s** |
| NPU forced | 31.6 tok/s | 2.0 tok/s |

The NPU loses by ~30× at decode for a structural reason, not a tuning miss:
llama.cpp dispatches each op individually to the DSP over FastRPC — ~230 calls
at ~75 µs each, so ~17 ms of dispatch overhead per token against ~55 ms of real
compute. Reaching it also costs a Hexagon SDK install, a self-signed HTP
driver, **test-signing mode**, and **Secure Boot disabled**.

The NPU's advantage is power draw, not speed. For an agent that runs for
minutes on a plugged-in laptop, that is the wrong thing to optimise.
**Build for the CPU.**

## Build flags, and why each

**The toolchain is already right.** llama.cpp's stock
`cmake/arm64-windows-llvm.cmake` compiles with
`-march=armv8.7-a -fvectorize -ffp-model=fast` — precisely the Oryon ISA level,
so `arm64-windows-llvm-release` needs no `-march` override. Verified by reading
the file. Use **clang, not MSVC**.

| flag | why |
|---|---|
| `GGML_CPU_KLEIDIAI=ON` | Arm's matmul microkernels; resolves at runtime to the **i8mm + dotprod** paths on Oryon |
| `GGML_OPENMP=OFF` | the documented Windows-on-Arm recommendation; llama.cpp's own threadpool does better |
| `GGML_LTO=ON` | cheap, and these are small hot kernels |
| `GGML_OPENCL=ON` | second preset only — benchmark it, do not assume it wins |

Leave `GGML_KLEIDIAI_SME` unset: there is no SME here, and the runtime check
will correctly skip those kernels.

## Q4_0, not Q4_K_M

The X Elite-specific call, and the easiest thing to get wrong. **Q4_0** and
**IQ4_NL** get *runtime repacking* — on load, weights are rewritten into the
interleaved layout the i8mm kernels want. Q4_K_M is the better
quality-per-byte format on most hardware and does **not** get that treatment.

The old pre-repacked `Q4_0_4_4` / `Q4_0_4_8` files are deprecated; plain Q4_0
repacks itself now, so do not go hunting for them.

## Runtime flags

| flag | why |
|---|---|
| `-t 8` / `-tb 12` | prefill is compute-bound and wants all 12 cores; decode is bandwidth-bound and often peaks *below* 12, where extra threads add contention but no bandwidth |
| `--no-mmap` | with repacking on load, mmap can leave you paying for the mapped file *and* the repacked copy |
| `--mlock` | 32 GB against a 4.7 GB model — pin it, never page |
| `-ctk q8_0 -ctv q8_0` | halves KV traffic on a bandwidth-bound decode; needs `-fa on` |
| `-c 8192` | matches the balanced [[Harness Profiles|profile]]'s `num_ctx` |

**Plug the laptop in and set Windows power mode to Best Performance.** Oryon
clocks down hard on battery — this moves the numbers more than any flag above.

## Status

`-t 8 -tb 12`, the batch sizes and the q8_0 KV win are **reasoned, not
measured** — a hypothesis from "decode is bandwidth-bound". Run
`bench-xelite.ps1` before trusting them.

The PowerShell scripts and both CMake presets have **never been executed** —
written on macOS/arm64 with no Snapdragon and no Windows on Arm available. Flag
and preset names are verified against llama.cpp source; expect to fix a path on
first run.

## Related

- [[Snapdragon X Elite]] · [[Ollama Shim]] · [[Model Tiers]] · [[Running the Agent]]
