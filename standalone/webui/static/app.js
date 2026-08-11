/* Agent Lab — pick a model, run a task, watch the loop. */
'use strict';

const $ = (id) => document.getElementById(id);
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({ error: r.statusText }));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
};
const post = (path, body) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body || {}) });

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
const bytes = (n) => n < 1024 ? `${n} B`
  : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
const clip = (s, n) => (s = String(s ?? ''), s.length > n ? s.slice(0, n) + '…' : s);
const ago = (ts) => {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};

const TOOL_ICON = {
  list_emails: '📥', read_email: '✉️', send_email: '📤', list_events: '📅',
  add_event: '📅', send_message: '💬', set_reminder: '⏰',
  create_presentation: '📊', create_spreadsheet: '📈', read_spreadsheet: '📈',
  think: '💭', save_memory: '🧠', recall_memories: '🧠', done: '✅',
  list_dir: '📁', read_file: '📄', write_file: '✏️', append_file: '➕',
  delete_path: '🗑️', move_path: '↔️', search_files: '🔎', run_command: '⌨️',
};

/* A call that changes the world, rather than reading it. The dot on the
   timeline is green for these and blue for a read, so the shape of a run is
   legible before a word of it is read. */
const MUTATORS = new Set([
  'send_email', 'add_event', 'send_message', 'set_reminder', 'save_memory',
  'create_presentation', 'create_spreadsheet',
  'write_file', 'append_file', 'delete_path', 'move_path', 'run_command',
]);

/* Which argument names the file a tool produced. Office files land in the
   agent's workspace, which is what /api/preview can read, so those get a real
   preview pane. write_file and append_file go to the user's own folder: they
   belong in the touched strip, but there is nothing to render for them. */
const ARTIFACT_ARG = { create_presentation: 'filename', create_spreadsheet: 'filename' };
const TOUCH_ARG = { ...ARTIFACT_ARG, write_file: 'path', append_file: 'path' };

const S = {
  agents: [], agent: null, ws: null, run: null, es: null,
  call: null, t0: 0, timer: null, seen: {}, first: true,
  open: new Set(['files', 'inbox', 'calendar']),
};

/* ------------------------------------------------------------- models --- */

async function loadAgents(keep) {
  const data = await api('/api/agents');
  S.agents = data.agents;
  S.available = data.available || [];
  $('meter-ollama').className = 'meter dotmeter ' + (data.ollama ? 'up' : 'down');
  $('meter-ollama').querySelector('.label').textContent =
    data.ollama ? 'Ollama running' : 'Ollama not running';
  renderPresets(data.presets);
  renderAgents();
  renderModels(data.installed_models);
  if (!keep) {
    const pick = S.agents.find((a) => a.installed) || S.agents[0];
    if (pick) selectAgent(pick.id);
  }
}

/* The model tag is what a person picks by, so it leads. The folder label ("8B")
   was the headline and the tag was supporting text under it, which had the
   naming backwards: every folder is named after its model, so the folder label
   only repeats the tag in a vaguer form.
   Below it, the model's own description, generated from openrouter into
   model_catalog.json and shipped, so describing a model needs no network. */
function agentRow(a) {
  const on = a.id === S.agent;
  const cat = a.catalog || {};
  const card = el('button', 'agent' + (on ? ' on' : ''));
  card.type = 'button';
  card.setAttribute('role', 'radio');
  card.setAttribute('aria-checked', on ? 'true' : 'false');
  card.onclick = () => selectAgent(a.id);

  const head = el('div', 'agent-head');
  head.append(el('span', 'agent-name', a.model));
  if (!a.installed) head.append(el('span', 'agent-flag', 'not installed'));
  else if (a.runs) head.append(el('span', 'agent-trail', `${a.runs} run${a.runs === 1 ? '' : 's'}`));
  card.append(head);

  if (cat.title) {
    card.append(el('div', 'agent-support',
      [cat.vendor, cat.title].filter(Boolean).join(' ')));
  }
  card.append(el('div', 'agent-desc', cat.description || a.blurb || ''));

  const meta = [
    cat.context ? `${Math.round(cat.context / 1024)}k context` : null,
    a.speed,
    a.profile ? a.profile.label : null,
    `${a.files} file${a.files === 1 ? '' : 's'}`,
    `${a.memories} learned`,
  ].filter(Boolean).join('  ·  ');
  card.append(el('div', 'agent-meta', meta));

  if (!a.installed) card.append(downloadRow(a, cat));
  return card;
}

/* The command to run, one click to copy, plus a link to the model's own page.
   There used to be a Download button here that posted to the local ollama's
   /api/pull and streamed progress in place. It was removed: it only works
   against a real ollama, and anything else answering on that port (an
   OpenAI-compatible proxy, say) returns 404, so the row's reward for a click
   was a raw HTTPError quoting a 127.0.0.1 URL at someone who cannot act on it.
   The command works on every machine and says exactly what it will do. */
function downloadRow(a, cat) {
  const row = el('div', 'agent-get');
  const cmd = cat.pull || `ollama pull ${a.model}`;

  const copy = el('button', 'cmd', '');
  copy.type = 'button';
  copy.title = 'Copy this command';
  copy.append(el('code', null, cmd), el('span', 'cmd-hint', 'copy'));
  copy.onclick = (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(cmd).then(
      () => { copy.querySelector('.cmd-hint').textContent = 'copied'; },
      () => { copy.querySelector('.cmd-hint').textContent = 'select it'; });
    setTimeout(() => { copy.querySelector('.cmd-hint').textContent = 'copy'; }, 1600);
  };
  row.append(copy);

  if (cat.url) {
    const link = el('a', 'agent-link', 'Model page');
    link.href = cat.url;
    link.target = '_blank';
    link.rel = 'noreferrer noopener';
    link.onclick = (e) => e.stopPropagation();
    row.append(link);
  }
  return row;
}

function renderAgents() {
  const box = $('agents');
  box.textContent = '';
  const q = ($('agent-filter').value || '').trim().toLowerCase();
  /* Most used first, so the model you reach for is the one at the top. Ties
     break on the tag rather than on folder order, which is arbitrary. */
  const ranked = [...S.agents].sort((x, y) =>
    y.runs - x.runs || x.model.localeCompare(y.model));
  const shown = ranked.filter((a) => !q ||
    [a.model, a.name, a.speed, (a.catalog || {}).title, (a.catalog || {}).vendor]
      .some((f) => String(f || '').toLowerCase().includes(q)));

  for (const a of shown) box.append(agentRow(a));
  $('agents-none').classList.toggle('hidden', !!shown.length);
  /* A filter over three things is furniture. It appears once the list is long
     enough that finding a model is actually work. */
  $('rail-search').classList.toggle('hidden', S.agents.length < 6);
  $('agent-count').textContent = S.agents.length > 1 ? String(S.agents.length) : '';
  renderAvailable(q);
}

/* Models the catalog knows about that are not installed. Same row shape as an
   agent, minus the counts it cannot have yet, so the column reads as one list
   of models rather than two unrelated ones. */
