# Demo video: one email in, a spreadsheet and a deck out

Working plan for the Agent Lab demo. Division of labour: I produce the screen
recording, you record the voiceover from the transcript below, ChatCut matches
the cut to your read.

Target length **75 seconds**. Timings use **145 words per minute**, which is
normal product-demo narration pace: conversational speech is 150 to 160, and
demo reads land slower because the viewer is also reading the screen. That is
**2.4 words per second**. Every section below gives a word budget, not just a
duration, so the transcript can be checked before anything is recorded.

---

## 1. Read this first: three things that decide the shoot

### 1.1 The inbox is simulated. Do not imply otherwise.

The email Dana "sends" is a fixture in the agent's own workspace. There is no
mail account connected: `harness/mcp_bridge.py` can reach real Gmail and
Outlook but nothing imports it yet (see `notes/Audit 2026-08-11.md`, finding 6).

So the narration says **"an email lands in the inbox"** and never "your Gmail",
"connected to Outlook", or "syncs with your mail". The demo is honest as a
capability demo. It becomes a lie the moment it claims a live account.

### 1.2 The model must actually be local on the day

Right now port 11434 is an OpenRouter shim pretending to be ollama. The UI says
"Ollama running" and the banner says `llama3.1:8b`, but the tokens are coming
from OpenRouter over the network. **The line "nothing leaves this machine" is
false while that shim is up.**

Before recording:

    pkill -f openrouter_shim.py
    ollama pull llama3.1:8b
    ollama serve

Then confirm the banner still says `llama3.1:8b` and the run completes. Expect
it to be slower than the shim; see 1.3.

### 1.3 The run is faster than the narration

Measured end to end against the shim: **10.7 seconds, 7 model calls**, from
pressing Run to both files existing. The narration for the same stretch is
about 40 seconds. Two options, and the plan below uses the second:

- Slow the footage in the edit. Looks like a stall.
- **Shoot the beats with deliberate holds.** I control pacing from the driver
  script: open the email, hold. Press Run, hold. Let the run play at real speed,
  hold on each artifact as it lands. Screen time then matches the read, and
  nothing is faked, because everything on screen happened when it appears to.

On real local ollama the run will be slower, which helps. Re-measure on the day
and adjust the holds; the driver script takes the hold lengths as arguments.

---

## 2. Recording setup

**Do not screen-record the desktop.** A full-screen capture picks up everything
else that is open. A test frame from this session showed a session list, a
Discord sidebar and a dozen personal file names. That footage cannot be shared.

Instead, Chrome in app mode, which has no tab strip and no URL bar, sized and
positioned exactly, with the capture cropped to that rectangle:

    open -na "Google Chrome" --args --new-window \
      --app=http://localhost:8765 \
      --window-size=1440,900 --window-position=0,0

    ffmpeg -f avfoundation -framerate 30 -i "3:none" \
      -vf "crop=2880:1800:0:0,scale=1440:900" \
      -c:v libx264 -crf 18 -pix_fmt yuv420p take.mp4

The crop is in physical pixels, so it is 2x the logical window on a Retina
display. Verify the first frame before shooting the whole take.

**Why a separate Chrome window and not the in-app browser:** the in-app preview
pane renders offscreen. `document.visibilityState` is `hidden` and a screen
capture of that region is whatever window happens to be in front. It cannot be
filmed. A real Chrome window can.

**Driving it:** Chrome is launched with `--remote-debugging-port=9222` and every
step goes through CDP `Runtime.evaluate`. `demo/cdp.py` is the client and
`demo/choreograph.py` is the shot list, so a take is reproducible and the holds
are arguments rather than hand timing.

Other pre-flight:

- Theme **dark**, glass **on** (the default). Both are in the person menu.
- Viewport 1440x900. Wider and the workspace and run panes both get roomy;
  narrower and the workspace becomes an overlay sheet.
