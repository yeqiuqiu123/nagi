'use strict';
// Nagi glance panel: renders the view model, draws the trunk, branches and silence
// strokes, runs the gated open motion and the settings sheet. Read-only.
(() => {
  const M = window.NagiModel;
  const $ = (id) => document.getElementById(id);
  const SVGNS = 'http://www.w3.org/2000/svg';
  const MAX_H = 690;
  const MIN_H = 320;
  const POLL_MS = 20000;
  const LAST_OPEN = 'nagi-last-open';
  const R = 10; // branch elbow radius
  const Motion = window.NagiMotion;
  const reduced = Motion.reduced;
  const panel = $('panel'); const scroll = $('scroll'); const inner = $('scroll-inner');
  const nowline = $('nowline'); const sheetLayer = $('sheet-layer');

  let readerFailedAt = null;
  let firstRender = true; let opening = false; const endedOpenBy = new Map(); let lastSilence = new Map();
  let envelope = null; let view = null;
  let running = []; let sheet = null;
  let lastOpen = null;
  try { const v = Number(localStorage.getItem(LAST_OPEN)); if (Number.isFinite(v) && v > 0) lastOpen = v; } catch {}

  const native = (message) => { try { window.webkit.messageHandlers.nagiPanel.postMessage(message); } catch {} };

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
    return el;
  }
  const sep = () => h('span', { class: 'sep', text: ' · ' });
  const svg = (tag, attrs) => { const el = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v); return el; };

  // ---- Rendering --------------------------------------------------------
  function renderLimits(vm) {
    const list = $('limits');
    // Every line reads name, % left, date; an account with several windows heads its own lines.
    const pct = (l) => (l.pct == null ? (l.head ? '' : '—') : null);
    const cells = (l) => [
      h('span', { class: 'lim-name', text: l.name }),
      pct(l) != null ? h('span', { class: 'lim-pct', text: pct(l) })
        : h('span', { class: 'lim-pct' }, h('b', { text: l.empty ? 'empty' : l.pct + '%' }), l.empty ? null : ' left'),
      // A date stamp never breaks mid-phrase.
      h('span', { class: 'lim-date' }, l.date, l.stamp ? h('span', { class: 'nowrap', text: (l.date ? ' · ' : '') + l.stamp }) : null)];
    const lines = (items, note) => [...items.flatMap((l) => [
      h('li', { class: 'lim' + (l.head ? ' head' : '') + (l.pct == null && !l.head ? ' none' : '') + (l.empty ? ' empty' : ''), 'data-node': 'limit', 'aria-label': l.label }, cells(l)),
      ...l.subs.map((s) => h('li', { class: 'lim sub' + (s.empty ? ' empty' : ''), 'aria-label': s.label }, cells(s)))]),
    ...(note ? [h('li', { class: 'lim-note', text: note })] : [])];
    // Several sources: each source's own account lines under its own name, never merged.
    list.replaceChildren(...(vm.limitGroups ? vm.limitGroups.flatMap((g) => [h('li', { class: 'lim-source', text: g.label }), ...lines(g.lines, g.note)])
      : lines(vm.limits, vm.limitNote)));
  }

  function renderHero(vm) {
    const hero = vm.hero;
    const left = h('div', { class: 'hero-left' }, h('span', { class: 'num' + (hero.quiet ? ' quiet' : ''), text: hero.num }), hero.word && h('span', { class: 'run-word', text: hero.word }), h('span', { class: 'bl', 'aria-hidden': 'true' }));
    const right = h('div', { class: 'hero-right' });
    if (hero.time) right.append(h('span', { class: 'hero-time', text: hero.time }));
    if (hero.alert) right.append(h('span', { class: 'hero-alert' + (hero.calm ? ' calm' : ''), text: hero.alert }));
    if (hero.words.length) {
      const words = h('span', { class: 'hero-words' });
      hero.words.forEach((w, i) => { if (i) words.append(sep()); words.append(h('span', { class: 'hero-word ' + w.cls, 'data-target': w.target, text: w.text })); });
      right.append(words);
    }
    hero.subs.forEach((s) => right.append(h('span', { class: 'hero-sub', text: s })));
    const box = $('hero');
    box.replaceChildren(left, right);
    box.classList.toggle('dim', hero.dim);
    $('now').setAttribute('aria-label', vm.heroLabel);
    $('now').setAttribute('role', 'status');
  }

  function rowEl(r, project) {
    const depth = Math.min(r.depth, 3);
    const cls = 'row ' + r.kind + (r.asks ? ' is-asks' : '') + (r.stuck ? ' is-stuck' : '') + (r.isNew ? ' is-new' : '') + (r.pending ? ' is-pending' : '');
    const meta = h('span', { class: 'meta' });
    if (r.stateWord) meta.append(h('span', { class: 'state ' + r.stateWord.cls, text: r.stateWord.text }), sep());
    // The model word carries its provider's brand colour; the rest of the meta stays neutral.
    r.meta.forEach((m, i) => { if (i) meta.append(sep()); meta.append(i === 0 ? h('span', { class: 'model' + (r.provider ? ' pv-' + r.provider : ''), text: m }) : m); });
    const link = h('a', { class: cls, href: r.href || null, 'data-provider': r.provider || null, 'data-key': 'row:' + r.id, 'data-id': r.id, 'data-start': r.started || 0, 'aria-label': r.label },
      h('span', { class: 'node', 'aria-hidden': 'true' }),
      h('span', { class: 'title' }, r.prefix && h('span', { class: 'prefix', text: r.prefix }), r.prefix && ' ', r.rest,
        r.kind === 'parent' && h('span', { class: 'fold-tail', text: ' · ' + r.meta[r.meta.length - 1] })),
      meta);
    if (r.silence) {
      const lull = h('span', { class: 'lull ' + r.silence.cls + (r.silence.f >= 0.5 ? ' late' : ''), 'aria-hidden': 'true', 'data-f': r.silence.f });
      lull.style.transform = 'scaleX(' + r.silence.f.toFixed(3) + ')';
      link.append(lull);
    }
    return h('li', { class: 'item d' + depth }, link,
      r.children.length > 0 && h('ul', { class: 'kids' }, r.children.map((c) => rowEl(c, project))));
  }

  // T3's project icon sits on the trunk in place of the project node. It is decorative; the
  // heading text stays the label. Favicons come from owner-authenticated fetches as blob: URLs.
  const favicons = new Map(); // key → object URL, null (no favicon) or 'pending'
  function projectIcon(icon) {
    const I = window.NagiIcons;
    const fallback = () => I.monogram(icon.fallback.monogram, icon.fallback.color);
    let el;
    if (icon.kind === 'monogram') el = I.monogram(icon.text, icon.color);
    else if (icon.kind === 'emoji') el = I.emoji(icon.emoji);
    else if (icon.kind === 'lucide') el = I.lucide(icon.name, icon.color);
    else if (icon.kind === 'favicon' && /^[0-9a-f]{32}$/.test(icon.key)) {
      const known = favicons.get(icon.key);
      if (typeof known === 'string' && known !== 'pending') el = I.image(known);
      else if (known === null) el = fallback();
      else {
        el = h('span', { class: 'pi pi-pending' });
        if (known !== 'pending') loadFavicon(icon.key);
      }
      el.dataset.iconKey = icon.key;
    } else el = fallback();
    el.setAttribute('aria-hidden', 'true');
    el.dataset.fallback = JSON.stringify(icon.fallback);
    return el;
  }
  async function loadFavicon(key) {
    favicons.set(key, 'pending');
    let url = null;
    try {
      const response = await fetch('/api/project-icon/' + key, { cache: 'no-store' });
      if (response.ok) {
        const blob = await response.blob();
        if (blob.size && /^image\/(png|jpeg|webp|gif|x-icon|svg\+xml)$/.test(blob.type)) url = URL.createObjectURL(blob);
      }
    } catch {}
    favicons.set(key, url);
    // Swap every waiting badge for this project in place; a broken image falls back too.
    document.querySelectorAll(`.pi[data-icon-key="${key}"]`).forEach((old) => {
      const fallback = JSON.parse(old.dataset.fallback);
      const next = url ? window.NagiIcons.image(url) : window.NagiIcons.monogram(fallback.monogram, fallback.color);
      next.dataset.iconKey = key; next.dataset.fallback = old.dataset.fallback; next.setAttribute('aria-hidden', 'true');
      const img = next.querySelector('img');
      if (img) img.addEventListener('error', () => { favicons.set(key, null); next.replaceWith(Object.assign(window.NagiIcons.monogram(fallback.monogram, fallback.color), { ariaHidden: 'true' })); }, { once: true });
      old.replaceWith(next);
    });
  }

  function projectList(vm) {
    const kids = [];
    if (vm.projects.length) {
      kids.push(h('ul', { class: 'projects', 'aria-label': 'Agents by project' }, vm.projects.map((p) => h('li', { class: 'project' },
        h('div', { class: 'proj-head', 'data-node': 'project' }, projectIcon(p.icon), h('span', { class: 'proj-name', text: p.title })),
        h('ul', { class: 'agents' }, p.rows.map((r) => rowEl(r, p.title)))))));
    }
    if (vm.omitted) kids.push(h('p', { class: 'note', text: vm.omitted }));
    if (vm.message) kids.push(h('p', { class: 'message', 'data-node': 'anchor', text: vm.message }));
    return kids;
  }

  function renderPast(vm, view) {
    const past = $('past');
    if (!view || view.kind !== 'multi') {
      const kids = projectList(vm);
      if (view && view.kind === 'empty') kids.push(h('p', { class: 'setup-call' }, h('button', { class: 'btn default', type: 'button', id: 'start-setup', text: 'Set up Nagi' })));
      past.replaceChildren(...kids);
      const start = $('start-setup');
      if (start) start.addEventListener('click', (event) => openSetup({ instant: event.detail === 0 }));
      return;
    }
    // Several sources: harness → computer → projects, each source with its own truth and Ended line.
    past.replaceChildren(...vm.groups.map((g) => h('section', { class: 'source-group', 'aria-label': g.name },
      view.showHarness && h('div', { class: 'src-head', 'data-node': 'source' }, harnessIcon(g.harness, g.name), h('span', { class: 'src-name', text: g.name })),
      g.sources.map((src) => h('div', { class: 'source', 'data-source': src.id, 'aria-label': g.name + ', ' + src.label },
        view.showComputer && h('div', { class: 'computer-head', 'data-node': 'computer' }, h('span', { class: 'computer-name', text: src.label })),
        src.state && h('p', { class: 'source-state', 'data-node': 'anchor', text: src.state }),
        projectList({ ...src.vm, message: src.vm.mode === 'live' ? src.vm.message : '' }),
        src.vm.ended && endedBlock(src.vm.ended, 'src:' + src.id))))));
  }

  function harnessIcon(id, name) {
    const identity = M.projectIdentity(name);
    const el = window.NagiIcons.monogram(identity.monogram, identity.color);
    el.setAttribute('aria-hidden', 'true');
    return el;
  }

  function renderEnded(vm, view) {
    const box = $('ended');
    const e = view && view.kind === 'multi' ? null : vm.ended;
    box.hidden = !e;
    if (!e) { box.replaceChildren(); return; }
    box.replaceChildren(...endedBlock(e, 'single').childNodes);
  }

  // One Ended line and its list; each source keeps its own, opened independently.
  function endedBlock(e, key) {
    const listId = key === 'single' ? 'ended-list' : 'ended-list-' + key.replace(/[^a-z0-9]/gi, '');
    let endedOpen = !!endedOpenBy.get(key);
    // The visible line is the button's name (WCAG 2.5.3); the split and the open state are its
    // description and aria-expanded, so speech control can say what it sees.
    const descId = listId + '-desc';
    const button = h('button', { class: 'ended-btn', type: 'button', 'data-key': key === 'single' ? 'ended' : 'ended:' + key, 'aria-expanded': String(endedOpen), 'aria-controls': listId,
      'aria-describedby': descId },
      h('span', { class: 'ended-line' }, h('b', { text: String(e.count) }), ' ended since ' + e.since,
        (() => { const s = svg('svg', { class: 'chev', viewBox: '0 0 12 12', 'aria-hidden': 'true' }); s.append(svg('path', { d: 'M4.5 2.5 8 6l-3.5 3.5' })); return s; })()),
      // Lines break only between project names, never inside one.
      h('span', { class: 'ended-split' }, e.projects.split(', ').flatMap((name, i) => [i ? ', ' : null, h('span', { class: 'nowrap', text: name })])));
    // Outside the button, so it is the description only and never part of the name.
    const desc = h('span', { class: 'sr', id: descId, text: e.split + '.' });
    // Expanded: project groups read as headings, failed and stopped threads as rows under them.
    const list = h('ul', { class: 'ended-list', id: listId, hidden: !endedOpen },
      h('li', { class: 'eg-total', text: e.split }),
      e.groups.map((g) => h('li', { class: 'eg-group' },
        h('div', { class: 'eg' }, projectIcon(g.icon), h('span', { class: 'eg-name', text: g.title }), h('span', { class: 'eg-meta', text: g.summary })),
        g.problems.length > 0 && h('ul', { class: 'problems' }, g.problems.map((p, i) => h('li', {},
          h('a', { class: 'problem', href: p.href || null, 'data-key': 'problem:' + g.id + ':' + i, 'aria-label': p.title + '. ' + p.meta + '.' + (p.href ? ' Opens in T3 Code.' : '') },
            h('span', { class: 'node', 'aria-hidden': 'true' }), h('span', { class: 'title', text: p.title }),
            h('span', { class: 'meta' }, h('span', { class: 'model' + (p.provider ? ' pv-' + p.provider : ''), text: p.model }), sep(), p.when))))))));
    button.addEventListener('click', () => {
      endedOpen = !endedOpen; endedOpenBy.set(key, endedOpen);
      button.setAttribute('aria-expanded', String(endedOpen));
      list.hidden = !endedOpen;
      layout();
      // The list scrolls in under the pinned line with an inset, so no line is cut.
      if (endedOpen) reveal(button, button);
    });
    return h('div', { class: 'ended' }, button, desc, list);
  }

  // ---- Layout and geometry -----------------------------------------------
  function rel(el, box) {
    const r = el.getBoundingClientRect();
    return { x: r.left - box.left + r.width / 2, y: r.top - box.top + r.height / 2, top: r.top - box.top, bottom: r.bottom - box.top };
  }

  function placeNowLine() {
    const now = $('now');
    now.style.height = '';
    const nb = now.getBoundingClientRect();
    const y = Math.round(now.querySelector('.bl').getBoundingClientRect().top - nb.top + 6);
    nowline.style.top = y + 'px';
    now.style.height = (y + 1) + 'px';
    // Keep the right-hand words clear of the line whatever the numeral's metrics are.
    const right = now.querySelector('.hero-right');
    right.style.transform = '';
    const over = right.getBoundingClientRect().bottom - nb.top - (y - 5);
    if (over > 0) right.style.transform = 'translateY(' + (-over) + 'px)';
  }

  function drawTop() {
    const geo = $('geo-top'); const pinned = $('pinned');
    const box = pinned.getBoundingClientRect();
    geo.setAttribute('width', box.width); geo.setAttribute('height', box.height);
    geo.replaceChildren();
    const tx = parseFloat(getComputedStyle(panel).getPropertyValue('--trunk-x'));
    const nowY = rel(nowline, box).y;
    const lims = [...document.querySelectorAll('#limits [data-node="limit"]')];
    if (lims.length) {
      const first = rel(lims[0].querySelector('.lim-name'), box).y;
      geo.append(svg('path', { class: 'trunk', d: `M${tx} ${first} V${nowY}` }));
      lims.forEach((li) => geo.append(svg('circle', { class: 'n-limit' + (li.classList.contains('empty') ? ' empty' : ''), cx: tx, cy: rel(li.querySelector('.lim-name'), box).y, r: 4 })));
    }
  }

  function drawPast() {
    const geo = $('geo-past');
    const box = inner.getBoundingClientRect();
    geo.setAttribute('width', box.width); geo.setAttribute('height', inner.scrollHeight);
    geo.replaceChildren();
    const tx = parseFloat(getComputedStyle(panel).getPropertyValue('--trunk-x'));
    const heads = [...document.querySelectorAll('#past [data-node="project"] .proj-name')];
    // The trunk runs to the last Ended line, truth line or heading, whichever is lowest.
    const ends = [...inner.querySelectorAll('.ended:not([hidden]) .ended-line, [data-node="anchor"], [data-node="source"] .src-name, [data-node="computer"] .computer-name')];
    const endLine = !$('ended').hidden ? $('ended').querySelector('.ended-line') : null;
    const lows = [...ends, ...heads].map((el) => rel(el, box).y);
    const lastY = lows.length ? Math.max(...lows) : null;
    if (lastY == null) return;
    // An expanded Ended list keeps the trunk running down past its project headings.
    const groups = [...document.querySelectorAll('.ended-list:not([hidden]) .eg-name')];
    const trunkEnd = Math.max(lastY, ...groups.map((el) => rel(el, box).y));
    geo.append(svg('path', { class: 'trunk', d: `M${tx} 0 V${trunkEnd}` }));
    groups.forEach((el) => { if (!el.parentElement.querySelector('.pi')) geo.append(svg('circle', { class: 'n-group', cx: tx, cy: rel(el, box).y, r: 3 })); });
    // Each failed or stopped thread hangs from its project's stem on a node, never a bare indent.
    document.querySelectorAll('.ended-list:not([hidden]) .eg-group').forEach((group) => {
      const gy = rel(group.querySelector('.eg-name'), box).y;
      group.querySelectorAll('.problem .node').forEach((el) => {
        const n = rel(el, box);
        geo.append(svg('path', { class: 'branch', d: `M${tx} ${gy} V${n.y - R} Q${tx} ${n.y} ${tx + R} ${n.y} H${n.x - 4.5}` }));
        geo.append(svg('circle', { class: 'n-ended', cx: n.x, cy: n.y, r: 4 }));
      });
    });
    // A project's T3 icon stands in for its node on the trunk.
    heads.forEach((el) => { if (!el.parentElement.querySelector('.pi')) geo.append(svg('circle', { class: 'n-project', cx: tx, cy: rel(el, box).y, r: 4.5 })); });
    if (endLine) geo.append(svg('circle', { class: 'n-ended', cx: tx, cy: rel(endLine, box).y, r: 4 }));
    // Each source's Ended line, and each computer, sits on the trunk as a ring.
    inner.querySelectorAll('.source .ended-line').forEach((el) => geo.append(svg('circle', { class: 'n-ended', cx: tx, cy: rel(el, box).y, r: 4 })));
    inner.querySelectorAll('[data-node="computer"] .computer-name').forEach((el) => geo.append(svg('circle', { class: 'n-group', cx: tx, cy: rel(el, box).y, r: 3 })));
    const branches = [];
    const node = (item) => rel(item.querySelector(':scope > .row .node'), box);
    document.querySelectorAll('#past .project').forEach((proj) => {
      const py = rel(proj.querySelector('.proj-name'), box).y;
      proj.querySelectorAll(':scope > .agents > .item').forEach((item) => {
        const n = node(item);
        branches.push({ item, d: `M${tx} ${py} V${n.y - R} Q${tx} ${n.y} ${tx + R} ${n.y} H${n.x - 5.5}` });
      });
    });
    document.querySelectorAll('#past .kids').forEach((ul) => {
      const p = node(ul.parentElement);
      [...ul.children].forEach((item) => {
        const n = node(item);
        const d = n.x - p.x < R + 6 ? `M${p.x} ${p.y + 5.5} V${n.y - 5.5}`
          : `M${p.x} ${p.y + 5.5} V${n.y - R} Q${p.x} ${n.y} ${p.x + R} ${n.y} H${n.x - 5.5}`;
        branches.push({ item, d });
      });
    });
    branches.forEach((b) => {
      const row = b.item.querySelector(':scope > .row');
      const path = svg('path', { class: 'branch', d: b.d, 'data-start': row.dataset.start });
      if (row.classList.contains('is-new')) path.dataset.new = '1';
      geo.append(path);
    });
    document.querySelectorAll('#past .row .node').forEach((el) => {
      const a = rel(el, box); const row = el.parentElement;
      const parent = row.classList.contains('parent');
      // Solid title dots are running rows only; queued or starting rows get a small ring.
      const pending = row.classList.contains('is-pending');
      // The node keeps its state shape (solid running, ring otherwise) in the provider's colour;
      // asks you stays rose, the one colour reserved for it.
      const asks = row.classList.contains('is-asks');
      const tone = !asks && row.dataset.provider ? ' pv-' + row.dataset.provider : '';
      const c = svg('circle', { class: (parent ? 'n-parent' : asks ? 'n-asks' : pending ? 'n-pending' : 'n-running') + tone, cx: a.x, cy: a.y, r: parent ? 4.5 : pending ? 3.5 : 5 });
      c.dataset.key = row.dataset.key;
      geo.append(c);
    });
  }

  function natural() { return $('pinned').offsetHeight + inner.offsetHeight; }

  // Scroll so `top` sits INSET px under the rose line while `target` stays fully in view.
  const INSET = 10; // the gap the list has under the rose line at rest
  function reveal(top, target) {
    const view = scroll.getBoundingClientRect();
    const y = (el) => el.getBoundingClientRect().top - view.top + scroll.scrollTop;
    const want = y(top) - INSET;
    const bottom = y(target) + target.getBoundingClientRect().height + INSET - scroll.clientHeight;
    scroll.scrollTop = Math.min(Math.max(want, bottom), y(target) - INSET);
  }

  function syncHeroWords() {
    const overflow = scroll.scrollHeight > scroll.clientHeight + 1;
    const view = scroll.getBoundingClientRect();
    document.querySelectorAll('#hero .hero-word').forEach((word) => {
      const row = document.querySelector('#past .row.is-' + word.dataset.target);
      let out = false;
      if (overflow && row) { const r = row.getBoundingClientRect(); out = r.top < view.top || r.bottom > view.bottom; }
      const isButton = word.tagName === 'BUTTON';
      if (out === isButton) return;
      const next = out ? h('button', { type: 'button', class: word.className, 'data-target': word.dataset.target, 'data-key': 'word:' + word.dataset.target, text: word.textContent })
        : h('span', { class: word.className, 'data-target': word.dataset.target, text: word.textContent });
      if (out) next.addEventListener('click', () => {
        // Keep the project heading (and so the parent) in view above the row.
        reveal(row.closest('.project').querySelector('.proj-head'), row);
        row.focus({ preventScroll: true });
      });
      word.replaceWith(next);
    });
  }

  function layout() {
    placeNowLine();
    panel.classList.remove('fold');
    // The overflow rule is about the running rows; an expanded Ended list never folds them.
    const open = [...document.querySelectorAll('.ended-list:not([hidden])')].reduce((n, el) => n + el.offsetHeight, 0);
    if (natural() - open > MAX_H) panel.classList.add('fold');
    drawTop();
    drawPast();
    syncHeroWords();
    // Two spare px absorb the rounding between window and CSS pixels at fractional text scales.
    native('height:' + Math.max(MIN_H, Math.min(MAX_H, Math.ceil(natural()) + 2)));
  }

  // When an agent speaks again while the panel is open, its stroke clears.
  function clearSilences() {
    const next = new Map();
    document.querySelectorAll('#past a.row.running').forEach((row) => {
      const lull = row.querySelector('.lull');
      const f = lull ? Number(lull.dataset.f) : 0;
      next.set(row.dataset.id, f);
      const before = lastSilence.get(row.dataset.id);
      if (before != null && before >= 1 / 3 && f < 1 / 3) Motion.clearSilence(row, lull, before);
    });
    lastSilence = next;
  }

  // ---- Data -----------------------------------------------------------------
  async function getJson(path) {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw Object.assign(new Error('HTTP ' + response.status), { status: response.status });
    return response.json();
  }

  function render() {
    const opened = Date.now();
    // An open is the first render, or a native reopen of the already-loaded page (Mac).
    const isOpen = firstRender || opening;
    view = M.buildSources(envelope, { now: opened, lastOpen: isOpen ? lastOpen : null, reduced: reduced(), readerDownAt: readerFailedAt });
    const vm = view.vm;
    const active = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key : null;
    const top = scroll.scrollTop;
    renderLimits(vm); renderHero(vm); renderPast(vm, view); renderEnded(vm, view);
    panel.dataset.state = vm.mode;
    layout();
    if (isOpen) scroll.scrollTop = 0; else scroll.scrollTop = top;
    if (active) { const el = document.querySelector(`[data-key="${CSS.escape(active)}"]`); if (el) el.focus({ preventScroll: true }); }
    if (isOpen) {
      Motion.playOpen({ vm, opened, lastOpen, nowline, scroll, geo: $('geo-past'), rows: [...document.querySelectorAll('#past a.row.is-new')] });
      if (vm.mode === 'live') { lastOpen = opened; try { localStorage.setItem(LAST_OPEN, String(opened)); } catch {} }
      opening = false;
    }
    if (firstRender) {
      firstRender = false;
      native('ready');
      // Nothing connected yet: the setup opens by itself, once per page.
      if (view.kind === 'empty' && !readerFailedAt) openSetup({ instant: true });
    }
    clearSilences();
  }

  async function refresh() {
    // One envelope carries every source's agents and limits (API v1).
    let failure = null;
    try { envelope = await getJson('/api/sources/v1/glance'); readerFailedAt = null; }
    catch (error) { failure = error; readerFailedAt = Date.now(); } // a failed read dates what was shown
    if (firstRender && failure && failure.status === 401) return; // native recovery reopens the panel
    if (firstRender) await document.fonts.ready;
    render();
  }

  // ---- Setup and Sources (loaded on demand: most opens never need them) -------------------
  let setupModule = null;
  function loadSetup() {
    if (!setupModule) {
      setupModule = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/nagi-setup.js';
        script.onload = () => (window.NagiSetup ? resolve(window.NagiSetup) : reject(new Error('setup')));
        script.onerror = () => { setupModule = null; reject(new Error('setup')); };
        document.head.append(script);
      });
    }
    return setupModule;
  }
  const setupHost = { refresh: () => refresh(), native, opener: () => $('gear'), sources: () => envelope };
  function openSetup(options) { loadSetup().then((S) => S.open(setupHost, options || {})).catch(() => {}); }
  function openSources(options) { loadSetup().then((S) => S.openSources(setupHost, options || {})).catch(() => {}); }

  // ---- Settings sheet -----------------------------------------------------------
  const FIELDS = [
    { key: 'stuckMinutes', input: 'stuck-minutes', note: 'stuck-clamped', min: 5, max: 120 },
    { key: 'endedExpiryHours', input: 'ended-hours', note: 'ended-clamped', min: 1, max: 168 },
    // Unticked means "off"; the number keeps its value so ticking it again restores it.
    { key: 'limitAlertPercent', input: 'alert-percent', note: 'alert-clamped', min: 1, max: 50, toggle: 'alert-on' },
  ];
  const DEFAULTS = { stuckMinutes: 15, endedExpiryHours: 24, limitAlertPercent: 10 };

  const isOff = (f) => f.toggle && !$(f.toggle).checked;
  function fieldValue(f) { if (isOff(f)) return 'off'; const r = M.clampSetting(f.key, $(f.input).value); return r.invalid ? NaN : r.value; }
  function clampField(f) {
    if (isOff(f)) { $(f.note).hidden = true; syncSave(); return 'off'; }
    const loaded = sheet.loaded[f.key];
    const r = M.clampSetting(f.key, $(f.input).value, loaded === 'off' ? undefined : loaded);
    const note = $(f.note);
    $(f.input).value = String(r.value);
    note.hidden = !r.clamped;
    if (r.clamped) note.textContent = 'Set to ' + r.value + ', the nearest allowed value.';
    syncSave();
    return r.value;
  }
  function syncSave() {
    $('save').disabled = !sheet || FIELDS.every((f) => fieldValue(f) === sheet.loaded[f.key]);
  }
  function fill(values) {
    FIELDS.forEach((f) => {
      const value = values[f.key] == null ? DEFAULTS[f.key] : values[f.key];
      if (f.toggle) {
        const on = value !== 'off';
        $(f.toggle).checked = on;
        $(f.input).disabled = !on;
        if (on || !$(f.input).value) $(f.input).value = String(on ? value : DEFAULTS[f.key]);
      } else $(f.input).value = String(value);
      $(f.note).hidden = true;
    });
    syncSave();
  }

  // Keyboard, Return, Esc and the tray open and close the sheet on the next frame (motion
  // rule 1); only a pointer click on the gear, Cancel or the scrim gets the short transition.
  function instant(on) { sheetLayer.classList.toggle('instant', !!on); }
  async function openSettings(options) {
    if (sheet) return;
    instant(!options || options.instant !== false);
    sheet = { loaded: { ...((envelope && envelope.settings) || DEFAULTS) }, defaults: DEFAULTS, opener: document.activeElement };
    $('sheet-error').hidden = true;
    fill(sheet.loaded);
    sheetLayer.hidden = false;
    void sheetLayer.offsetHeight; // start the transition from the closed state
    sheetLayer.dataset.open = 'true';
    panel.querySelectorAll('.pinned, .scroll').forEach((el) => { el.inert = true; });
    $('stuck-minutes').focus({ preventScroll: true });
    try {
      const value = await getJson('/api/settings');
      if (!sheet) return;
      sheet.loaded = { ...value.settings }; sheet.defaults = { ...value.defaults };
      fill(sheet.loaded);
      if ((value.warnings || []).includes('settings_invalid')) showError("Settings were reset to the defaults because the saved file couldn't be read.");
    } catch {}
  }
  function showError(text) { const e = $('sheet-error'); e.textContent = text; e.hidden = false; }
  function closeSettings(options) {
    if (!sheet) return;
    instant(!options || options.instant !== false);
    const opener = sheet.opener; sheet = null;
    sheetLayer.dataset.open = 'false';
    panel.querySelectorAll('.pinned, .scroll').forEach((el) => { el.inert = false; });
    const done = () => { if (!sheet) sheetLayer.hidden = true; };
    if (reduced() || sheetLayer.classList.contains('instant')) done(); else setTimeout(done, 200);
    const back = opener && opener.isConnected ? opener : $('gear');
    back.focus({ preventScroll: true });
  }
  async function saveSettings() {
    if (!sheet || $('save').disabled) return;
    const body = {}; FIELDS.forEach((f) => { body[f.key] = clampField(f); });
    $('save').disabled = true;
    try {
      const response = await fetch('/api/settings', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-Progress-Desk': '1' }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const saved = await response.json();
      if (envelope) envelope.settings = { ...saved.settings };
      closeSettings();
      refresh();
    } catch {
      showError("Couldn't save. Your settings are unchanged.");
      syncSave();
    }
  }

  function wireSheet() {
    // event.detail is 0 for a keyboard-fired click.
    $('gear').addEventListener('click', (event) => openSettings({ instant: event.detail === 0 }));
    $('cancel').addEventListener('click', (event) => closeSettings({ instant: event.detail === 0 }));
    $('restore').addEventListener('click', () => { if (sheet) fill(sheet.defaults); });
    // Settings → Sources: the settings sheet steps aside for the Sources sheet.
    $('manage-sources').addEventListener('click', (event) => { closeSettings({ instant: true }); openSources({ instant: event.detail === 0 }); });
    $('sheet').addEventListener('submit', (event) => { event.preventDefault(); saveSettings(); });
    sheetLayer.querySelector('.scrim').addEventListener('click', () => closeSettings({ instant: false }));
    FIELDS.forEach((f) => {
      const input = $(f.input);
      if (f.toggle) $(f.toggle).addEventListener('change', () => { input.disabled = !$(f.toggle).checked; $(f.note).hidden = true; syncSave(); });
      input.addEventListener('input', () => { $(f.note).hidden = true; syncSave(); });
      input.addEventListener('blur', () => { if (sheet) clampField(f); });
      input.addEventListener('keydown', (event) => {
        if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
        event.preventDefault();
        const step = (event.shiftKey ? 10 : 1) * (event.key === 'ArrowUp' ? 1 : -1);
        const v = fieldValue(f);
        input.value = String(Math.min(f.max, Math.max(f.min, (Number.isNaN(v) ? (typeof sheet.loaded[f.key] === 'number' ? sheet.loaded[f.key] : DEFAULTS[f.key]) : v) + step)));
        $(f.note).hidden = true; syncSave();
      });
    });
    // Keep Tab inside the sheet while it is open.
    $('sheet').addEventListener('keydown', (event) => {
      if (event.key !== 'Tab') return;
      const items = [...$('sheet').querySelectorAll('input:not(:disabled), button:not(:disabled)')];
      const i = items.indexOf(document.activeElement);
      if (event.shiftKey && i <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
      else if (!event.shiftKey && i === items.length - 1) { event.preventDefault(); items[0].focus(); }
    });
  }

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    if (sheet) closeSettings(); else native('close');
  });
  scroll.addEventListener('scroll', syncHeroWords, { passive: true });
  window.addEventListener('resize', () => { if (!firstRender) { drawTop(); syncHeroWords(); } });

  wireSheet();
  // Mac keeps the page loaded between opens: reopen() refreshes in place and treats the
  // next render as an open (what's new since the last look), with no reload or blank frame.
  function reopen() { if (!firstRender) opening = true; return refresh(); }
  window.NagiGlance = Object.freeze({ openSettings, refresh, reopen, openSetup, openSources });
  refresh();
  setInterval(refresh, POLL_MS);
})();