function renderAvailable(q) {
  const box = $('available');
  box.textContent = '';
  const shown = (S.available || []).filter((m) => !q ||
    [m.tag, m.title, m.vendor].some((f) => String(f || '').toLowerCase().includes(q)));
  for (const m of shown) {
    const row = el('div', 'agent avail');
    const head = el('div', 'agent-head');
    head.append(el('span', 'agent-name', m.tag),
                el('span', 'agent-trail', m.context ? `${Math.round(m.context / 1024)}k` : ''));
    row.append(head);
    row.append(el('div', 'agent-support', [m.vendor, m.title].filter(Boolean).join(' ')));
    row.append(el('div', 'agent-desc avail-desc', m.description || ''));
    row.append(downloadRow({ model: m.tag }, m));
    box.append(row);
  }
  $('rail-more').classList.toggle('hidden', !shown.length);
}

async function selectAgent(id) {
  S.agent = id;
  S.first = true;
  S.seen = {};
  renderAgents();
  syncModel();
  await loadWorkspace();
  $('run').disabled = !!S.run;
}

// The agent folder decides the harness profile and owns the state; this only
// decides which installed tag does the talking. Defaults to the model
// config.json names, and falls back to whatever IS installed so a fresh
// machine can demo without a 4.7 GB download first.
const MORE = '__more__';

function renderModels(list) {
  const sel = $('model');
  sel.textContent = '';
  for (const m of list || []) sel.append(new Option(m, m));
  if (!sel.options.length) sel.append(new Option('no models installed', ''));
  /* The picker is where you go when you want a different model, so it is also
     where "I want one I do not have" belongs. Choosing it opens the rail
     rather than changing the model. */
  const more = new Option('More models…', MORE);
  more.className = 'opt-more';
  sel.append(more);
  syncModel();
}

function syncModel() {
  const sel = $('model');
  const a = S.agents.find((x) => x.id === S.agent);
  if (!a || !sel.options.length) return;
  const exact = [...sel.options].find((o) => o.value === a.model && o.value !== MORE);
  sel.value = exact ? a.model : sel.options[0].value;
  sel.classList.toggle('substituted', !exact);
  sel.title = exact
    ? `${a.model} — the model this agent folder is configured for`
    : `${a.model} is not installed; running on ${sel.value} instead`;
}

function renderPresets(list) {
  const box = $('presets');
  box.textContent = '';
  /* One row that scrolls sideways, rather than a block that wraps to five.
     Six wrapped suggestions took more vertical space than the transcript they
     sit under and read as the main content of the pane. Shorter labels than
     the wrapped version carried, since a row is scanned, not read. */
  for (const t of list) {
    const b = el('button', 'preset', clip(t, 44));
    b.type = 'button';
    b.title = t;
    b.onclick = () => { $('task').value = t; $('task').focus(); growTask(); };
    box.append(b);
  }
}

/* ---------------------------------------------------------- the folder --- */

async function loadWorkspace() {
  if (!S.agent) return;
  S.ws = await api(`/api/workspace?agent=${S.agent}`);
  $('folder-path').textContent = S.ws.folder;
  renderTree(S.ws);
}

function section(key, icon, name, items, render, emptyText) {
  const d = el('details', 'node');
  d.open = S.open.has(key);
  d.ontoggle = () => d.open ? S.open.add(key) : S.open.delete(key);

  const sum = el('summary');
  const count = el('span', 'count', String(items.length));
  sum.append(el('span', 'caret', '▶'), el('span', 'ico', icon),
             el('span', 'nm', name), count);
  d.append(sum);

  const list = el('div', 'items');
  if (!items.length) {
    list.append(el('div', 'empty-note', emptyText));
  } else {
    const prev = S.seen[key] || null;
    const keys = [];
    items.forEach((item, i) => {
      const node = render(item, i);
      const k = JSON.stringify(item);
      keys.push(k);
      if (prev && !prev.has(k)) {
        node.classList.add('fresh');
        count.classList.add('bump');
        d.open = true;
        S.open.add(key);
      }
      list.append(node);
    });
    if (!S.first || !prev) S.seen[key] = new Set(keys);
  }
  d.append(list);
  return d;
}

function itemNode(line1, line2, onclick) {
  const n = el('button', 'item');
  const t1 = el('div', 't1');
  t1.innerHTML = line1;
  n.append(t1);
  if (line2) n.append(el('div', 't2', line2));
  if (onclick) n.onclick = onclick; else n.style.cursor = 'default';
  return n;
}

const esc = (s) => String(s ?? '').replace(/[&<>]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function renderTree(ws) {
  const tree = $('tree');
  tree.textContent = '';

  tree.append(section('files', '📁', 'files', ws.files, (f) =>
    itemNode(`<b>${esc(f.name)}</b>`, `${bytes(f.size)} · ${ago(f.mtime)}`,
             () => openFile(f.name)),
    'nothing created yet'));

  tree.append(section('inbox', '📥', 'inbox', ws.emails, (e) =>
    itemNode(`<b>${esc(e.subject)}</b>`, `${e.from} · ${e.date}`,
             () => openEmail(e)),
    'inbox empty'));

  tree.append(section('calendar', '📅', 'calendar', ws.events, (v) =>
    itemNode(`<b>${esc(v.title)}</b>`,
             `${v.date} · ${v.start}–${v.end}${v.location ? ' · ' + v.location : ''}` +
             (v.attendees && v.attendees.length ? ` · ${v.attendees.join(', ')}` : '')),
    'no events'));

  tree.append(section('messages', '💬', 'messages', ws.messages, (m) =>
    itemNode(`to <b>${esc(m.to)}</b>`, clip(m.text, 160)),
    'none sent'));

  tree.append(section('reminders', '⏰', 'reminders', ws.reminders, (r) =>
    itemNode(esc(r.text), `${r.date} at ${r.time}`),
    'none set'));

  tree.append(section('sent', '📤', 'sent mail', ws.sent, (m) =>
    itemNode(`<b>${esc(m.subject || '(no subject)')}</b>`, `to ${m.to} · ${clip(m.body, 90)}`,
             () => openViewer(m.subject || 'Sent mail', mailBody({ ...m, from: 'you' }))),
    'nothing sent'));

  tree.append(section('memory', '🧠', 'memory', ws.memory, (f) =>
    itemNode(esc(f), null), 'nothing learned yet'));

  if (ws.tree) {
    tree.append(section('real', '💽', 'working folder', ws.tree, (f) =>
      itemNode((f.dir ? '📂 ' : '') + esc(f.name), f.dir ? null : bytes(f.size || 0)),
      'empty'));
  }

  tree.append(section('runs', '📜', 'past runs', ws.logs || [], (l) =>
    itemNode(esc(l.name.replace('.json', '')), ago(l.mtime), () => openLog(l.name)),
    'no runs yet'));

  S.first = false;
}

/* -------------------------------------------------------------- viewer --- */

function openViewer(title, node, dl) {
  $('viewer-title').textContent = title;
  const body = $('viewer-body');
  body.textContent = '';
  body.append(node);
  const a = $('viewer-dl');
  if (dl) { a.href = dl; a.classList.remove('hidden'); } else a.classList.add('hidden');
  $('viewer').classList.remove('hidden');
}
const closeViewer = () => $('viewer').classList.add('hidden');

function mailBody(e) {
  const box = el('div');
  box.append(el('div', 'mail-meta',
    `${e.from ? 'from ' + e.from : ''}${e.to ? 'to ' + e.to : ''}${e.date ? ' · ' + e.date : ''}`));
  box.append(el('div', 'mail-body', e.body || ''));
  return box;
}
const openEmail = (e) => openViewer(e.subject, mailBody(e));

// ---------------------------------------------------------- office viewers --
// Both render from real geometry the server pulled out of the file, so what you
// see is close to what PowerPoint/Excel would draw — not a text summary.

const COL_LETTER = (n) => {
  let s = '';
  while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = (n - 1 - m) / 26; }
  return s;
};

