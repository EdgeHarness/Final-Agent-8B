# Demo video: one email in, a spreadsheet and a deck out

Working plan for the Agent Lab demo. Division of labour: I produce the screen
recording, you record the voiceover from the transcript below, ChatCut matches
the cut to your read.

Target length **85 seconds** (take 6; take 5 as shot is 68). Timings use **145 words per minute**, which is
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

### 1.2 The shim is fine for takes. It matters only for a published claim.

Port 11434 is an OpenRouter shim standing in for ollama, deliberately: it is a
local testing convenience and it is not pushed. `openrouter_shim.py` is
git-excluded and the key lives in the environment, never in a tracked file.

So every take in `demo/` is a valid rehearsal, and the pacing, the beats and the
artifacts are all real. The one thing the shim changes is **whether beat 1 can
be said out loud**. "Everything here runs on this laptop" is a claim about where
the tokens come from, and while the shim is up they come from OpenRouter.

Two honest ways to ship:

- **Record the final take against real ollama.** `pkill -f openrouter_shim.py`,
  `ollama pull llama3.1:8b`, `ollama serve`. Slower per call, which helps the
  pacing. Then beat 1 is true as written.
- **Or keep the shim and drop the locality claim** from beat 1, making it a
  capability demo: "one email in, a spreadsheet and a deck out." The footage
  needs no change either way, only the narration.

Decide before the voiceover is recorded, not after.

### 1.2b Demo in draft mode. Do not demo live mode.

The MCP bridge is wired now, so the app can reach real Gmail and Outlook. For a
recorded demo the answer is **draft mode, or no MCP at all** - and draft is the
better story anyway, not a compromise:

- **Draft mode never shows the model a tool that can transmit.** Send, forward
  and reply are dropped from the registry before the model sees it, so the
  worst case on camera is a draft sitting in a Drafts folder. There is no take
  where a wrong click mails a stranger.
- **"The agent composes, you send" is the line you want.** It is the honest
  description of the safety model and it is more reassuring than a demo that
  shows an agent sending mail unattended.
- **Live mode cannot be rehearsed.** Every take sends. There is no second
  attempt at an email that already left.

Take 5 as shot uses no MCP at all - the whole run is the simulated office - so
it is already safe and needs no change. If you want a real-account beat, shoot
it as a SEPARATE short segment in draft mode against a throwaway account, and
end on the draft appearing in the real Gmail web UI. That shot is the proof,
and it costs nothing if it goes wrong.

Real-account confirmations are now visually distinct in the UI: a red card that
names the account, and in live mode says the message cannot be undone with the
button relabelled "Send it". That is what makes a live demo *possible*; it is
still not what makes it *wise*.

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
- Seed Dana's email and the attachment (section 5). Seed **after** the reset,
  since the reset clears the files directory.
- One take per section is fine. ChatCut cuts on the transcript, so overlap is
  cheap and gaps are expensive: **hold every beat two seconds longer than feels
  right.**

---

## 3. The cut, beat by beat

**This is the take 6 cut.** Takes 1 to 5 shot an earlier version where Dana's
numbers were written out in the email body. Three changes, all in section 3c:
the numbers now live in an attachment, the ask carries a date, and one beat is
reserved for a guard firing. Take 5 remains a valid fallback if take 6 does not
come together.

Total 85s. Word budgets at 2.4 words/second.

### Beat 1 — Cold open, the empty app (0:00 to 0:07, 7s, ~17 words)

**On screen:** the welcome state. Logo, "Run your inbox, calendar and
documents". Nothing else moves.

> Everything here runs on this laptop. No account, no upload, no cloud.

*Note:* only say this after 1.2 is done.

### Beat 2 — The email (0:07 to 0:18, 11s, ~26 words)

**On screen:** workspace opens, inbox section, Dana's email at the top, click to
open it. Hold on the body. The body has no figures in it, only the filename.

> Dana asks for two things off an export she attached. A clean spreadsheet with
> a total, and a short deck for the review.

### Beat 3 — The ask (0:18 to 0:26, 8s, ~19 words)

**On screen:** the composer. Type the task at human speed, then Enter.

> I do not tell it how. I tell it what Dana asked for, and press Run.

### Beat 4 — The plan (0:26 to 0:38, 12s, ~29 words)

**On screen:** plan chips appear across the top, then the first model call
streams its reasoning. Hold on the step count.

> It writes a plan first, in tool names, not prose. Open the mail, open the
> file, build the sheet, build the deck.

### Beat 5 — It opens the file (0:38 to 0:52, 14s, ~34 words)

**On screen:** `read_email`, then `read_spreadsheet` on `q3_raw.xlsx`, with the
returned rows visible in the call result. Hold on the rows.

> The numbers were never in the email. It opens the file and reads them. That is
> the difference between an agent and a model guessing what your figures were.

