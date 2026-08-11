"""Drive the Agent Lab demo window through the beats, with holds for narration."""
import subprocess, sys, time

CDP = ["python3", "%s/cdp.py" % (sys.path[0] or ".")]

def js(expr):
    r = subprocess.run(CDP + [expr], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()

def beat(name, seconds):
    print("  [%6.1fs] %s" % (time.time() - T0, name), flush=True)
    time.sleep(seconds)

# app.js declares `const S` at top level, so it is NOT a window property and
# every window.S poll reads undefined. Watch what the user watches instead:
# Stop is visible exactly while a run is in flight.
def RUNNING():
    return js("String(!document.getElementById('stop').classList.contains('hidden'))")

T0 = time.time()

# 1. cold open on the welcome state
js("location.reload(); 'reload'")
time.sleep(2.5)
js("document.documentElement.setAttribute('data-theme','dark');"
   "document.body.classList.remove('flat'); 'theme set'")
beat("welcome held", 4)

# 2. the email
js("document.getElementById('ws-btn').click(); 'workspace'")
beat("workspace opened", 1.5)
js("(()=>{const t=[...document.querySelectorAll('#tabs .tab')].find(b=>/workspace/i.test(b.textContent));"
   "if(t)t.click();return 'ws tab';})()")
beat("workspace tab", 1.5)
js("(()=>{const n=[...document.querySelectorAll('.node')].find(d=>/inbox/.test(d.textContent));"
   "if(n){n.open=true;n.scrollIntoView({block:'start'});}return 'inbox open';})()")
beat("inbox shown", 2.5)
js("(()=>{const b=[...document.querySelectorAll('.item')].find(x=>/Q3 regional numbers/.test(x.textContent));"
   "if(!b) return 'EMAIL ROW NOT FOUND';"
   "b.scrollIntoView({block:'center'});b.click();return 'clicked';})()")
time.sleep(1.2)
opened = js("String(!document.getElementById('viewer').classList.contains('hidden'))")
print("  viewer open:", opened, flush=True)
beat("Dana's email body held", 7)
js("(()=>{const c=document.getElementById('viewer-close');if(c)c.click();return 'closed';})()")
beat("viewer closed", 1)

# 3. the ask, typed at human speed
# Measured, not written for feel. "do what she asks" produced the artifacts in
# 2 runs of 5; naming the spreadsheet took opening the attachment to 7 of 7, and
# "both of the things" took the deck from 1 in 7 to 3 of 3. See the plan, s5.
TASK = ("Read Dana's newest email, open the spreadsheet she mentions, "
        "and produce both of the things she asks for")
js("document.getElementById('ws-btn').click(); document.getElementById('task').focus(); 'focus'")
time.sleep(0.8)
for i in range(1, len(TASK) + 1, 2):
    js("(()=>{const t=document.getElementById('task');t.value=%r;"
       "t.dispatchEvent(new Event('input',{bubbles:true}));return 1;})()" % TASK[:i])
beat("task typed", 1.5)

# 4-6. the run, live
js("(()=>{const t=document.getElementById('task');t.focus();"
   "t.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));"
   "return 'RUN';})()")
print("  [%6.1fs] RUN pressed" % (time.time() - T0), flush=True)
# wait for it to START. Polling for "not running" straight after Enter saw the
# state before the POST had returned and declared the run over in 1.2 seconds.
for _ in range(30):
    if RUNNING() == "true":
        break
    time.sleep(0.5)
else:
    print("  WARNING: run never started", flush=True)
print("  [%6.1fs] run started" % (time.time() - T0), flush=True)
for _ in range(120):
    if RUNNING() == "false":
        break
    time.sleep(1)
print("  [%6.1fs] run finished" % (time.time() - T0), flush=True)

# Beat 5. read_spreadsheet on q3_raw.xlsx is the moment the video's whole claim
# rests on: the numbers came out of her file, not out of the model. Put it on
# screen deliberately instead of letting it scroll past inside the run.
found = js("(()=>{const r=[...document.querySelectorAll('.ev')]"
           ".filter(x=>/read_spreadsheet/.test(x.textContent)).pop();"
           "if(!r) return 'READ ROW NOT FOUND - take is invalid';"
           "r.scrollIntoView({block:'center'});"
           "return 'read row shown';})()")
print("  ", found, flush=True)
beat("read_spreadsheet held, source rows visible", 7)
# The run auto-opens the LAST artifact, which is the deck. The spreadsheet is
# the stronger proof (a real =SUM formula, not generated prose), so hold there
# first and give it the longest dwell in the video.
# NOT just /xlsx/: q3_raw.xlsx is open too now that the agent reads it, and it
# sorts first. Holding on the source file while the narration says "the sheet it
# built" would be the one genuinely dishonest frame in the video.
js("(()=>{const t=[...document.querySelectorAll('#tabs .tab')]"
   ".find(b=>/xlsx/i.test(b.textContent) && !/q3_raw/i.test(b.textContent));"
   "if(!t) return 'GENERATED SHEET TAB NOT FOUND';"
   "t.click();return 'sheet tab';})()")
beat("SPREADSHEET held, formula visible", 8)

js("(()=>{const t=[...document.querySelectorAll('#tabs .tab')].find(b=>/pptx/i.test(b.textContent));"
   "if(t)t.click();return 'deck tab';})()")
beat("deck held", 6)
js("(()=>{const c=document.getElementById('canvas');if(c)c.scrollTo({top:c.scrollHeight,behavior:'smooth'});return 'scroll';})()")
beat("deck scrolled to the total slide", 5)

js("(()=>{const f=document.querySelector('.feed');if(f)f.scrollTo({top:f.scrollHeight,behavior:'smooth'});return 'endcard';})()")
beat("end card held", 6)
print("  DONE in %.1fs" % (time.time() - T0))