function renderDeck(p) {
  const wrap = el('div', 'deck');
  // Every length is a fraction of the slide, so one CSS container query unit
  // (cqw = 1% of the frame width) scales text and boxes together at any size.
  const pctW = (v) => (v / p.w_pt) * 100;
  p.slides.forEach((s, i) => {
    wrap.append(el('div', 'n', `slide ${i + 1} of ${p.slides.length}`));
    const frame = el('div', 'slide-frame');
    frame.style.aspectRatio = `${p.w_pt} / ${p.h_pt}`;
    for (const sh of s.shapes) {
      const node = el('div', 'sh sh-' + sh.kind);
      node.style.left = sh.x * 100 + '%';
      node.style.top = sh.y * 100 + '%';
      node.style.width = sh.w * 100 + '%';
      node.style.height = sh.h * 100 + '%';
      if (sh.fill) node.style.background = sh.fill;
      if (sh.kind === 'picture') {
        const img = el('img');
        img.src = sh.src;
        node.append(img);
      } else if (sh.kind === 'table') {
        const t = el('table', 'sh-table');
        sh.rows.forEach((row, ri) => {
          const tr = el('tr');
          row.forEach((c) => tr.append(el(ri === 0 ? 'th' : 'td', null, c)));
          t.append(tr);
        });
        node.append(t);
      } else if (sh.kind === 'text') {
        for (const para of sh.paragraphs) {
          const line = el('p', 'sh-p');
          line.textContent = para.text;
          line.style.fontSize = pctW(para.size) + 'cqw';
          if (para.color) line.style.color = para.color;
          if (para.bold) line.style.fontWeight = '700';
          if (para.align) line.style.textAlign = para.align;
          if (para.level) line.style.paddingLeft = para.level * 3 + '%';
          if (!sh.title && para.level >= 0 && sh.paragraphs.length > 1) {
            line.classList.add('bullet');
          }
          node.append(line);
        }
      }
      frame.append(node);
    }
    wrap.append(frame);
  });
  return wrap;
}

function renderWorkbook(p) {
  const wrap = el('div', 'book');
  p.sheets.forEach((sh, si) => {
    const tab = el('div', 'sheet-tab' + (si === 0 ? ' on' : ''));
    tab.textContent = sh.sheet;
    wrap.append(tab);

    // cells swallowed by a merge must not be emitted at all
    const skip = new Set();
    for (const m of sh.merges) {
      for (let r = m.r; r < m.r + m.rs; r++) {
        for (let c = m.c; c < m.c + m.cs; c++) {
          if (r !== m.r || c !== m.c) skip.add(r + ':' + c);
        }
      }
    }
    const span = {};
    for (const m of sh.merges) span[m.r + ':' + m.c] = m;

    const scroll = el('div', 'sheet-scroll');
    const t = el('table', 'grid');
    const head = el('tr');
    head.append(el('th', 'corner'));
    for (let c = 1; c <= sh.cols; c++) {
      const th = el('th', 'colhead', COL_LETTER(c));
      th.style.minWidth = Math.max(48, sh.widths[c - 1] || 72) + 'px';
      head.append(th);
    }
    t.append(head);

    sh.rows.forEach((row, ri) => {
      const tr = el('tr');
      tr.append(el('th', 'rowhead', String(ri + 1)));
      row.forEach((cell, ci) => {
        const key = (ri + 1) + ':' + (ci + 1);
        if (skip.has(key)) return;
        const td = el('td', null, cell.v);
        const m = span[key];
        if (m) { if (m.cs > 1) td.colSpan = m.cs; if (m.rs > 1) td.rowSpan = m.rs; }
        if (cell.b) td.style.fontWeight = '700';
        if (cell.a) td.style.textAlign = cell.a;
        if (cell.f) { td.classList.add('formula'); td.title = cell.f; }
        tr.append(td);
      });
      t.append(tr);
    });
    scroll.append(t);
    wrap.append(scroll);
    if (sh.truncated) {
      wrap.append(el('div', 'n', `showing the first ${sh.rows.length} rows`));
    }
  });
  return wrap;
}

/* One place that turns a preview payload into a node, so the full pane, the
   thumbnail and the modal cannot drift apart. */
function renderPreview(p) {
  if (p.kind === 'pptx') return renderDeck(p);
  if (p.kind === 'xlsx') return renderWorkbook(p);
  if (p.kind === 'text') return el('div', 'plain', p.text);
  return el('div', 'plain', `binary file, ${bytes(p.size)} — download to open it`);
}

async function openFile(name) {
  const url = `/api/download?agent=${S.agent}&name=${encodeURIComponent(name)}`;
  let p;
  try {
    p = await api(`/api/preview?agent=${S.agent}&name=${encodeURIComponent(name)}`);
  } catch (err) {
    return openViewer(name, el('div', 'plain', String(err.message)));
  }
  const box = el('div');
  box.append(renderPreview(p));
  openViewer(name, box, url);
}

async function openLog(name) {
  const log = await api(`/api/log?agent=${S.agent}&name=${encodeURIComponent(name)}`);
  const box = el('div');
  box.append(el('div', 'mail-meta',
    `${log.model || ''} · ${log.finished ? 'finished' : 'ran out of model calls'}${log.summary ? ' · ' + log.summary : ''}`));
  box.append(el('div', 'mail-body', log.task));
  const pre = el('pre', 'raw');
  pre.textContent = (log.transcript || [])
    .filter((t) => t.kind !== 'system')
    .map((t) => `[${t.kind}] ${t.content}`).join('\n\n');
  box.append(pre);
  openViewer(name, box);
}

/* ----------------------------------------------- the artifact pane ------ */
/* The point of this layout: a file lands, it is on screen. No click, no modal,
   at the size the thing is actually meant to be read at. */

/* The All and Workspace tabs exist before anything does. Codex keeps its
   top-level tabs visible whether or not they have content, so the right side
   always says what it is for instead of being an unexplained empty box. */
const panes = {
  all: { pane: $('pane-all'), tab: null },
  ws: { pane: $('pane-ws'), tab: null },
};
const allCount = el('span', 'count', '0');

function makeTab(label, cls, onSelect) {
  const tab = el('button', 'tab' + (cls ? ' ' + cls : ''));
  tab.type = 'button';
  tab.setAttribute('role', 'tab');
  tab.append(document.createTextNode(label));
  tab.onclick = onSelect;
  $('tabs').append(tab);
  return tab;
}

