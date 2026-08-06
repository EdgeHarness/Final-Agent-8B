---
tags: [howto, architecture]
cssclasses: [topic-core]
---

# Agent Lab

The demo frontend: [standalone/webui/](../standalone/webui/), launched by
[Agent Lab.command](../Agent%20Lab.command). A local web console where you type
a task and watch the [[Agent Loop|loop]] run — plan, every token as it is
written, each tool call, the harness's repairs and the verifier, and the agent's
folder updating as it changes.

It binds loopback only and runs one agent at a time in a subprocess
(`webui/runner.py`), which installs the harness's `STREAM_HOOK` / `EVENT_HOOK` /
`TOOL_HOOK` seams and narrates the run as JSONL. The benchmark path imports none
of it — see [[Architecture#Design rule visible throughout]].

```bash
./"Agent Lab.command"          # or: cd standalone && python3 -m webui.server
```

## Which model actually drives it

The left rail picks an **agent folder** (here only `8b`), which fixes the
[[Harness Profiles|profile]] and owns the state. The dropdown next to **Run**
picks which *installed* Ollama tag does the talking.

That split exists because `agents/8b/config.json` names `llama3.1:8b`, and a
machine that has `llama3.1:latest` or `llama3.2:3b` pulled would otherwise have
to download 4.7 GB before it could demo anything. The dropdown turns **amber**
when the tag is not the one the folder asks for, so a substitution is never
silent.

The override is applied *before* the profile lookup in `runner.py`, so the
harness tuning follows the model doing the work rather than the one in the
config.

## The office viewers

`/api/preview` returns geometry, not a text summary, and the browser draws it.

**PowerPoint** — every shape's real position, size, font size, weight and colour,
expressed as fractions of the slide. The frame is a CSS container, so `1cqw` is
1% of the slide width and text scales with the panel at any size. Tables render
as tables, pictures as embedded data URIs, and solid autoshapes keep their fill
so the accent bar and rules survive.

**Excel** — a real grid: column letters, row numbers, sticky headers, column
widths, merged cells, bold, alignment. Formula cells show a `ƒ` marker with the
formula on hover. openpyxl does not evaluate formulas and a file Excel has never
opened carries no cached result, so those cells display the formula text itself
rather than a blank.

## Decks that look like decks

[office.py](../standalone/harness/office.py) used to hand python-pptx a title
and a bullet list and accept the default 4:3 template. It now renders a designed
deck: **16:9**, a cover with a full-height accent bar, content slides with a
title rule, bullet sizing that shrinks as a slide fills, slide numbers, and one
palette applied throughout. Spreadsheets get a dark header row, frozen panes,
fitted column widths, thousands separators and a bold total row.

Two constraints shaped it, and both still hold:

- **`slide.shapes.title` stays valid.** The benchmark graders and the viewer
  both find titles through it, so the design restyles real placeholders
  (layout 0 for the cover, layout 5 "Title Only" for content) instead of
  dropping to blank layouts.
- **Values and formulas are untouched.** The spreadsheet styling is presentation
  only, so `read_spreadsheet()` and the graders see exactly what they saw before.

Fonts are set at both paragraph *and* run level. Paragraph font is only a
default that runs inherit — anything reading run properties sees nothing, which
is precisely how the cover title looked like 30pt to the viewer while being 44pt
in PowerPoint.

## Related

- [[Running the Agent]] · [[Tools]] · [[Agent Loop]] · [[Ollama Shim]]
