'use strict';
// Nagi glance panel (v3, "Soundings"): renders the view model as a band of dials, a watch
// list with a status column and drawn lineage, one Ended line and a source rail; runs the
// gated open motion and the settings sheet. Read-only.
(() => {
  const M = window.NagiModel;
  const $ = (id) => document.getElementById(id);
  const SVGNS = 'http://www.w3.org/2000/svg';
  const MAX_H = 690;
  const MIN_H = 320;
  const POLL_MS = 20000;
  const LAST_OPEN = 'nagi-last-open';
  const LAST_DIALS = 'nagi-dials';
  const R = 10; // branch elbow radius
  const GAP = 3; // air between a line's end and the node it meets
  const DIAL_R = 22; const DIAL_C = 2 * Math.PI * DIAL_R;
  const Motion = window.NagiMotion;
  const reduced = Motion.reduced;
  const panel = $('panel'); const scroll = $('scroll'); const inner = $('scroll-inner');
  const sheetLayer = $('sheet-layer');

  let readerFailedAt = null;
  let firstRender = true; let opening = false;
  let endedOpen = false; let openDial = null; let openSource = null; let loadOpen = false; let prsOpen = false;
  // Which detail opened last, so Esc closes that one first and returns focus to its trigger.
  let lastOpened = null;
  let envelope = null; let view = null;
  // GitHub checks, pull requests, ended results and machine load (web/glance-ci.js): the four
  // feeds as last read (null = the route answered 404, undefined = it didn't answer), the last
  // that did answer, and what NagiCI built from them for this render.
  // Until the first read lands nothing is drawn for a feed: not read yet is not a failure.
  let feeds = { ci: null, pulls: null, ended: null, machine: null }; const feedsPrev = {}; let ci = null;
  // Which refresh is the newest: an older one that lands late is dropped, never drawn.
  let refreshGen = 0;
  // Whether each feed was last known to be absent (a reader without the route) or switched
  // off, kept across opens so a failed first read stays silent only for a feed that was.
  const FEEDS_KNOWN = 'nagi-feeds-known';
  const OFF = Object.freeze({ status: 'not_set_up', attemptedAt: null, checkedAt: null, reason: 'disabled', data: null });
  const feedOff = (value) => !!value && value.status === 'not_set_up' && value.reason === 'disabled';
  try {
    const known = JSON.parse(localStorage.getItem(FEEDS_KNOWN) || 'null') || {};
    for (const key of ['ci', 'pulls', 'ended', 'machine']) { if (known[key] === 'absent') feedsPrev[key] = null; else if (known[key] === 'off') feedsPrev[key] = OFF; }
  } catch {}
  function rememberFeeds() {
    const known = {};
    for (const [key, value] of Object.entries(feedsPrev)) known[key] = value === null ? 'absent' : feedOff(value) ? 'off' : 'on';
    try { localStorage.setItem(FEEDS_KNOWN, JSON.stringify(known)); } catch {}
  }
  let sheet = null;
  let lastOpen = null; let lastDials = null;
  try { const v = Number(localStorage.getItem(LAST_OPEN)); if (Number.isFinite(v) && v > 0) lastOpen = v; } catch {}
  try { const v = JSON.parse(localStorage.getItem(LAST_DIALS) || 'null'); if (v && typeof v === 'object') lastDials = v; } catch {}

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
  const chevron = () => { const s = svg('svg', { class: 'chev', viewBox: '0 0 12 12', 'aria-hidden': 'true' }); s.append(svg('path', { d: 'M4.5 2.5 8 6l-3.5 3.5' })); return s; };
  // A source chip: the app's monogram, its full name as the tooltip.
  const chip = (tag) => h('span', { class: 'chip hx-' + tag.harness, title: tag.name + ' · ' + tag.label, text: tag.chip });

  // ---- Checks, deployments, pull requests, load: the drawn marks -----------------------
  // Shapes from the lead's accepted drawings (design/themes/creative-direction.md, Part 2); every
  // colour is a class, so the theme paints them and a dated mark is the same shape in grey.
  const TRI = 'M8 3.2L13.4 12.6H2.6Z';
  const C6 = 2 * Math.PI * 6;
  function markSvg(m) {
    const s = svg('svg', { class: 'mark ' + m.kind + '-' + m.state + (m.dated ? ' dated' : ''), viewBox: m.kind === 'pr' ? '0 0 24 24' : '0 0 16 16', 'aria-hidden': 'true' });
    const add = (tag, cls, attrs) => s.append(svg(tag, { class: cls, ...attrs }));
    if (m.kind === 'deploy') {
      if (m.state === 'success') add('path', 's f', { d: TRI });
      else if (m.state === 'failed') { add('path', 's f', { d: TRI }); add('path', 'k w18', { d: 'M8 6.4v3.4' }); }
      else if (m.state === 'waiting') { add('path', 's', { d: TRI }); add('circle', 'f', { cx: 8, cy: 9.6, r: 1.3 }); }
      else if (m.state === 'unknown') add('path', 's', { d: TRI, 'stroke-dasharray': '3 2.4' });
      else add('path', 's', { d: TRI }); // deploying, inactive
      return s;
    }
    if (m.kind === 'pr') { // a pull request with no checks: Lucide git-pull-request
      add('circle', 's', { cx: 18, cy: 18, r: 3 }); add('circle', 's', { cx: 6, cy: 6, r: 3 });
      add('path', 's', { d: 'M13 6h3a2 2 0 0 1 2 2v7' }); add('path', 's', { d: 'M6 9v12' });
      return s;
    }
    if (m.state === 'passed') { add('circle', 's', { cx: 8, cy: 8, r: 6 }); add('path', 's', { d: 'M5.2 8.2l2 2 3.6-4' }); }
    else if (m.state === 'merged') { add('circle', 'f', { cx: 8, cy: 8, r: 7 }); add('path', 'k', { d: 'M4.9 8.2l2.1 2.1 4-4.4' }); }
    else if (m.state === 'failed') { add('circle', 'f', { cx: 8, cy: 8, r: 7 }); add('path', 'k', { d: 'M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8' }); }
    else if (m.state === 'running') {
      // The arc is the share of checks finished. With no count there is no arc to draw, so
      // the ring holds a dot: running, and no guess at how far.
      add('circle', 't', { cx: 8, cy: 8, r: 6 });
      if (m.f == null) add('circle', 'f', { cx: 8, cy: 8, r: 2.5 });
      else add('circle', 's', { cx: 8, cy: 8, r: 6, transform: 'rotate(-90 8 8)', 'stroke-dasharray': Math.max(0.01, C6 * m.f).toFixed(2) + ' ' + C6.toFixed(2) });
    } else if (m.state === 'cancelled') { add('circle', 's', { cx: 8, cy: 8, r: 6 }); add('path', 's', { d: 'M5.2 8h5.6' }); }
    else { // unknown: a dashed ring with a small ?
      add('circle', 's', { cx: 8, cy: 8, r: 6, 'stroke-dasharray': '2 3.39' });
      add('path', 's w16', { d: 'M6.4 6.5a1.7 1.7 0 1 1 2.5 1.5c-.6.33-.9.66-.9 1.2' }); add('circle', 'f', { cx: 8, cy: 11.1, r: 0.95 });
    }
    return s;
  }
  // A mark with a link opens its page on GitHub; one without is a labelled picture.
  const markEl = (m, key, extra) => (m.href
    ? h('a', { class: 'mk' + (extra ? ' ' + extra : ''), href: m.href, 'data-key': key, 'aria-label': m.label, title: m.title }, markSvg(m))
    : h('span', { class: 'mk' + (extra ? ' ' + extra : ''), role: 'img', 'aria-label': m.label, title: m.title }, markSvg(m)));

  // The header's checks ring: one segment per watched branch, failed, running, passed.
  function ringSvg(ring) {
    const s = svg('svg', { class: 'cring' + (ring.dated ? ' dated' : ''), viewBox: '0 0 20 20', 'aria-hidden': 'true' });
    if (ring.unknown) {
      s.append(svg('circle', { class: 'u', cx: 10, cy: 10, r: 7, 'stroke-dasharray': '2 3.5' }));
      s.append(svg('path', { class: 'uq', d: 'M8.4 8.5a1.7 1.7 0 1 1 2.5 1.5c-.6.33-.9.66-.9 1.2' }));
      s.append(svg('circle', { class: 'ud', cx: 10, cy: 13.1, r: 0.95 }));
      return s;
    }
    const c = 2 * Math.PI * 7; const total = ring.segments.reduce((n, x) => n + x.n, 0);
    const gap = ring.segments.length > 1 ? 2.2 : 0; let at = 0;
    for (const x of ring.segments) {
      const len = c * x.n / total;
      s.append(svg('circle', { class: 'seg ' + x.state, cx: 10, cy: 10, r: 7, transform: 'rotate(' + (-90 + at / c * 360).toFixed(1) + ' 10 10)',
        'stroke-dasharray': Math.max(1, len - gap).toFixed(2) + ' ' + c.toFixed(2) }));
      at += len;
    }
    return s;
  }
  // Machine load: concentric arcs, CPU outside, memory, GPU innermost when there is one.
  function loadSvg(load) {
    const s = svg('svg', { class: 'lring', viewBox: '0 0 22 22', 'aria-hidden': 'true' });
    const radii = [9.5, 6.5, 3.5];
    if (load.failed) { s.append(svg('circle', { class: 'u', cx: 11, cy: 11, r: 9.5, 'stroke-dasharray': '1.5 2.6' })); return s; }
    load.rings.forEach((x, i) => {
      const r = radii[i]; const c = 2 * Math.PI * r;
      if (x.f == null) { s.append(svg('circle', { class: 'u', cx: 11, cy: 11, r, 'stroke-dasharray': '1.5 2.6' })); return; }
      s.append(svg('circle', { class: 't', cx: 11, cy: 11, r }));
      if (x.f > 0) s.append(svg('circle', { class: 'a' + (x.high ? ' high' : ''), cx: 11, cy: 11, r, transform: 'rotate(-90 11 11)', 'stroke-dasharray': (c * x.f).toFixed(2) + ' ' + c.toFixed(2) }));
    });
    return s;
  }

  // The checks ring, a deployment in flight, and the load ring sit between the flags and the gear.
  function gauges() {
    let box = $('gauges');
    if (!box) { box = h('div', { class: 'gauges', id: 'gauges' }); $('flags').after(box); }
    return box;
  }
  function renderGauges() {
    const kids = [];
    const head = ci && ci.header;
    if (head && (head.ring.segments.length || head.ring.unknown)) {
      const ring = head.ring;
      const button = h('button', { type: 'button', class: 'gauge cgauge' + (ring.dated ? ' is-dated' : ''), 'data-key': 'gauge:ci', 'aria-label': ring.label }, ringSvg(ring),
        ring.failed > 0 && h('b', { class: 'gauge-n', text: String(ring.failed) }));
      button.addEventListener('click', () => {
        // Couldn't check: the rail says why. Otherwise the first failed (or running) row comes into view.
        if (ring.unknown) { openSource = 'gh'; lastOpened = 'src'; renderRail(view.vm); layout(); focusKey('src:gh'); return; }
        const row = head.target && document.querySelector('#past .row[data-id="' + CSS.escape(head.target) + '"]');
        if (!row) return;
        reveal(row.closest('.project').querySelector('.proj-head'), row);
        row.focus({ preventScroll: true });
      });
      kids.push(button);
    }
    if (head && head.deploy) kids.push(markEl(head.deploy, 'gauge:deploy', 'gauge-mk'));
    const load = ci && ci.load;
    if (load) {
      const button = h('button', { type: 'button', class: 'gauge lgauge' + (loadOpen ? ' is-open' : ''), 'data-key': 'gauge:load', 'aria-expanded': String(loadOpen), 'aria-controls': 'load-detail', 'aria-label': load.label }, loadSvg(load));
      button.addEventListener('click', () => { loadOpen = !loadOpen; if (loadOpen) lastOpened = 'load'; renderGauges(); layout(); focusKey('gauge:load'); });
      kids.push(button);
    } else loadOpen = false;
    gauges().replaceChildren(...kids);
    renderLoadDetail(load);
  }
  // The exact numbers, one press away, in the dial detail's look.
  function renderLoadDetail(load) {
    let box = $('load-detail');
    if (!box) { box = h('div', { class: 'dial-detail load-detail', id: 'load-detail', hidden: true }); $('dial-note').after(box); }
    box.hidden = !(loadOpen && load);
    if (box.hidden) { box.replaceChildren(); return; }
    box.replaceChildren(...[
      h('ul', { class: 'dd-rows' }, load.failed ? h('li', { class: 'dd-row words', text: load.failed.words })
        : load.rows.map((r) => h('li', { class: 'dd-row' + (r.pct == null ? ' unread' : '') }, h('span', { class: 'dd-w', text: r.name }),
          h('span', { class: 'dd-p' }, r.pct == null ? "couldn't read" : h('b', { text: r.pct })), h('span', { class: 'dd-d', text: r.more })))),
      !load.failed && h('p', { class: 'dd-key' }, 'CPU is the one-minute load across all cores, so it can pass 100%.'),
      load.asOf && h('p', { class: 'dd-key', text: load.asOf.charAt(0).toUpperCase() + load.asOf.slice(1) + '.' })].filter(Boolean));
  }

  // Pull requests waiting on the owner: one group in the watch list, built like a project.
  const PR_SHOWN = 4;
  function prsGroup(p) {
    const I = window.NagiIcons;
    // A queue that couldn't be read says so where it would have been: pull requests may be
    // waiting on the owner, and silence would read as none.
    if (p.failed) return h('li', { class: 'prs-say' }, h('p', { class: 'say' }, I.glyph('pull-request'), h('span', { class: 'say-words', text: 'Pull requests: ' + p.failed.words })));
    if (!p.rows.length) return null;
    const shown = prsOpen ? p.rows : p.rows.slice(0, PR_SHOWN);
    const rows = shown.map((r) => h('li', { class: 'item d1' },
      h('a', { class: 'row pr', href: r.href || null, tabindex: r.href ? null : '-1', 'data-key': 'pr:' + r.key, 'aria-label': r.label },
        h('span', { class: 'node', 'aria-hidden': 'true' }),
        h('span', { class: 'title', text: r.title }),
        // Why it waits, then its checks (drawn, not a second link: the row is the PR).
        h('span', { class: 'aside' }, h('span', { class: 'why-line' }, h('span', { class: 'note asks why', text: r.why }), r.mark && markSvg(r.mark)),
          h('span', { class: 'pr-ref', text: r.repo + ' #' + r.number })))));
    const more = p.rows.length - shown.length;
    if (more > 0) {
      const button = h('button', { type: 'button', class: 'prs-more', 'data-key': 'prs-more', text: '+ ' + more + ' more' });
      button.addEventListener('click', () => { prsOpen = true; renderPast(view.vm, view); layout(); focusKey('pr:' + p.rows[PR_SHOWN].key); });
      rows.push(h('li', { class: 'prs-more-item' }, button));
    }
    return h('li', { class: 'project prs' },
      h('div', { class: 'proj-head', 'data-node': 'project' }, h('span', { class: 'pi pi-prs', 'aria-hidden': 'true' }, I.glyph('pull-request')),
        h('span', { class: 'proj-name', text: 'Pull requests' }), p.dated && h('span', { class: 'proj-asof', text: p.asOf }),
        h('span', { class: 'chip', title: 'GitHub', text: 'GH' })),
      h('ul', { class: 'agents' }, rows));
  }

  // Ended results: `6 PRs` and a mark per pull request, at most two lines, then `+N`.
  function resultsLine(r) {
    if (!r) return null;
    if (r.failed && ci && ci.rail) return null; // said once, in the rail
    if (r.failed) return h('div', { class: 'results' }, h('span', { class: 'res-failed', text: "PRs couldn't check · " + r.failed.words.replace(/^couldn't check · /, '') }));
    if (!r.count) return null;
    return h('div', { class: 'results' },
      h('span', { class: 'res-count' }, h('b', { text: r.count + (r.partial ? '+' : '') }), r.count === 1 && !r.partial ? ' PR' : ' PRs'),
      r.marks.map((m, i) => markEl(m, 'result:' + i, 'res')),
      h('span', { class: 'res-more', hidden: true }),
      r.dated && h('span', { class: 'res-asof', text: ' · ' + r.asOf }));
  }
  // Two lines of marks at most: what doesn't fit is counted in `+N` at the end of the second.
  function fitResults() {
    const box = document.querySelector('#ended .results');
    if (!box) return;
    const marks = [...box.querySelectorAll('.mk.res')];
    const more = box.querySelector('.res-more');
    if (!more) return;
    marks.forEach((m) => { m.hidden = false; });
    more.hidden = true;
    const lines = [...new Set(marks.map((m) => m.offsetTop))];
    if (lines.length <= 2) return;
    // Lines are compared by their middles: the `+N` text is shorter than a mark's target.
    const limit = lines[1] + marks[0].offsetHeight;
    const middle = (el) => el.offsetTop + el.offsetHeight / 2;
    let hidden = marks.filter((m) => middle(m) > limit);
    hidden.forEach((m) => { m.hidden = true; });
    more.hidden = false;
    for (let i = marks.length - hidden.length - 1; i > 0; i--) {
      more.textContent = '+' + hidden.length;
      if (middle(more) <= limit) break;
      marks[i].hidden = true; hidden = [marks[i], ...hidden];
    }
    more.textContent = '+' + hidden.length;
  }

  // ---- Header: the count, and only what needs saying ---------------------------------
  function renderStatus(vm) {
    const hero = vm.hero;
    const kids = [];
    if (hero.quiet) kids.push(h('span', { class: 'headline says' + (hero.calm ? ' calm' : ''), text: hero.alert }));
    else if (hero.idle) kids.push(h('span', { class: 'headline says calm', text: 'Nothing running' }), hero.since && h('span', { class: 'since', text: 'since ' + hero.since }));
    else kids.push(h('span', { class: 'headline' + (hero.dim ? ' dim' : '') }, h('b', { class: 'num', text: hero.num }), ' ' + hero.word));
    const box = $('status');
    box.replaceChildren(...kids.filter(Boolean));
    box.setAttribute('aria-label', vm.heroLabel);
    // What needs you: each is a button that brings its row into view.
    const flags = [];
    if (!hero.quiet && hero.alert) flags.push(h('span', { class: 'flag alert', text: hero.alert }));
    // Pull requests waiting on the owner join what's blocked on them, before `asks you`.
    if (ci && ci.pulls && ci.pulls.flag) {
      const flag = h('button', { type: 'button', class: 'flag asks', 'data-key': 'word:prs', text: ci.pulls.flag });
      flag.addEventListener('click', () => {
        const group = document.querySelector('#past .project.prs');
        const row = group && group.querySelector('.row');
        if (!row) return;
        reveal(group.querySelector('.proj-head'), row);
        row.focus({ preventScroll: true });
      });
      flags.push(flag);
    }
    hero.words.forEach((w) => {
      const flag = h('button', { type: 'button', class: 'flag ' + w.cls, 'data-key': 'word:' + w.target, text: w.text });
      flag.addEventListener('click', () => {
        const row = document.querySelector('#past .row.is-' + w.target);
        if (!row) return;
        reveal(row.closest('.project').querySelector('.proj-head'), row);
        row.focus({ preventScroll: true });
      });
      flags.push(flag);
    });
    // Sources that can't be reached: one short flag; it opens the rail's own words.
    if (vm.unread) {
      const down = (vm.rail || []).find((r) => r.state === 'down');
      const flag = h('button', { type: 'button', class: 'flag quiet', 'data-key': 'word:down', text: vm.unread + (vm.unread === 1 ? ' source down' : ' sources down') });
      flag.addEventListener('click', () => { openSource = down.id; lastOpened = 'src'; renderRail(vm); layout(); focusKey('src:' + down.id); });
      flags.push(flag);
    }
    $('flags').replaceChildren(...flags);
    renderGauges();
    // A second line only for an exception: what failed and when, or what the count leaves out.
    const subs = hero.fine ? [] : hero.subs.filter((t) => !t.startsWith('nothing running since') && !/sources can't be read/.test(t));
    const sub = $('status-sub');
    sub.hidden = !subs.length;
    sub.textContent = subs.join(' · ');
  }

  // ---- Dials: one ring per limit window ------------------------------------------------
  // The arc is what's left; the tick is how much of the window's time is left. A failed read
  // is a dashed ring with no arc; an empty window says `empty`; a dated value is grey.
  function dial(cell, group) {
    const drawn = (cell.state === 'value' || cell.state === 'low' || cell.state === 'dated') && cell.pct > 0;
    const s = svg('svg', { viewBox: '0 0 50 50', 'aria-hidden': 'true' });
    s.append(svg('circle', { class: 'track', cx: 25, cy: 25, r: DIAL_R }));
    if (drawn) {
      const arc = svg('circle', { class: 'arc', cx: 25, cy: 25, r: DIAL_R, transform: 'rotate(-90 25 25)',
        'stroke-dasharray': (DIAL_C * cell.pct / 100).toFixed(2) + ' ' + DIAL_C.toFixed(2) });
      arc.dataset.key = group.key + ':' + cell.w; arc.dataset.pct = cell.pct;
      s.append(arc);
    }
    if (cell.timeLeft != null) {
      const a = cell.timeLeft * 2 * Math.PI; const dx = Math.sin(a); const dy = -Math.cos(a);
      const at = (r) => ({ x: (25 + dx * r).toFixed(2), y: (25 + dy * r).toFixed(2) });
      const from = at(DIAL_R - 1); const to = at(DIAL_R + 6.5);
      s.append(svg('line', { class: 'tick-halo', x1: from.x, y1: from.y, x2: to.x, y2: to.y }));
      s.append(svg('line', { class: 'tick', x1: from.x, y1: from.y, x2: to.x, y2: to.y }));
    }
    const val = cell.pct != null && cell.state !== 'empty' ? h('span', { class: 'val' }, h('b', { text: String(cell.pct) }), h('small', { text: '%' }))
      : h('span', { class: 'val word', text: cell.state === 'empty' ? 'empty' : cell.state === 'failed' ? '?' : cell.state === 'checking' ? '…' : '—' });
    return h('span', { class: 'dial', 'data-pv': group.provider }, s, val);
  }

  function renderDials(vm) {
    const groups = vm.dials || [];
    const box = $('dials');
    box.hidden = !groups.length;
    box.replaceChildren(...groups.map((g) => {
      const open = openDial === g.key;
      // With several sources, the chips under a group say which of them read it.
      const button = h('button', { type: 'button', class: 'acct' + (open ? ' is-open' : ''), 'data-key': 'dial:' + g.key, 'aria-expanded': String(open), 'aria-controls': 'dial-detail', 'aria-label': g.label },
        h('span', { class: 'acct-name', text: g.name }),
        h('span', { class: 'cells' }, g.cells.map((c) => h('span', { class: 'cell ' + c.state },
          dial(c, g), h('span', { class: 'w', text: c.w }), h('span', { class: 'd', text: c.d || '\u00a0' })))),
        // A value from an earlier check is grey and says when it was read, once for the group.
        g.asOf && h('span', { class: 'as-of', text: g.asOf }),
        g.sources.length > 0 && h('span', { class: 'chips' }, g.sources.map(chip)));
      button.addEventListener('click', () => { openDial = open ? null : g.key; if (!open) lastOpened = 'dial'; renderDials(vm); layout(); focusKey('dial:' + g.key); });
      return button;
    }));
    // The exact lines for the chosen account: each window, its percent, its full reset date.
    const g = groups.find((d) => d.key === openDial);
    const detail = $('dial-detail');
    detail.hidden = !g;
    if (!g) { openDial = null; detail.replaceChildren(); }
    else {
      detail.replaceChildren(...[
        h('div', { class: 'dd-head' }, h('span', { class: 'dd-name', text: g.name }), g.about && h('span', { class: 'dd-about', text: g.about })),
        h('ul', { class: 'dd-rows' }, g.rows.map((r) => h('li', { class: 'dd-row' + (r.pct == null ? ' words' : '') },
          r.pct != null && h('span', { class: 'dd-w', text: r.name }),
          r.pct != null && h('span', { class: 'dd-p' }, h('b', { text: r.empty ? 'empty' : r.pct + '%' }), r.empty ? null : ' left'),
          h('span', { class: 'dd-d', text: r.pct != null && !r.empty ? 'resets ' + r.date : r.date })))),
        // The one mark that needs a word, said once, where the exact times are.
        g.cells.some((c) => c.timeLeft != null) && h('p', { class: 'dd-key' }, h('i', { 'aria-hidden': 'true' }), 'The tick is the time left in the window. An arc past it will last.')].filter(Boolean));
    }
    const note = $('dial-note');
    note.hidden = !(vm.dialNotes || []).length;
    note.textContent = (vm.dialNotes || []).join(' ');
  }

  // ---- The watch list ---------------------------------------------------------------------
  function rowEl(r) {
    const depth = Math.min(r.depth, 3);
    const running = r.kind === 'running';
    const cls = 'row ' + r.kind + (r.asks ? ' is-asks' : '') + (r.stuck ? ' is-stuck' : '') + (r.isNew ? ' is-new' : '') + (r.pending ? ' is-pending' : '') + (r.dated ? ' is-dated' : '');
    // The status column: model and run time, then a state only when there is one to say.
    // A parent kept for context says nothing unless it failed or was stopped.
    let aside = null;
    if (running) {
      aside = h('span', { class: 'aside' }, h('span', { class: 'model' + (r.provider ? ' pv-' + r.provider : ''), text: r.model }),
        r.run && sep(), r.run && h('span', { class: 'run', text: r.run }),
        r.note && h('span', { class: 'note ' + r.note.cls, text: r.note.text }));
    } else if (r.state !== 'completed') {
      aside = h('span', { class: 'aside' }, h('span', { class: 'note quiet', text: r.meta[r.meta.length - 1] }));
    }
    // Checks, then deployment: marks at the trailing edge of the first line, each its own link.
    const own = ci && ci.byAgent[r.id];
    const marks = own ? [own.ci, own.deploy].filter(Boolean) : [];
    if (marks.length && !aside) aside = h('span', { class: 'aside' });
    // A row its app can't open is not a tab stop, but the header's flags can still focus it.
    const link = h('a', { class: cls + (marks.length ? ' mk' + marks.length : ''), href: r.href || null, tabindex: r.href ? null : '-1', 'data-provider': r.provider || null, 'data-key': 'row:' + r.id, 'data-id': r.id, 'data-start': r.started || 0, 'aria-label': r.label,
      // How far through the stuck threshold its silence is; the node draws it as a draining disc.
      'data-f': r.silence ? r.silence.f.toFixed(3) : null },
      h('span', { class: 'node', 'aria-hidden': 'true' }),
      h('span', { class: 'title' }, r.prefix && h('span', { class: 'prefix', text: r.prefix }), r.prefix && ' ', r.rest),
      aside);
    return h('li', { class: 'item d' + depth + (marks.length ? ' has-marks' : '') }, link,
      marks.length > 0 && h('span', { class: 'marks' }, marks.map((m) => markEl(m, 'mk:' + r.id + ':' + m.kind))),
      r.children.length > 0 && h('ul', { class: 'kids' }, r.children.map((c) => rowEl(c))));
  }

  // T3's project icon heads each project's rail. It is decorative; the heading text stays the
  // label. Favicons come from owner-authenticated fetches as blob: URLs.
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

  // An empty list: a quiet mark and a few words. The sentence is its tooltip and, on a click
  // or Enter, a line beneath it.
  let sayOpen = false;
  function sayLine(say) {
    const inside = [window.NagiIcons.glyph(say.icon), h('span', { class: 'say-words', text: say.words })];
    if (!say.detail) return h('p', { class: 'say', 'data-node': 'anchor' }, inside);
    const detail = h('p', { class: 'say-detail', id: 'say-detail', hidden: !sayOpen, text: say.detail });
    const button = h('button', { type: 'button', class: 'say', 'data-key': 'say', 'data-node': 'anchor', title: say.detail, 'aria-expanded': String(sayOpen), 'aria-controls': 'say-detail' }, inside);
    button.addEventListener('click', () => { sayOpen = !sayOpen; button.setAttribute('aria-expanded', String(sayOpen)); detail.hidden = !sayOpen; layout(); });
    return h('div', { class: 'say-box' }, button, detail);
  }

  function renderPast(vm, view) {
    const kids = [];
    const list = vm.list || [];
    const prs = ci && ci.pulls ? prsGroup(ci.pulls) : null;
    if (list.length || prs) {
      const items = list.map((p) => h('li', { class: 'project' + (p.dated ? ' is-dated' : '') },
        h('div', { class: 'proj-head', 'data-node': 'project' }, projectIcon(p.icon), h('span', { class: 'proj-name', text: p.title }), p.source && chip(p.source)),
        h('ul', { class: 'agents' }, p.rows.map((r) => rowEl(r)))));
      // Straight after the last project that needs the owner, or first when none does.
      if (prs) items.splice(list.reduce((at, p, i) => (p.urgency > 0 && !p.dated ? i + 1 : at), 0), 0, prs);
      kids.push(h('ul', { class: 'projects', 'aria-label': 'Agents by project' }, items));
    }
    (vm.notes || []).forEach((text) => kids.push(h('p', { class: 'note-line', text })));
    if (vm.say) kids.push(sayLine(vm.say));
    if (view && view.kind === 'empty') kids.push(h('p', { class: 'setup-call' }, h('button', { class: 'btn default', type: 'button', id: 'start-setup', text: 'Set up Nagi' })));
    $('past').replaceChildren(...kids);
    const start = $('start-setup');
    if (start) start.addEventListener('click', (event) => openSetup({ instant: event.detail === 0 }));
  }

  // ---- Ended: one line, an outcome bar, and the threads that failed or were stopped ----------
  function renderEnded(vm) {
    const box = $('ended');
    const e = vm.endedAll;
    box.hidden = !e;
    if (!e) { box.replaceChildren(); return; }
    const t = e.totals;
    const bar = h('span', { class: 'obar', 'aria-hidden': 'true' });
    [['done', t.completed], ['failed', t.failed], ['stopped', t.stopped]].forEach(([cls, n]) => {
      if (!n) return;
      const part = h('i', { class: cls }); part.style.flexGrow = String(n); bar.append(part);
    });
    // The visible line is the button's name; the dated sentence is its description.
    const button = h('button', { class: 'ended-btn', type: 'button', 'data-key': 'ended', 'aria-expanded': String(endedOpen), 'aria-controls': 'ended-list', 'aria-describedby': 'ended-desc' },
      h('span', { class: 'node', 'aria-hidden': 'true' }),
      h('span', { class: 'ended-line' }, e.count == null ? 'Ended' : h('b', { text: String(e.count) }), e.count == null ? '' : ' ended'),
      bar.children.length > 0 && bar,
      e.problems && h('span', { class: 'ended-problems', text: e.problems }),
      e.more && h('span', { class: 'ended-more', text: e.more }),
      h('span', { class: 'ended-span' }, e.span, chevron()));
    const desc = h('span', { class: 'sr', id: 'ended-desc', text: e.label + (e.split ? ' ' + e.split + '.' : '') });
    const produced = (g) => (ci && ci.results && ci.results.byProject[g.key]) || [];
    const list = h('ul', { class: 'ended-list', id: 'ended-list', hidden: !endedOpen },
      e.groups.map((g) => h('li', { class: 'eg-group' },
        h('div', { class: 'eg' }, projectIcon(g.icon), h('span', { class: 'eg-name', text: g.title }), g.source && chip(g.source), h('span', { class: 'eg-meta', text: g.summary })),
        (g.problems.length > 0 || produced(g).length > 0) && h('ul', { class: 'problems' }, g.problems.map((p, i) => h('li', {},
          h('a', { class: 'problem', href: p.href || null, 'data-key': 'problem:' + g.key + ':' + i, 'aria-label': p.title + '. ' + p.meta + '.' + (p.href ? ' Opens in its app.' : '') },
            h('span', { class: 'node', 'aria-hidden': 'true' }), h('span', { class: 'title', text: p.title }),
            h('span', { class: 'aside', text: p.when })))),
          // What each finished agent produced: its pull request, its state and its checks.
          produced(g).map((x) => h('li', {},
            h('a', { class: 'problem result', href: x.href || null, tabindex: x.href ? null : '-1', 'data-key': 'result-row:' + g.key + ':' + x.agentId, 'aria-label': x.title + '. ' + x.label },
              h('span', { class: 'node', 'aria-hidden': 'true' }), h('span', { class: 'title', text: x.title }),
              h('span', { class: 'aside' }, '#' + x.number + (x.word ? ' ' + x.word : ''), x.mark && markSvg(x.mark)))))))));
    button.addEventListener('click', () => {
      endedOpen = !endedOpen;
      button.setAttribute('aria-expanded', String(endedOpen));
      list.hidden = !endedOpen;
      layout();
      if (endedOpen) reveal(button, button);
    });
    box.replaceChildren(...[button, resultsLine(ci && ci.results), desc, list].filter(Boolean));
  }

  // ---- Sources rail: a chip per source; words only for an exception ---------------------------
  const GH_GLYPH = { absent: 'plug', down: 'unplug', checking: 'hourglass', dated: 'hourglass', partial: 'question' };
  function renderRail(vm) {
    const gh = ci && ci.rail;
    // GitHub explains itself in the rail, even beside a single source.
    const items = [...(vm.rail || []), ...(gh ? [{ id: 'gh', harness: 'gh', chip: 'GH', name: 'GitHub', label: 'checks and pull requests', title: 'GitHub',
      state: gh.state, icon: GH_GLYPH[gh.state] || 'question', count: null, words: gh.words, detail: gh.detail, said: gh.said, showLabel: false }] : [])];
    const box = $('rail');
    box.hidden = !items.length;
    if (!items.length) { box.replaceChildren(); openSource = null; return; }
    const chips = h('div', { class: 'srcs' }, items.map((r) => {
      const inside = [chip(r), r.showLabel && h('span', { class: 'src-label', text: r.label }),
        r.count != null && h('b', { class: 'src-count', text: String(r.count) }), r.icon && window.NagiIcons.glyph(r.icon), r.words && h('span', { class: 'src-words', text: r.words })];
      // Only a source with something to explain opens a line of words.
      if (!r.detail) return h('span', { class: 'src ' + r.state, title: r.title, 'aria-label': r.said, role: 'img' }, inside);
      const open = openSource === r.id;
      const button = h('button', { type: 'button', class: 'src ' + r.state + (open ? ' is-open' : ''), 'data-key': 'src:' + r.id, title: r.title + ': ' + r.detail, 'aria-label': r.said, 'aria-expanded': String(open), 'aria-controls': 'rail-detail' }, inside);
      button.addEventListener('click', () => { openSource = open ? null : r.id; if (!open) lastOpened = 'src'; renderRail(vm); layout(); focusKey('src:' + r.id); });
      return button;
    }));
    const chosen = items.find((r) => r.id === openSource && r.detail);
    if (!chosen) openSource = null;
    box.replaceChildren(...[chosen && h('p', { class: 'rail-detail', id: 'rail-detail' }, h('b', { text: chosen.title }), ' ' + chosen.detail), chips].filter(Boolean));
  }

  // ---- Layout and geometry -----------------------------------------------------------------
  // Positions in the scrolled content's own CSS pixels. Under a CSS zoom (the website's Mac
  // density) rects come back scaled, so they are divided back; the native shells zoom the
  // whole page, where the factor is 1.
  function rel(el, box) {
    const r = el.getBoundingClientRect();
    const k = inner.offsetWidth ? box.width / inner.offsetWidth : 1;
    return { x: (r.left - box.left + r.width / 2) / k, y: (r.top - box.top + r.height / 2) / k, top: (r.top - box.top) / k, bottom: (r.bottom - box.top) / k };
  }
  const radius = (row) => (row.classList.contains('is-pending') ? 4.5 : 5.5);

  // Each project is its own small tree: a rail from its icon through its agents, and a drawn
  // branch from every parent to each child. Lines stop short of the nodes they meet.
  function drawPast() {
    const geo = $('geo-past');
    const box = inner.getBoundingClientRect();
    geo.setAttribute('width', inner.offsetWidth); geo.setAttribute('height', inner.scrollHeight);
    geo.replaceChildren();
    const branch = (d, row) => {
      const path = svg('path', { class: 'branch', d, 'data-start': row ? row.dataset.start : 0 });
      if (row && row.classList.contains('is-new')) path.dataset.new = '1';
      geo.append(path);
    };
    const rail = (head, rows) => {
      if (!head || !rows.length) return;
      const top = rel(head, box);
      let y = top.bottom + 1;
      rows.forEach((row) => {
        const n = rel(row.querySelector('.node'), box); const r = radius(row);
        if (n.y - r - GAP > y) branch(`M${top.x} ${y} V${n.y - r - GAP}`, row);
        y = n.y + r + GAP;
      });
    };
    const rowOf = (item) => item.querySelector(':scope > .row');
    document.querySelectorAll('#past .project').forEach((proj) => {
      rail(proj.querySelector('.proj-head .pi'), [...proj.querySelectorAll(':scope > .agents > .item')].map(rowOf));
    });
    document.querySelectorAll('#past .kids').forEach((ul) => {
      const parentRow = rowOf(ul.parentElement);
      const p = rel(parentRow.querySelector('.node'), box); const pr = radius(parentRow);
      [...ul.children].forEach((item) => {
        const row = rowOf(item);
        const n = rel(row.querySelector('.node'), box); const r = radius(row);
        const d = n.x - p.x < R + 6 ? `M${p.x} ${p.y + pr + GAP} V${n.y - r - GAP}`
          : `M${p.x} ${p.y + pr + GAP} V${n.y - R} Q${p.x} ${n.y} ${p.x + R} ${n.y} H${n.x - r - GAP}`;
        branch(d, row);
      });
    });
    // An expanded Ended list: each project's failed and stopped threads hang from its icon.
    document.querySelectorAll('.ended-list:not([hidden]) .eg-group').forEach((group) => {
      rail(group.querySelector('.eg .pi'), [...group.querySelectorAll('.problem')]);
    });
    // Nodes keep their state shape (solid running, ring otherwise) in the provider's colour;
    // asks you stays rose, the one colour reserved for it. A dated row is always hollow.
    document.querySelectorAll('#past .row .node, #ended .problem .node, #ended .ended-btn .node').forEach((el) => {
      const a = rel(el, box); const row = el.parentElement;
      const running = row.classList.contains('running') && !row.classList.contains('is-dated');
      const pending = row.classList.contains('is-pending');
      const asks = row.classList.contains('is-asks');
      if (row.classList.contains('pr')) { geo.append(svg('circle', { class: 'n-pr', cx: a.x, cy: a.y, r: 4.5 })); return; }
      const tone = !asks && row.dataset.provider ? ' pv-' + row.dataset.provider : '';
      // Silence drains the node like a timer: a full disc has just spoken, a thin wedge is
      // nearly stuck, an empty yellow ring is stuck. Under a tenth it is simply full.
      const f = running && !asks && row.dataset.f != null ? Number(row.dataset.f) : 0;
      if (f >= 0.1) {
        const late = f >= 0.5 ? ' late' : '';
        geo.append(svg('circle', { class: 'n-rim' + tone + late, cx: a.x, cy: a.y, r: 4.5 }));
        if (f < 1) {
          const left = (1 - f) * 2 * Math.PI; const r = 4.5;
          const x = a.x + Math.sin(left) * r; const y = a.y - Math.cos(left) * r;
          geo.append(svg('path', { class: 'n-wedge' + tone + late, d: `M${a.x} ${a.y} V${a.y - r} A${r} ${r} 0 ${left > Math.PI ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)} Z` }));
        }
        return;
      }
      const c = svg('circle', { class: (asks ? 'n-asks' : pending ? 'n-pending' : running ? 'n-running' : 'n-ring') + tone, cx: a.x, cy: a.y, r: pending ? 3.5 : running || asks ? 5 : 4.5 });
      if (row.dataset.key) c.dataset.key = row.dataset.key;
      geo.append(c);
    });
  }

  function natural() { return $('pinned').offsetHeight + inner.offsetHeight + $('rail').offsetHeight; }

  // Scroll so `top` sits INSET px under the pinned band while `target` stays fully in view.
  const INSET = 8;
  function reveal(top, target) {
    const view = scroll.getBoundingClientRect();
    const y = (el) => el.getBoundingClientRect().top - view.top + scroll.scrollTop;
    const want = y(top) - INSET;
    const bottom = y(target) + target.getBoundingClientRect().height + INSET - scroll.clientHeight;
    scroll.scrollTop = Math.min(Math.max(want, bottom), y(target) - INSET);
  }
  // Focus without jumping the page; a dial scrolled out of its band is brought back into it.
  function focusKey(key) {
    const el = document.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (!el) return;
    el.focus({ preventScroll: true });
    const band = el.closest('.dials');
    if (band) {
      const b = band.getBoundingClientRect(); const r = el.getBoundingClientRect();
      if (r.top < b.top) band.scrollTop -= b.top - r.top;
      else if (r.bottom > b.bottom) band.scrollTop += r.bottom - b.bottom;
    }
  }

  // The flags wrap inside their own box, as they always have; when the gauges leave them so
  // little room that they would stack three high, they take a line of their own under the header.
  function fitFlags() {
    const top = $('flags').parentElement;
    top.classList.remove('flags-below');
    if (!$('gauges') || !$('gauges').childElementCount) return;
    const lines = new Set([...$('flags').children].map((f) => f.offsetTop)).size;
    if (lines > 2) top.classList.add('flags-below');
  }
  function layout() {
    fitFlags();
    fitResults();
    drawPast();
    // Two spare px absorb the rounding between window and CSS pixels at fractional text scales.
    native('height:' + Math.max(MIN_H, Math.min(MAX_H, Math.ceil(natural()) + 2)));
  }

  // What each dial read at this open, so the next open can show what changed since.
  function rememberDials() {
    const now = {};
    document.querySelectorAll('#dials .arc').forEach((arc) => { now[arc.dataset.key] = Number(arc.dataset.pct); });
    document.querySelectorAll('#dials .cell.empty').forEach((cell, i) => { now['empty:' + i] = 0; });
    lastDials = now;
    try { localStorage.setItem(LAST_DIALS, JSON.stringify(now)); } catch {}
  }

  // ---- Data -----------------------------------------------------------------
  async function getJson(path) {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw Object.assign(new Error('HTTP ' + response.status), { status: response.status });
    return response.json();
  }

  // The saved theme repaints on every render, but never over an Appearance preview: while that
  // sheet is open, the 20-second poll must not undo what the owner is trying.
  function applyTheme() {
    const T = window.NagiTheme;
    if (!T || (window.NagiAppearance && window.NagiAppearance.isOpen())) return;
    T.apply((envelope && envelope.settings && envelope.settings.theme) || T.current());
  }

  function render() {
    applyTheme();
    const opened = Date.now();
    // An open is the first render, or a native reopen of the already-loaded page (Mac).
    const isOpen = firstRender || opening;
    view = M.buildSources(envelope, { now: opened, lastOpen: isOpen ? lastOpen : null, reduced: reduced(), readerDownAt: readerFailedAt });
    const vm = view.vm;
    const active = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key : null;
    const top = scroll.scrollTop;
    // Every open starts from the glance: nothing expanded.
    if (isOpen) { endedOpen = false; openDial = null; openSource = null; loadOpen = false; prsOpen = false; }
    ci = window.NagiCI ? window.NagiCI.build(feeds, { now: opened, vm, prev: feedsPrev }) : null;
    renderStatus(vm); renderDials(vm); renderPast(vm, view); renderEnded(vm); renderRail(vm);
    panel.dataset.state = vm.mode;
    panel.dataset.kind = view.kind;
    layout();
    if (isOpen) scroll.scrollTop = 0; else scroll.scrollTop = top;
    if (active) focusKey(active);
    if (isOpen) {
      Motion.playOpen({ vm, opened, lastOpen, lastDials, geo: $('geo-past'), dials: $('dials') });
      if (vm.mode === 'live') { lastOpen = opened; try { localStorage.setItem(LAST_OPEN, String(opened)); } catch {} rememberDials(); }
      opening = false;
    }
    if (firstRender) {
      firstRender = false;
      native('ready');
      // Nothing connected yet: the setup opens by itself, once per page.
      if (view.kind === 'empty' && !readerFailedAt) openSetup({ instant: true });
    }
  }

  // The CI model (web/glance-ci.js) is loaded by the page, before this file.
  const ciReady = Promise.resolve();
  const FEEDS = [['ci', '/api/sources/v1/ci'], ['pulls', '/api/sources/v1/ci/pulls'], ['ended', '/api/sources/v1/ci/ended'], ['machine', '/api/sources/v1/machine']];
  // 404 is a reader without the route (null); any other failure is a read that didn't answer.
  const readFeed = (key, path) => getJson(path).then((body) => (body && body[key] !== undefined ? body[key] : undefined), (error) => (error.status === 404 ? null : undefined));
  const FEED_GRACE_MS = 400;

  async function refresh() {
    // Refreshes can overlap (the poll, a reopen, a changed setting) and land in any order.
    // Only the newest may write what the panel holds; a superseded one is dropped whole.
    const gen = ++refreshGen;
    const newest = () => gen === refreshGen;
    // The four CI and load feeds are read alongside the glance and never hold it up: past a
    // short grace the glance draws without them, and again when they land.
    let landed = false;
    const reads = Promise.all([ciReady, ...FEEDS.map(([key, path]) => readFeed(key, path).then((value) => [key, value]))]).then(([, ...pairs]) => {
      if (!newest()) return;
      feeds = Object.fromEntries(pairs);
      pairs.forEach(([key, value]) => { if (value !== undefined) feedsPrev[key] = value; });
      rememberFeeds();
      landed = true;
    });
    // One envelope carries every source's agents and limits (API v1).
    let failure = null; let read = null;
    try { read = await getJson('/api/sources/v1/glance'); }
    catch (error) { failure = error; }
    if (!newest()) return;
    if (failure) readerFailedAt = Date.now(); // a failed read dates what was shown
    else { envelope = read; readerFailedAt = null; }
    if (firstRender && failure && failure.status === 401) return; // native recovery reopens the panel
    if (firstRender) await document.fonts.ready;
    await Promise.race([reads, new Promise((resolve) => setTimeout(resolve, FEED_GRACE_MS))]);
    if (!newest()) return;
    render();
    if (!landed) reads.then(() => { if (newest() && landed && !firstRender) render(); });
  }

  // The GitHub preference changed in Settings → Sources. Whatever was read before no longer
  // stands: reads still in flight are dropped, and what the panel held from GitHub (pull
  // request titles among it) is cleared at once. Off draws nothing; on, or unknown, starts
  // from no reading, so a failure shows as one.
  function githubChanged(enabled) {
    refreshGen++;
    const checking = { status: 'unavailable', attemptedAt: new Date().toISOString(), checkedAt: null, reason: 'checking', data: null };
    for (const key of ['ci', 'pulls', 'ended']) {
      if (enabled === false) { feeds[key] = OFF; feedsPrev[key] = OFF; }
      else { delete feedsPrev[key]; if (enabled === true) feeds[key] = checking; else delete feeds[key]; }
    }
    rememberFeeds();
    if (!firstRender) render();
    return refresh();
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
  const setupHost = { refresh: () => refresh(), githubChanged, native, opener: () => $('gear'), sources: () => envelope };
  function openSetup(options) { loadSetup().then((S) => S.open(setupHost, options || {})).catch(() => {}); }
  function openSources(options) { loadSetup().then((S) => S.openSources(setupHost, options || {})).catch(() => {}); }

  // ---- Appearance (loaded on demand, the same way) ----------------------------------------
  let appearanceModule = null;
  function loadAppearance() {
    if (!appearanceModule) {
      appearanceModule = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'nagi-appearance.js';
        script.onload = () => (window.NagiAppearance ? resolve(window.NagiAppearance) : reject(new Error('appearance')));
        script.onerror = () => { appearanceModule = null; reject(new Error('appearance')); };
        document.head.append(script);
      });
    }
    return appearanceModule;
  }
  const appearanceHost = {
    native, opener: () => $('gear'),
    settings: () => (envelope && envelope.settings) || null,
    // The reader's answer after a save is the truth the next render paints from.
    saved: (settings) => { if (envelope) envelope.settings = { ...settings }; },
    refresh: () => refresh(),
  };
  function openAppearance(options) { if (!window.NagiTheme) return; loadAppearance().then((A) => A.open(appearanceHost, options || {})).catch(() => {}); }

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
  // The Appearance row says what is chosen: `Violet · System`, and custom colours only when set.
  const APPEARANCE_WORDS = { system: 'System', light: 'Light', dark: 'Dark' };
  function showAppearance(theme) {
    const T = window.NagiTheme;
    const field = $('change-appearance').closest('.field');
    field.hidden = !T;
    if (!T) return;
    const t = T.normalize(theme || T.current());
    $('appearance-value').textContent = ((T.THEMES[t.name] || {}).label || t.name) + ' · ' + (APPEARANCE_WORDS[t.appearance] || 'System')
      + (Object.keys(t.colors || {}).length ? ' · custom colours' : '');
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
    showAppearance(sheet.loaded.theme);
    sheetLayer.hidden = false;
    void sheetLayer.offsetHeight; // start the transition from the closed state
    sheetLayer.dataset.open = 'true';
    panel.querySelectorAll('.pinned, .scroll, .rail').forEach((el) => { el.inert = true; });
    $('stuck-minutes').focus({ preventScroll: true });
    try {
      const value = await getJson('/api/settings');
      if (!sheet) return;
      sheet.loaded = { ...value.settings }; sheet.defaults = { ...value.defaults };
      fill(sheet.loaded);
      showAppearance(sheet.loaded.theme);
      if ((value.warnings || []).includes('settings_invalid')) showError("Settings were reset to the defaults because the saved file couldn't be read.");
    } catch {}
  }
  function showError(text) { const e = $('sheet-error'); e.textContent = text; e.hidden = false; }
  function closeSettings(options) {
    if (!sheet) return;
    instant(!options || options.instant !== false);
    const opener = sheet.opener; sheet = null;
    sheetLayer.dataset.open = 'false';
    panel.querySelectorAll('.pinned, .scroll, .rail').forEach((el) => { el.inert = false; });
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
    // Settings → Appearance: the same hand-over.
    $('change-appearance').addEventListener('click', (event) => { closeSettings({ instant: true }); openAppearance({ instant: event.detail === 0 }); });
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
    // Esc closes what is open, innermost first: the sheet, a detail, then the panel.
    if (sheet) closeSettings();
    else if (openDial || openSource || loadOpen) {
      // One Esc closes one detail: the one opened last, then the others.
      const open = { dial: !!openDial, src: !!openSource, load: loadOpen };
      const kind = open[lastOpened] ? lastOpened : ['dial', 'src', 'load'].find((k) => open[k]);
      const key = kind === 'dial' ? 'dial:' + openDial : kind === 'src' ? 'src:' + openSource : 'gauge:load';
      if (kind === 'dial') openDial = null; else if (kind === 'src') openSource = null; else loadOpen = false;
      lastOpened = openDial ? 'dial' : openSource ? 'src' : loadOpen ? 'load' : null;
      if (view) { renderDials(view.vm); renderRail(view.vm); renderGauges(); layout(); focusKey(key); }
    } else native('close');
  });
  window.addEventListener('resize', () => { if (!firstRender) layout(); });

  wireSheet();
  // Mac keeps the page loaded between opens: reopen() refreshes in place and treats the
  // next render as an open (what's new since the last look), with no reload or blank frame.
  function reopen() { if (!firstRender) opening = true; return refresh(); }
  window.NagiGlance = Object.freeze({ openSettings, refresh, reopen, openSetup, openSources, openAppearance });
  refresh();
  setInterval(refresh, POLL_MS);
})();