/* A role=tablist promises arrow-key navigation and a roving tabindex: one stop
   for the whole group, arrows to move within it. Every tab being tabindex 0
   means Tab walks through all of them, which is the behaviour the role tells
   screen reader users will not happen. */
$('tabs').addEventListener('keydown', (ev) => {
  const tabs = [...$('tabs').querySelectorAll('.tab')];
  const i = tabs.indexOf(document.activeElement);
  if (i < 0) return;
  const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[ev.key];
  if (to === undefined) return;
  ev.preventDefault();
  const next = tabs[(to + tabs.length) % tabs.length];
  next.focus();
  next.click();
});

panes.all.tab = makeTab('All', null, () => select('all'));
panes.all.tab.append(allCount);
panes.ws.tab = makeTab('Workspace', null, () => select('ws'));

function select(name) {
  for (const [k, v] of Object.entries(panes)) {
    const on = k === name;
    v.pane.classList.toggle('on', on);
    v.tab.classList.toggle('on', on);
    v.tab.setAttribute('aria-selected', on ? 'true' : 'false');
    // roving tabindex: the selected tab is the group's single tab stop
    v.tab.tabIndex = on ? 0 : -1;
  }
}
select('all');   // the All tab reads as selected from the first frame

async function showArtifact(name, stat) {
  if (panes[name]) {
    // a rewrite: the caption has to follow, or the All view disagrees with the
    // chip strip about what the agent just produced
    if (panes[name].stat) panes[name].stat.textContent = stat || '';
    return select(name);
  }
  let payload;
  try {
    payload = await api(`/api/preview?agent=${S.agent}&name=${encodeURIComponent(name)}`);
  } catch (_) {
    return;                    // the touched chip already records that it exists
  }
  if (panes[name]) return;     // two events for the same file raced here

  $('holding').classList.add('hidden');
  $('grid-all').classList.remove('hidden');
  // the first file is the moment the workspace becomes worth looking at
  setWorkspace(true);

  const pane = el('div', 'pane');
  // the static panes are marked up as tabpanels; panes built at runtime were
  // not, so most of the tablist pointed at nothing
  pane.setAttribute('role', 'tabpanel');
  pane.setAttribute('aria-label', name);
  pane.style.padding = '22px 26px';
  pane.append(renderPreview(payload));
  $('canvas').append(pane);

  const tab = makeTab(name, 'new', () => select(name));

  /* The same renderers again, into a small box. They size themselves from
     their container, so there is no separate thumbnail code path to keep in
     sync with the real one. */
  const thumb = el('button', 'thumb');
  thumb.type = 'button';
  const cap = el('div', 'cap');
  const capStat = el('span', null, stat || '');
  cap.append(el('b', null, name), capStat);
  const shot = el('div', 'shot');
  shot.append(renderPreview(payload));
  thumb.append(cap, shot);
  thumb.onclick = () => select(name);
  $('grid-all').append(thumb);

  panes[name] = { pane, tab, stat: capStat };
  const made = Object.keys(panes).length - 2;
  allCount.textContent = String(made);
  if (!document.body.classList.contains('ws-open')) {
    $('ws-count').textContent = String(made);
    $('ws-count').classList.remove('hidden');
  }
  select(name);
  setTimeout(() => tab.classList.remove('new'), 950);
}

/* --- what this run touched --- */
/* Scoped to the run, not the folder: a file the agent never opened is not part
   of the story being told. Keyed by name, because an agent revising its own
   deck writes the same file twice and a second chip for it is a lie about how
   many things it made. */
const touched = {};
/* Every product that lists changed files caps the list. Ours appended without
   a ceiling, so a long run would grow the strip until it pushed the canvas off
   screen. Measured: at 1440 the strip fits 5 chips per row, at 1280 it fits 4.
   8 is two rows, and the CSS bounds the strip to two rows independently so a
   long filename can never push it to three. */
const TOUCHED_MAX = 8;
let overflowChip = null;

function addTouched(name, stat) {
  $('touched-none').classList.add('hidden');
  let chip = touched[name];
  if (!chip) {
    if (Object.keys(touched).length >= TOUCHED_MAX) {
      if (!overflowChip) {
        overflowChip = el('span', 'more', '');
        $('touched').append(overflowChip);
      }
      touched[name] = null;                       // counted, not drawn
      overflowChip.textContent = `+${Object.keys(touched).length - TOUCHED_MAX} more`;
      return;
    }
    chip = el('button', 'chip');
    chip.type = 'button';
    chip.append(el('span', 'nm', name), el('span', 'add', ''));
    chip.onclick = () => panes[name] ? select(name) : openFile(name);
    $('touched').append(chip);
    touched[name] = chip;
  }
  if (!chip) return;                              // an overflowed file, rewritten
  chip.querySelector('.add').textContent = stat || '';
  chip.classList.remove('fresh');
  void chip.offsetWidth;           // restart the animation on a rewrite
  chip.classList.add('fresh');
  setTimeout(() => chip.classList.remove('fresh'), 950);
}

/* The runner already tells us how big the thing it made is, so showing it here
   beats leaving it buried in the arguments. */
function statFor(e) {
  const a = e.args || {};
  if (Array.isArray(a.rows)) return `+${a.rows.length} rows`;
  if (Array.isArray(a.slides)) return `+${a.slides.length} slides`;
  return '';
}

/* ------------------------------------------------------- the timeline --- */

const feed = $('timeline');
function push(cls) {
  const n = el('div', 'ev ' + (cls || ''));
  feed.append(n);
  autoscroll();
  return n;
}

/* Only auto-scroll when the viewport is already within 100px of the bottom.
   Before this, every event yanked the pane down, so you could not read back
   through a run while it was still going. Scroll up once and the feed leaves
   you alone until you return to the bottom yourself. */
const STICK_PX = 100;
function autoscroll() {
  const f = feed.parentElement;
  if (f.scrollHeight - f.scrollTop - f.clientHeight <= STICK_PX) {
    f.scrollTop = f.scrollHeight;
  }
}

/* The clock stops when the run does. It used to be a bare setInterval that was
   only cleared on finishRun, so a stream that ended without closing kept
   counting: a screenshot twenty minutes later read "1270s" for an 11-second
   run. A number that keeps moving after the thing it measures has stopped is
   worse than no number. */
const paintClock = () =>
  $('time-val').textContent = `${Math.round((Date.now() - S.t0) / 1000)}s`;
function startClock() {
  stopClock();
  S.t0 = Date.now();
  paintClock();
  S.timer = setInterval(paintClock, 250);
}
function stopClock() {
  if (S.timer) { clearInterval(S.timer); S.timer = null; }
  paintClock();                       // land on the true final value
}

function meters(c, budget) {
  const box = $('meter-calls');
  $('calls-val').textContent = `${c}/${budget}`;
  const r = budget ? c / budget : 0;
  $('calls-bar').style.transform = `scaleX(${r})`;
  // classList, not className: assigning the whole string used to drop the
  // layout classes the moment a run crossed a threshold
  box.classList.toggle('warn', r > 0.7 && r <= 0.9);
  box.classList.toggle('bad', r > 0.9);
}