- Reset the agent first so the file list is empty and the timeline is the
  welcome screen. The reset control is the circular arrow in the workspace
  header, or `POST /api/reset`.
- Seed Dana's email (script in section 5).
- One take per section is fine. ChatCut cuts on the transcript, so overlap is
  cheap and gaps are expensive: **hold every beat two seconds longer than feels
  right.**

---

## 3. The cut, beat by beat

Total 75s. Word budgets at 2.4 words/second.

### Beat 1 — Cold open, the empty app (0:00 to 0:07, 7s, ~17 words)

**On screen:** the welcome state. Logo, "Run your inbox, calendar and
documents". Nothing else moves.

> Everything here runs on this laptop. No account, no upload, no cloud.

*Note:* only say this after 1.2 is done.

### Beat 2 — The email (0:07 to 0:18, 11s, ~26 words)

**On screen:** workspace opens, inbox section, Dana's email at the top, click to
open it. Hold on the body long enough to read the three regional numbers.

> Dana sends the quarterly numbers and asks for two things. A spreadsheet with a
> total, and a short deck for Friday's review.

### Beat 3 — The ask (0:18 to 0:26, 8s, ~19 words)

**On screen:** the composer. Type the task at human speed, then Enter.

> I do not tell it how. I tell it what Dana asked for, and press Run.

### Beat 4 — The plan (0:26 to 0:38, 12s, ~29 words)

**On screen:** plan chips appear across the top, then the first model call
streams its reasoning. Hold on "Planned 4 steps."

> It writes a plan first, in tool names, not prose. Read the inbox, open Dana's
> mail, build the sheet, build the deck.

### Beat 5 — It looks before it writes (0:38 to 0:50, 12s, ~29 words)

**On screen:** `list_emails` then `read_email` rows land, each with the real
arguments it sent.

> It reads the actual email before it writes anything. That matters more than it
> sounds: this is where a model that guesses invents your numbers.

### Beat 6 — The artifacts land (0:50 to 1:04, 14s, ~34 words)

**On screen:** the workspace opens by itself as the first file is written. The
spreadsheet renders live, then the deck. Hold on each.

> The workspace opens on its own the moment something is written. The
> spreadsheet, with a real formula in the total row. Then the deck, from the
> same numbers.

### Beat 7 — The proof (1:04 to 1:15, 11s, ~26 words)

**On screen:** side by side, Dana's email and the total cell showing `=SUM(B2:B4)`.
Then the end card: model calls, tokens, time.

> Twelve forty, eight forty-five, six ten. The same three numbers she sent.
> Seven model calls, eleven seconds, on a laptop.

**Total: ~180 words, 75 seconds.**

---

## 3b. What five takes taught me

Take 5 is the keeper: `demo/agentlab-demo-take5.mp4`, 68 seconds, 1440x868.

- **Take 1** looked right and was not. The driver polled `window.S.run` to know
  when the run ended, and `app.js` declares `const S` at top level, which never
  becomes a window property. It read `undefined` and called the run finished 1.2
  seconds after Enter. Poll what the viewer sees instead: the Stop button is
  visible exactly while a run is in flight.
- **Take 2** exposed the inbox order. Dana's brand new email rendered at the
  BOTTOM of the inbox, under nine older ones, because the panel used
  state.json's insertion order while the agent's own `list_emails` sorts newest
  first. Fixed in the product, not worked around in the shoot.
- **Take 3** was well paced but shot the wrong hero. The run auto-opens the LAST
  artifact, which is the deck, so the spreadsheet never got a hold. The
  spreadsheet is the stronger proof: `=SUM(B2:B4)` is a real formula in a real
  .xlsx and anyone can make a model emit slide text. The shot list now clicks
  back to the sheet and gives it the longest dwell in the video.
- **Take 4** showed `1240000` where Dana's email said `$1,240,000`. The file was
  correct, with a `#,##0` number format Excel honours, but the browser preview
  printed `str(value)` and ignored the format. On camera it read as though the
  agent had mangled the number. Fixed in `webui/server.py`.