### Beat 6 — The harness pushes back (0:52 to 1:04, 12s, ~29 words)

**On screen:** whichever guard fires. See 3c: this beat is reserved, not
scripted. If nothing fires in the take, cut straight from beat 5 to beat 7 and
drop these words.

> It does not always get it right first time. When it drifts, the harness asks
> it a question rather than letting it through.

### Beat 7 — The artifacts land (1:04 to 1:18, 14s, ~34 words)

**On screen:** the workspace opens by itself as the first file is written. The
spreadsheet renders live, then the deck. Hold on each.

> The workspace opens on its own the moment something is written. The
> spreadsheet, with a real formula in the total row. Then the deck, from the
> same numbers.

### Beat 8 — The proof (1:18 to 1:29, 11s, ~26 words)

**On screen:** side by side, the Q3 column of `q3_raw.xlsx` and the total cell
showing `=SUM(B2:B4)`. Then the end card: model calls, tokens, time.

> Twelve forty, eight forty-five, six ten. Straight out of her file. Nine model
> calls, on a laptop.

**Total: ~197 words, 85 seconds.**

### 3c. The guard beat, and why it cannot be scripted

Beat 6 is the only beat in this cut that shows the middle of the diagram, and it
is the only reason the video is not "an AI made a spreadsheet". It is also the
only beat I cannot promise will happen, because a guard fires when the model
errs and the model is not obliged to err on cue.

What the fixture does is raise the odds honestly. Three ways it can fire:

- **Planned read before writing.** The plan names `read_spreadsheet` before
  `create_spreadsheet`; an 8B that jumps to the write is questioned once. Most
  likely of the three, precisely because the data now lives in a file.
- **Date mismatch.** Dana's mail says "Wednesday's review" and asks for a
  Thursday reminder. `set_reminder` is a write with a date, so a wrong ISO date
  gets caught and quoted back. This is why the reminder is in the ask at all.
- **Unplanned write.** Fires if the model invents work its own plan never named.

So: shoot three or four takes. If a guard fires in one of them, that is the
take, and the moment is genuine. If none fires, ship the shorter cut without
beat 6 rather than staging one. A staged guard is the one thing in this video
that would be a lie, and it is the exact claim a technical viewer will check.

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

   *Revised after take 5.* Point 3 was too absolute. Not narrating the harness
   left a video that showed a straight pipeline: prompt in, files out, which is
   what every wrapper looks like. One beat of the loop is worth the twelve
   seconds (beat 6). The full explanation still belongs in the second video.
4. **The numbers belong in a file, not in the email body.** Takes 1 to 5 had
   Dana write the figures out in prose and the agent retype them. That is the
   exact shape of the worst bug the audit found: an 8B reading numbers from
   prose invents plausible ones, and on camera nobody can tell the difference
   until they check. Moving them into `q3_raw.xlsx` makes the tool result the
   ground truth and makes beat 5 a stronger claim, not a weaker one.
5. **One seeded email, never a live mailbox.** Sender identity is not part of
   the story and a live inbox means unrelated mail can ruin a take.

---

## 5. Setup script

Reset the agent first, then seed. One command, idempotent, from `standalone/`:

```bash
../.venv/bin/python ../demo/seed_take6.py
```

That writes `agents/8b/workspace/files/q3_raw.xlsx`:

| Region | Q2 | Q3 |
|---|---|---|
| West | 1,105,000 | 1,240,000 |
| East | 802,000 | 845,000 |
| Online | 498,000 | 610,000 |

and seeds email `e11` from Dana, whose body names the file and contains **no
figures at all**. Q2 is in the sheet on purpose: the ask is for the Q3 column,
so picking the right column is work the agent has to actually do rather than
copy the only thing present.

Verified: `read_spreadsheet('q3_raw.xlsx')` returns those rows, and e11 is the
newest email so it renders at the top of the inbox panel.

The task typed on camera:

> Read Dana's newest email and do what she asks

Shorter than the take 5 task on purpose. "build the spreadsheet and the deck"
told the agent the answer; this version makes it derive both from the mail,
which is what the video claims it does.

Expected output, three artifacts:

- `q3_numbers.xlsx` — Region/Amount, the three Q3 figures, Total `=SUM(B2:B4)`
- `q3_review.pptx` — a short deck off the same numbers
- a reminder on Thursday to send it round

Re-measure the call count and wall time on the day; the take 5 figures (7 calls,
10.7s) are for the old, easier fixture and will be low for this one.

## 6. Known risks on the day

- **The take 6 fixture is harder than take 5's, deliberately.** Three artifacts
  instead of two, a column to choose, and a filename to carry from the email
  into a tool call. Expect a lower success rate per take and budget more takes.
  If the 8B cannot land it in four or five attempts, that is a finding worth
  writing into the audit, not a reason to simplify the fixture back.
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