/* Finding 7. The plan arrives once, as lines like "1. read_email - get the Q3
   numbers". Only the tool name is kept: the prose after it repeats what the
   timeline is about to say anyway, and this strip has to stay one or two rows
   tall beside the Steps only button. */
let planSteps = [];
let planCursor = -1;   // index of the furthest step reached so far
function drawPlan(content) {
  /* Idempotent: clear before drawing. Appending meant a second plan event
     duplicated the whole strip, and the harness can legitimately emit one
     again after a failure. A step already spent must never reappear. */
  $('plan').textContent = '';
  planCursor = -1;
  planSteps = String(content).split('\n').filter(Boolean).map((line) => {
    const m = line.match(/^\d+\.\s*(\S+)/);
    const node = el('span', 'step', m ? m[1] : clip(line, 28));
    node.title = line;
    $('plan').append(node);
    return { tool: m ? m[1] : null, node, done: false };
  });
  if (planSteps[0]) planSteps[0].node.classList.add('now');
}

/* The pointer only moves forward. A real run showed why: the model skipped
   step 3, completed 4 and 5, and "now" walked backwards onto the skipped step,
   so a finished plan pointed at something it had already moved past. A step
   the run overtook is not what happens next, it is a step that did not happen,
   so it goes quiet rather than reclaiming the cursor. */
function advancePlan(tool) {
  const i = planSteps.findIndex((s) => !s.done && s.tool === tool);
  if (i < 0) return;                       // an unplanned call: leave the plan alone
  planSteps[i].done = true;
  planSteps[i].node.classList.remove('now');
  planSteps[i].node.classList.add('done');
  if (i > planCursor) planCursor = i;
  for (const s of planSteps) s.node.classList.remove('now');
  const next = planSteps.find((s, j) => !s.done && j > planCursor);
  if (next) next.node.classList.add('now');
}

/* Nothing is "next" once the run is over. Without this the strip kept a live
   pointer on a finished run. */
function endPlan() {
  for (const s of planSteps) s.node.classList.remove('now');
}

/* --- events ------------------------------------------------------------ */

function onBanner(e) {
  resetRun();
  meters(0, e.budget);
  const n = push('act');
  n.append(el('div', 'banner-task', e.task));

  /* One line of facts, not a wall. This used to print five run chips followed
     by eight harness knobs, thirteen boxes stacked three rows deep above the
     first thing the model said. The run line keeps what changes between runs;
     the harness settings are fixed configuration and live behind the
     disclosure that was already there to explain them. */
  const p = e.profile;
  const facts = [e.model, `${e.budget} calls`, e.toolset];
  if (p) facts.push(p.label);
  if (e.root) facts.push(`folder: ${e.root}`);
  if (e.yolo) facts.push('confirmations off');
  if (e.tiers) facts.push(`tiers: ${Object.values(e.tiers.roles).join(', ')}`);
  n.append(el('div', 'banner-facts', facts.join('  ·  ')));

  if (p) {
    const det = el('details', 'harness-why');
    det.append(el('summary', null, 'harness settings'));
    const hz = el('div', 'harness-strip');
    const knob = (on, label) => el('span', 'knob' + (on ? ' on' : ' off'), label);
    hz.append(knob(p.plan, p.plan ? `plan ≤${p.plan_max_steps}` : 'no plan'),
              knob(p.verify_rounds > 0, p.verify_rounds ? `verify ×${p.verify_rounds}` : 'no verify'),
              knob(p.loop_break, p.loop_break ? 'loop-break' : 'loops ok'),
              knob(true, `out ≤${p.num_predict}`),
              knob(true, `ctx ${(p.num_ctx / 1024).toFixed(0)}k`),
              knob(true, `think ≤${p.think_streak_cap}`),
              knob(true, `mem ${p.memory_k}`));
    det.append(hz);
    if (p.rationale) det.append(el('div', 'note', p.rationale));
    det.append(el('div', 'note', `${e.today} · ${e.endpoint}`));
    n.append(det);
  }
  S.banner = n;
}

/* A disclosure that keeps the long text out of the flow but never out of
   reach. Two callers wanted the same thing with different bodies. */
function details(label, text, cls) {
  const det = el('details');
  det.append(el('summary', null, label));
  det.append(cls === 'note' ? el('div', 'note', text) : (() => {
    const pre = el('pre', 'raw');
    pre.textContent = text;
    return pre;
  })());
  return det;
}

/* The model speaks JSON, but its `thought` field is the only part a person
   wants. Pulling the field out of a half-written object means the sentence can
   stream as it is written, without the braces and quoting around it ever
   reaching the screen. */
