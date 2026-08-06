---
tags: [hardware, performance]
---

# Snapdragon X Elite

The target laptop: Lenovo Yoga, 32 GB, Snapdragon X Elite (X1E-78-100 /
X1E-80-100). Everything in [[llama.cpp Backend]] follows from the two numbers
in bold below.

| | |
|---|---|
| CPU | 12× Qualcomm Oryon, 3 clusters of 4, up to 3.4 GHz |
| ISA | **ARMv8.7-A** |
| Cache | 2.3 MB L1 · 12 MB L2 · 6 MB L3 |
| Memory | LPDDR5x-8448, 8 × 16-bit channels — **135 GB/s** |
| GPU | Adreno X1-85, 3.8 TFLOPS |
| NPU | Hexagon, 45 TOPS INT8 |
| TDP | 35 W (45 W PL2) |

## What ARMv8.7-A settles

Two consequences decide the whole build, and neither needs measuring — they
follow from the architecture level:

- **`dotprod`, `i8mm` and `bf16` are present.** `dotprod` is mandatory from
  ARMv8.4-A, `i8mm` and `bf16` from ARMv8.6-A. These are exactly the features
  the fast integer-matmul kernels want.
- **`SVE`, `SVE2`, `SME`, `SME2` are absent.** Oryon v1 vectorises on NEON only.
  Any guide that says to build with `+sve`, or to chase SME microkernels, is
  describing a different chip.

There are also **no efficiency cores** — all 12 Oryon cores are identical, so
the usual "pin the hot threads to the P-cores" tuning has nothing to bite on.

## The roofline

Decode reads the entire weight set once per generated token, so it is
bandwidth-bound, not compute-bound:

```
decode ceiling (tok/s)  ≈  135 GB/s  ÷  model file size (GB)
```

A measured reference point — Llama-7B Q4_0, 3.82 GB, 24.8 tok/s against a 35.3
tok/s ceiling — puts real-world efficiency at **~70% of roofline**. Applying
that:

| model (Q4_0) | size | ceiling | realistic |
|---|---|---|---|
| Llama 3.2 3B | ~1.9 GB | 71 tok/s | ~50 tok/s |
| **Llama 3.1 8B** | ~4.7 GB | 29 tok/s | **~20 tok/s** |
| Qwen 2.5 14B | ~8.2 GB | 16 tok/s | ~11 tok/s |
| Qwen 2.5 32B | ~18.5 GB | 7 tok/s | ~5 tok/s |

**32 GB buys context and headroom, not speed.** A 32B model fits in RAM
comfortably and still decodes at ~5 tok/s, because the wall is bandwidth, not
capacity. 8B is the right size for this chip — which is also the size
[[Harness Profiles|the balanced profile]] was written for.

This is consistent with what the agent already predicts for itself: 700 output
tokens at ~20 tok/s is ~35 s per step, and
[[Running the Agent#What to expect at 8B|"tens of seconds per step"]] is exactly
what the 8B README claims.

## Which chip, though

The **current** Yoga Slim 7x (Gen 11) ships the **Snapdragon X2 Elite** — Oryon
v3, 18 cores, ~228 GB/s, 80 TOPS NPU. All of the above targets X1E. If the
machine turns out to be X2, the build flags stay valid (still ARM64, still
NEON) but every thread count and every number in the roofline table needs
redoing. **Unconfirmed — worth checking before spending time on tuning.**

## Related

- [[llama.cpp Backend]] · [[Ollama Shim]] · [[Determinism]]
