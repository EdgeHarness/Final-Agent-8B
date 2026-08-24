# This repository is now a shipping instance

As of 2026-08-23, engine development happens in
[Brick-Agent-Harness](https://github.com/EdgeHarness/Brick-Agent-Harness).
This repository is the Snapdragon deployment of that engine: device serving,
backend operation, packaging, and lab configuration. Nothing here was
deleted, because the lab machine runs from this tree; but the generic code in
`harness/` and `webui/` is frozen and superseded.

## What moved to Brick, and where

| from here | in Brick as of | notes |
|---|---|---|
| Agent Lab console (`webui/`) | `4cc0845`..`d70a941` | rebuilt on Brick's capability auth and domain packs |
| MCP connector layer (`harness/mcp_bridge.py`) | `b0062fc`, `dd8a124` | plus multi-account broker and env scrubbing (`a3ea192`) |
| conversation threads (`harness/chat.py`) | `f8b052a` | |
| the five guards (`harness/agent.py`) | `b625087` | `harness/guards.py`, domain-free, behind `RunConfig.guards` |
| per-model profiles (`harness/profiles.py`) | `11f4e18` | resolution and knobs preserved; loop reads them from `RunConfig.profile` |
| memory retrieval improvements (`harness/memory.py`) | `a5d02d7` | prefix overlap, dedupe, torn-line tolerance |
| backend shims (`npu/`, `llamacpp/`) | `7196640` | with `docs/NPU_SERVING.md`, `docs/LLAMACPP_BACKEND.md`, `docs/OLLAMA_SHIM.md` |

Deliberately NOT moved:

- `llamacpp/openrouter_shim.py` - carries a provider key; Brick's hard rule 9
  forbids it there. It stays local-only here as before.
- `harness/fs_tools.py` - general filesystem capability is not offered on a
  supported Brick surface (same rule). Real file access is MCP-mediated.
- The office world merged into `harness/world.py` here - Brick's
  `domains/office_demo/world.py` is digest-bound to its frozen study and
  stays as it is.

## What this repository remains for

- Running the agent on this Snapdragon X Elite machine: llama.cpp builds and
  flags, GenieX serving, the `serve-xelite` scripts, `Agent Lab.command` /
  `Agent Lab.ps1` launchers.
- Device-specific notes under `notes/`.
- Packaging work toward a customer-shippable install.

New engine features (guards, profiles, MCP, domains) land in Brick first and
flow here through deployment, not through parallel development. If you are
about to edit `harness/` or `webui/` here, stop and check whether the change
belongs upstream.