const THOUGHT_RE = /"(?:thought|reasoning)"\s*:\s*"((?:[^"\\]|\\.)*)/;
function liveThought(raw) {
  const m = raw.match(THOUGHT_RE);
  if (!m) return null;
  // a fragment can end mid-escape, which is not parseable; drop the dangling
  // backslash and let the next token complete it
  const body = m[1].replace(/\\$/, '');
  try { return JSON.parse('"' + body + '"'); }
  catch (_) { return body.replace(/\\n/g, '\n').replace(/\\"/g, '"'); }
}

function onCallStart(e) {
  const n = push('');
  // Until a thought appears there is nothing worth reading, so the row says it
  // is working rather than showing an object being assembled.
  const body = el('div', 'thinking', 'Thinking');
  n.append(body);
  S.call = { node: n, body, text: '' };
  meters(e.call, e.budget);
}

function onToken(e) {
  if (!S.call) return;
  S.call.text += e.text;
  const t = liveThought(S.call.text);
  if (t) {
    S.call.body.className = 'think';
    S.call.body.textContent = t;
  }
  autoscroll();
}

/* Every path that ends a call has to land the row in a readable state, or it
   shimmers "Thinking" forever. This is the one place that does it. */
function settleCall(text, raw) {
  if (!S.call) return;
  S.call.body.className = text ? 'think' : 'think quiet';
  S.call.body.textContent = text || 'no reasoning given';
  if (raw) S.call.node.append(details('raw reply', raw));
  S.call.node.classList.add('settled');
  S.call = null;
}

function onCallEnd(e) {
  $('tok-val').textContent = (+$('tok-val').textContent + e.output_tokens);
  if (S.call) {
    S.call.node.append(el('div', 'when',
      `${(e.ms / 1000).toFixed(1)}s · ${e.output_tokens} tokens`));
  }
}

/* The parsed thought replaces the streamed one. They are usually identical, but
   the streamed version came out of a half-written object and the parsed one is
   authoritative. The JSON stays reachable as evidence, collapsed. */
function onModelReply(content) {
  if (!S.call) return;
  let obj = null;
  try { obj = JSON.parse(content); } catch (_) { /* the harness will repair it */ }
  const thought = obj && (obj.thought || obj.reasoning);
  settleCall(thought ? String(thought) : (obj ? '' : 'reply was not valid JSON'), content);
}

let doneSummary = null;

function onNote(e) {
  const k = e.kind;
  if (k === 'system') {
    if (S.banner) S.banner.append(details('the prompt the harness built', e.content));
    return;
  }
  if (k === 'task' || k === 'observation') return;   // shown by the banner / tool row
  /* The plan call has to settle its row too. It did not, so the row that
     produced the plan kept whatever the model had streamed into it: a raw
     {"steps": [...]} object sitting at the top of every run forever. The plan
     strip already shows the steps, so the row only reports that it planned. */
  if (k === 'plan') {
    drawPlan(e.content);
    const n = planSteps.length;
    settleCall(`Planned ${n} step${n === 1 ? '' : 's'}.`, e.content);
    return;
  }
  if (k === 'model') return onModelReply(e.content);

  if (k === 'repair') {
    const d = el('div', 'note');
    d.append(el('b', null, 'harness repaired the call'),
             document.createTextNode(' · ' + e.content));
    push('').append(d);
    return;
  }
  /* The harness correcting the model is the recovery half of a failure.
     Without it the timeline shows a tool failing and then, unexplained, the
     same tool working, which reads as luck rather than as a system. */
  if (k === 'feedback') {
    const d = el('div', 'note');
    d.append(el('b', null, 'harness → model'), document.createTextNode(' · ' + e.content));
    push('act').append(d);
    return;
  }
  if (k === 'verify') {
    let v = {};
    try { v = JSON.parse(e.content); } catch (_) { /* keep the raw text */ }
    const ok = v.complete !== false;
    const d = el('div', 'note');
    /* The verifier fails open so a broken one cannot trap the agent, but that
       makes a failure look exactly like a pass. When the harness marks the
       verdict unverified, say so rather than claiming the run checks out. */
    if (ok && v.unverified) {
      d.append(el('b', 'warn-tag', 'not verified'),
               document.createTextNode(' · ' + v.unverified));
      push('').append(d);
      return;
    }
    d.append(el('b', ok ? 'good-tag' : 'bad-tag',
                ok ? 'verified complete' : 'verifier: not done'));
    if (!ok) d.append(document.createTextNode(' · ' + (v.missing || e.content)));
    push(ok ? 'made' : 'bad').append(d);
    return;
  }
  /* Held, not drawn. The `done` note and the `end` event both carry a sentence
     about the same run, and rendering both produced two near-identical
     paragraphs in a row. They belong in one card. */
  if (k === 'done') doneSummary = e.content;
}

function onTool(e) {
  if (e.name === 'think') return;
  const mut = MUTATORS.has(e.name);
  /* A failed mutator used to get the green "made" dot, so a create_deck that
     wrote nothing looked exactly like one that worked. Failure outranks
     intent: the dot follows what happened, not what was attempted. */
  if (e.ok) advancePlan(e.name);   // a failed call has not completed its step
  /* has-tool is what "Steps only" filters on: this event carries an action,
     so it survives the strip. */
  const n = push((!e.ok ? 'bad' : mut ? 'made' : 'act') + ' has-tool');

  const row = el('div', 'tool' + (e.ok ? '' : ' err'));
  const arg = Object.values(e.args || {})[0];
  row.append(el('span', 'nm', e.name),
             el('span', 'arg', arg == null ? '' : clip(typeof arg === 'string' ? arg : JSON.stringify(arg), 90)),
             el('span', 'out', e.ok ? (mut ? 'written' : 'completed') : 'failed'));
  n.append(row);
  /* Why it failed is the whole point of showing the failure. */
  if (!e.ok) n.append(el('div', 'reason', clip(e.result, 600)));

  if (!e.ok) return;
  const key = TOUCH_ARG[e.name];
  const name = key && e.args ? e.args[key] : null;
  if (!name) return;
  const stat = statFor(e);
  addTouched(name, stat);
  if (ARTIFACT_ARG[e.name]) showArtifact(name, stat);
}

function onConfirm(e) {
  const n = push('act');
  const box = el('div', 'confirm-box');
  box.append(el('div', 'tag', `the agent wants to ${e.action}`),
             el('div', 'note', e.detail));
  const row = el('div', 'confirm-actions');
  const allow = el('button', 'allow', 'Allow');
  const deny = el('button', 'deny', 'Deny');
  const answer = (ok) => {
    post('/api/confirm', { id: e.id, allow: ok }).catch(() => {});
    box.classList.add('answered');
    row.textContent = '';
    row.append(el('div', 'note', ok ? 'you allowed it' : 'you declined it'));
  };
  allow.onclick = () => answer(true);
  deny.onclick = () => answer(false);
  row.append(allow, deny);
  box.append(row);
  n.append(box);
  autoscroll();
}

/* The run already emitted a summary twice — a `done` note and an `end` event —
   both rendered as ordinary rows in the same type as everything else, so the
   conclusion read as two more log lines. A run needs a full stop: one card,
   answering what it did and what it made. Bounded, not a dump. */
function onEnd(e) {
  stopClock();
  endPlan();
  // a call still open at the end would shimmer "Thinking" on a finished run
  settleCall('', S.call ? S.call.text : '');
  const n = push(e.finished ? 'made' : 'bad');
  const card = el('div', 'endcard' + (e.finished ? '' : ' cut'));

  /* "Budget" is vague: it reads as money or tokens. What actually ends a run
     is MAX_CALLS, a cap on model calls. Tokens are capped per-call by
     num_predict and bounded by num_ctx, but neither stops a run, so naming
     tokens here would describe a mechanism the harness does not have. */
  card.append(el('div', 'endhead', e.finished ? 'Run complete' : 'Out of model calls'));

  // what it did: the model's own sentence, not the harness's tally
  const say = doneSummary || e.summary;
  if (say) card.append(el('div', 'endsay', say));

  /* What it made. The timeline says a file was written and then scrolls away;
     this is the only place the outputs are listed together, and each one is
     the same click as its tab. */
  const made = Object.keys(panes).filter((k) => k !== 'all' && k !== 'ws');
  if (made.length) {
    const box = el('div', 'endmade');
    box.append(el('div', 'endlabel', 'produced'));
    for (const name of made) {
      const row = el('button', 'endfile');
      row.type = 'button';
      row.append(el('span', 'nm', name),
                 el('span', 'add', panes[name].stat ? panes[name].stat.textContent : ''));
      row.onclick = () => select(name);
      box.append(row);
    }
    card.append(box);
  }

  const stats = el('div', 'endstats');
  const stat = (v, l, bad) => {
    const d = el('div', bad ? 'bad-stat' : null);
    d.append(el('b', null, String(v)), el('span', null, l));
    return d;
  };
  const plural = (nn, word) => `${word}${nn === 1 ? '' : 's'}`;
  /* calls first, flagged red when they are what stopped the run, because the
     stat that ended the run should be the one the eye lands on */
  stats.append(stat(`${e.calls}/${e.budget}`, 'model calls', !e.finished),
               stat(e.output_tokens, 'tokens out'),
               stat(`${e.wall}s`, 'model time'),
               stat(e.actions.length, plural(e.actions.length, 'action')));
  if (e.tool_errors) {
    stats.append(stat(e.tool_errors, plural(e.tool_errors, 'tool error'), true));
  }
  const badReplies = e.parse_failures + e.invalid_calls;
  if (badReplies) stats.append(stat(badReplies, plural(badReplies, 'bad reply'), true));
  card.append(stats);

  /* Its own class, not .endlabel: that one uppercases, which turned a
     case-sensitive path into AGENTS/8B/LOGS/RUN_003.JSON. */
  if (e.log) {
    const f = el('div', 'endfoot');
    f.append(el('span', null, 'Transcript'), el('code', null, e.log));
    card.append(f);
  }
  n.append(card);
}

function onError(e) {
  const n = push('bad');
  const d = el('div', 'note');
  d.append(el('b', 'bad-tag', 'error'), document.createTextNode(' ' + e.message));
  n.append(d);
  if (e.trace) {
    const det = details('traceback', e.trace);
    det.className = 'trace';
    n.append(det);
  }
}

/* One place that knows everything a run accumulates. Anything added to that
   list later has to be cleared here too, which is why it is one function
   rather than scattered resets. Without it a second Run stacks on the first:
   the plan strip doubles, spent steps reappear, artifact tabs pile up. */
function resetRun() {
  feed.textContent = '';
  $('empty').classList.add('hidden');
  $('plan').textContent = '';
  planSteps = [];
  planCursor = -1;
  S.call = null;
  S.banner = null;
  doneSummary = null;
  $('tok-val').textContent = '0';
  startClock();

  for (const k of Object.keys(panes)) {
    if (k === 'all' || k === 'ws') continue;
    panes[k].pane.remove();
    panes[k].tab.remove();
    delete panes[k];
  }
  $('grid-all').textContent = '';
  $('grid-all').classList.add('hidden');
  $('holding').classList.remove('hidden');
  allCount.textContent = '0';
  $('ws-count').classList.add('hidden');
  select('all');

  for (const k of Object.keys(touched)) delete touched[k];
  if (overflowChip) { overflowChip.remove(); overflowChip = null; }
  $('touched').querySelectorAll('.chip').forEach((c) => c.remove());
  $('touched-none').classList.remove('hidden');
}

/* ---------------------------------------------------------------- run --- */

function handle(e) {
  switch (e.t) {
    case 'banner': return onBanner(e);
    case 'llm_start': return onCallStart(e);
    case 'token': return onToken(e);
    case 'llm_end': return onCallEnd(e);
    case 'note': return onNote(e);
    case 'tool': return onTool(e);
    case 'world': return renderTree({ ...S.ws, ...e, logs: (S.ws || {}).logs || [] });
    case 'confirm': return onConfirm(e);
    case 'end': return onEnd(e);
    case 'error': return onError(e);
    case 'stdout': return void console.log('[runner]', e.text);
    case 'closed': return finishRun();
  }
}

async function startRun() {
  if (!S.agent) return;
  const task = $('task').value.trim();
  if (!task) { $('task').focus(); return; }
  const body = {
    agent: S.agent, task,
    root: $('opt-root').value.trim(),
    shell: $('opt-shell').checked,
    yolo: $('opt-yolo').checked,
    with_office: $('opt-office').checked,
    tiers: $('opt-tiers').checked,
    max_calls: parseInt($('opt-calls').value, 10) || null,
    model: $('model').value || null,
    mcp: mcpSelected(),
    mcp_mode: $('opt-mcp-mode').value,
  };
  resetRun();
  let res;
  try {
    res = await post('/api/run', body);
  } catch (err) {
    return onError({ message: err.message });
  }
  S.run = res.run;
  S.seen = {};
  S.first = false;
  $('run').disabled = true;
  $('stop').classList.remove('hidden');
  ['meter-calls', 'meter-time', 'meter-tok'].forEach((id) => $(id).classList.remove('hidden'));

  S.es = new EventSource(`/api/events?run=${S.run}`);
  S.es.onmessage = (m) => handle(JSON.parse(m.data));
  S.es.onerror = () => { if (S.run) finishRun(); };
}

function finishRun() {
  if (S.es) { S.es.close(); S.es = null; }
  stopClock();
  S.run = null;
  S.call = null;
  $('run').disabled = false;
  $('stop').classList.add('hidden');
  loadAgents(true);
  loadWorkspace();
}

/* --------------------------------------------------------------- chrome -- */

/* An explicit choice, stored, beating the OS preference in both directions. No
   attribute at all means "follow the OS", which is the right default and is
   what a first-time visitor gets. */
const themeBtn = $('theme');
const isDark = () => {
  const set = document.documentElement.getAttribute('data-theme');
  return set ? set === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
};
const paintTheme = () => {
  // the drawn mark stays; only the label changes, and it names the action
  themeBtn.title = isDark() ? 'Switch to light' : 'Switch to dark';
  themeBtn.setAttribute('aria-label', themeBtn.title);
};
try {
  const saved = localStorage.getItem('agentlab-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
} catch (_) { /* storage blocked; the OS default still works */ }
themeBtn.onclick = () => {
  const next = isDark() ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('agentlab-theme', next); } catch (_) {}
  paintTheme();
};
// follow the OS while the user has not overridden it
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', paintTheme);
paintTheme();

/* Ratio, not pixels: a pixel width would mean the split silently changes
   meaning when the window resizes. Percent keeps the user's intent ("show me
   more of the run") true at any size. */
const splitter = $('splitter');
const MIN_PCT = 24, MAX_PCT = 68;

function setSplit(pct) {
  const v = Math.min(MAX_PCT, Math.max(MIN_PCT, pct));
  document.documentElement.style.setProperty('--run-pct', v + '%');
  splitter.setAttribute('aria-valuenow', Math.round(v));
  try { localStorage.setItem('agentlab-split', String(v)); } catch (_) {}
}
try {
  const saved = parseFloat(localStorage.getItem('agentlab-split'));
  if (!Number.isNaN(saved)) setSplit(saved);
} catch (_) {}

splitter.addEventListener('pointerdown', (ev) => {
  ev.preventDefault();
  splitter.setPointerCapture(ev.pointerId);   // keep tracking outside the 6px
  splitter.classList.add('dragging');
  document.body.classList.add('resizing');
  const rect = document.querySelector('.body').getBoundingClientRect();
  const move = (m) => setSplit(((m.clientX - rect.left) / rect.width) * 100);
  const up = () => {
    splitter.classList.remove('dragging');
    document.body.classList.remove('resizing');
    splitter.removeEventListener('pointermove', move);
    splitter.removeEventListener('pointerup', up);
    splitter.removeEventListener('pointercancel', up);
  };
  splitter.addEventListener('pointermove', move);
  splitter.addEventListener('pointerup', up);
  splitter.addEventListener('pointercancel', up);
});

/* A separator that only responds to a mouse is not a control. Arrows nudge,
   Home/End jump to the limits, and double-click resets to the default rather
   than leaving the user to hunt for it. */
splitter.addEventListener('keydown', (ev) => {
  const now = parseFloat(splitter.getAttribute('aria-valuenow'));
  const to = { ArrowLeft: now - 2, ArrowRight: now + 2,
               Home: MIN_PCT, End: MAX_PCT }[ev.key];
  if (to === undefined) return;
  ev.preventDefault();
  setSplit(to);
});
splitter.addEventListener('dblclick', () => setSplit(50));

/* --- run options --------------------------------------------------------- */
/* The popover floats over the transcript, so the feed has to know how tall the
   dock is or the last events sit underneath it unreachable. Measured rather
   than assumed, because the field grows with the task text. */
const dockEl = document.querySelector('.dock');
new ResizeObserver(([entry]) => {
  document.documentElement.style.setProperty('--dock-h', entry.contentRect.height + 'px');
}).observe(dockEl);

const optsBtn = $('opts-btn'), optsBox = $('opts');
function setOpts(open) {
  optsBox.hidden = !open;
  optsBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  if (open) optsBox.querySelector('input').focus();
}
optsBtn.onclick = (e) => { e.stopPropagation(); setOpts(optsBox.hidden); };
// click-away and Escape, because a popover you can only close with the button
// that opened it is a trap
document.addEventListener('click', (e) => {
  if (!optsBox.hidden && !optsBox.contains(e.target) && e.target !== optsBtn) setOpts(false);
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !optsBox.hidden) { setOpts(false); optsBtn.focus(); }
});

/* ----------------------------------------------- real accounts (mcp) --- */

/* The registry, fetched once — mcp/servers.json is static for the life of the
   process. Rows reuse .menu-row so a server reads as one more switch in the
   menu rather than a form bolted into it. */
async function loadMcp() {
  let servers;
  try {
    servers = await api('/api/mcp');
  } catch (err) {
    return;                       // no registry is not a reason to break the menu
  }
  const box = $('opt-mcp');
  box.textContent = '';
  for (const s of servers) {
    // Built as nodes, not markup: the setup text goes into a title attribute and
    // esc() only covers &<>, so a quote in servers.json would break out of it.
    const row = el('label', 'menu-row mcp-row');
    row.title = s.setup;
    const cb = el('input');
    cb.type = 'checkbox';
    cb.className = 'mcp-server';
    cb.value = s.name;
    const label = el('span', 'menu-label', s.name);
    label.append(el('em', null, s.summary));
    const tick = el('span', 'tick', '✓');
    tick.setAttribute('aria-hidden', 'true');
    row.append(cb, label, tick);
    box.append(row);
  }
  paintOptDots();
}

function mcpSelected() {
  return [...document.querySelectorAll('.mcp-server:checked')].map((el) => el.value);
}

/* The popover closes and takes any memory of what is switched on with it, so
   the count stays behind on the bar. */
const OPT_LABELS = { 'opt-shell': 'shell', 'opt-yolo': 'no confirm',
                     'opt-office': 'office', 'opt-tiers': 'tiers' };
function paintOptDots() {
  const on = Object.keys(OPT_LABELS).filter((id) => $(id).checked).map((id) => OPT_LABELS[id]);
  const root = $('opt-root').value.trim();
  const calls = $('opt-calls').value.trim();
  if (root) on.unshift('folder');
  if (calls) on.push(`${calls} calls`);
  /* Real accounts lead the summary. Everything else here changes how the agent
     works; this is the only one that decides whether it can touch live mail. */
  const conn = mcpSelected();
  const mode = $('opt-mcp-mode').value;
  if (conn.length) on.unshift(mode === 'live' ? `${conn.length} live` : `${conn.length} real`);
  $('conn-state').textContent = conn.length
    ? `${conn.length} · ${mode === 'read_only' ? 'read only' : mode}` : 'none';
  $('conn-state').classList.toggle('hot', conn.length > 0 && mode === 'live');
  $('opt-dots').textContent = on.join(' · ');
  /* The two rows that take a value show it on the row, so the menu still reads
     as set or unset once it is closed and reopened. */
  $('root-val').textContent = root ? root.replace(/^.*\//, '') || root : 'simulated';
  $('calls-set').textContent = calls || 'auto';
}
optsBox.addEventListener('input', paintOptDots);
optsBox.addEventListener('change', paintOptDots);

/* The field grows with the text instead of scrolling inside two fixed rows. */
const taskBox = $('task');
function growTask() {
  taskBox.style.height = 'auto';
  taskBox.style.height = Math.min(taskBox.scrollHeight, 180) + 'px';
}
taskBox.addEventListener('input', growTask);

/* Enter sends, Shift+Enter writes a newline, the way every chat box works.
   IME composition is exempt: mid-composition Enter commits the candidate word
   and must not also fire the run, which is how a Korean or Japanese task gets
   sent half-typed. */
taskBox.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
  e.preventDefault();
  if (!$('run').disabled) startRun();
});