- **Take 5** shows `1,240,000 / 845,000 / 610,000` matching the email exactly.

Two of those four were real product bugs that only showed up because the app was
being filmed rather than clicked through.

## 4. What I would change about the idea

Your shape is right and I would shoot it first. Three notes.

1. **Lead with the payoff, not the empty app.** Consider a two-second cold open
   on the finished spreadsheet and deck, then cut to the empty app and "here is
   how that happened". Beat 1 as written asks the viewer to wait 18 seconds
   before anything is on screen. I would record both openings and let ChatCut
   decide.
2. **The strongest moment is the formula, not the deck.** Anyone can make a
   model emit slide text. `=SUM(B2:B4)` in the total row is a real spreadsheet
   formula in a real .xlsx, and it is the thing that says this is not a
   screenshot generator. Beat 7 should get the longest hold in the video.
3. **Do not narrate the harness.** The plan, the repair, the verifier are the
   interesting engineering and they belong in a second, longer video for a
   technical audience. This one answers "what does it do for me".

---

## 5. Setup script

Seed Dana's email and clear the workspace, run from `standalone/`:

```python
import json
p = 'agents/8b/workspace/state.json'
s = json.load(open(p))
s['emails'] = [e for e in s['emails'] if e['id'] != 'e11']
s['emails'].append({
    "id": "e11", "from": "dana@corp.com", "date": "2026-07-20 08:40",
    "subject": "Q3 regional numbers - sheet and deck for Friday?",
    "body": ("Morning! Final Q3 is in. West region $1,240,000; East region $845,000; "
             "Online $610,000. That is $2,695,000 all in, up 12% on Q2.\n\n"
             "Could you put these in a spreadsheet with a total, and turn the same "
             "numbers into a short deck for Friday's review? Thanks, Dana")
})
json.dump(s, open(p, 'w'), indent=2, ensure_ascii=False)
```

The task typed on camera:

> Read Dana's newest email and do what she asks: build the spreadsheet and the deck

Verified output, against the shim, 7 calls in 10.7s:

- `q3_numbers.xlsx` — Region/Amount, West 1240000, East 845000, Online 610000,
  Total `=SUM(B2:B4)`
- `q3_review.pptx` — three slides: Q3 Review; Regional Numbers with the three
  figures; Total $2,695,000, 12% up on Q2

## 6. Known risks on the day

- **The model is not deterministic.** Same prompt, different filenames and slide
  counts run to run. Shoot two or three takes and keep the cleanest. Do not
  re-cut the narration to match a filename.
- **It sometimes does extra work.** One observed run also messaged a third party
  it was never asked to contact. If a take does something unasked, discard the
  take; do not trim it out and imply it did not happen.
- **The composer keeps the task text after the run.** Minor, but on camera it
  looks like the box did not accept the input. Worth watching in playback.
- **Do not film "move my 2pm to Thursday" without re-testing it.** Until this
  pass the calendar was write-only and that phrasing produced a duplicate event
  plus a summary claiming the meeting had moved. `update_event` and
  `cancel_event` exist now, but it is the kind of task worth a dry run before
  the camera is on.

## 7. Reproducing a take

From `final-agent-8b/`:

```bash
open -na "Google Chrome" --args --new-window --app=http://localhost:8765 \
  "--remote-debugging-port=9222" "--user-data-dir=/tmp/chrome-demo" \
  "--window-size=1440,900" "--window-position=0,0" --no-first-run
python3 demo/choreograph.py     # prints each beat with its timestamp
```

Record in parallel, cropping to the window's physical rect (2x logical on
Retina; find it once by painting a full-viewport marker and locating it in a
screenshot):

```bash
ffmpeg -f avfoundation -framerate 30 -i "3:none" \
  -vf "crop=2876:1734:2:130,scale=1440:-2" \
  -c:v libx264 -crf 20 -pix_fmt yuv420p take.mp4
```