/* --- the two side panels ------------------------------------------------- */
/* Both closed by default. The conversation is the product; a rail of models
   and a pane of files you have not made yet are furniture around it. */
function setWorkspace(open) {
  document.body.classList.toggle('ws-open', open);
  $('ws-btn').setAttribute('aria-pressed', open ? 'true' : 'false');
  if (open) $('ws-count').classList.add('hidden');
}
function setRail(open) {
  document.body.classList.toggle('rail-open', open);
  if (open) $('agent-filter').focus();
}
$('ws-btn').onclick = () => setWorkspace(!document.body.classList.contains('ws-open'));
$('rail-close').onclick = () => setRail(false);
$('model').addEventListener('change', (e) => {
  if (e.target.value !== MORE) return;
  setRail(true);
  syncModel();          // put the picker back on the model actually in use
});

/* Steps only. Pure presentation: nothing is dropped from the DOM, so toggling
   back mid-run loses nothing and the filter costs one class on <body>. */
const stepsToggle = $('steps-toggle');
stepsToggle.onchange = () => {
  document.body.classList.toggle('steps-only', stepsToggle.checked);
  autoscroll();
};

/* --------------------------------------------------------------- boot --- */

$('run').onclick = startRun;
$('stop').onclick = () => post('/api/stop').catch(() => {});
$('viewer-close').onclick = closeViewer;
$('viewer').onclick = (e) => { if (e.target === $('viewer')) closeViewer(); };
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeViewer();
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) startRun();
});

$('reveal').onclick = () => post('/api/reveal', { agent: S.agent }).catch((e) => alert(e.message));
$('reset').onclick = async () => {
  if (!S.agent) return;
  const a = S.agents.find((x) => x.id === S.agent);
  if (!confirm(`Factory-reset ${a.name}?\n\nThis clears its inbox and calendar back to the ` +
               `starting fixtures, deletes the files it created, and erases everything ` +
               `it has learned. Past run transcripts are kept.`)) return;
  await post('/api/reset', { agent: S.agent, what: ['world', 'memory', 'files'] });
  S.seen = {};
  S.first = true;
  await loadWorkspace();
  await loadAgents(true);
};

$('agent-filter').addEventListener('input', renderAgents);
paintOptDots();
growTask();

loadAgents();
loadMcp();
setInterval(() => { if (!S.run) loadAgents(true); }, 20000);

/* Registering the worker is what makes the browser offer "Install app". Nothing
   on the page needs it, so a failure is silent — an old browser, or the
   pywebview window, still works normally. */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
