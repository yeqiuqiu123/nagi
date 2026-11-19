'use strict';
// Demo data for the website's panel. This file is the only part of site/panel/ that is not
// copied from web/: it answers the panel's API calls with a fictional fixture, so the real
// glance renderer, view model and motion run unchanged in a static page.
//
// Nothing here is real. Projects, titles and account labels are invented; there is no
// network access, no T3 Code and no reader. Time runs on a virtual clock so a few minutes
// of agent work fit in a few seconds; the page around the panel says so.
//
// Scenes (?scene=…): story (default, animated), still, calm, empty, asks, stuck, offline, limits, quiet.
(() => {
  const MIN = 60000;
  const params = new URLSearchParams(location.search);
  let scene = params.get('scene') || 'story';
  // Mac density: the panel at pageZoom 0.85, by real relayout (CSS zoom), as the Mac app shows it.
  if (params.get('density') === 'mac') { document.documentElement.style.zoom = '0.85'; document.documentElement.dataset.shell = 'mac'; }
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ---- Virtual clock ---------------------------------------------------------------
  // The panel reads Date.now() for "now". The demo moves it in minutes, not real time.
  const realNow = Date.now.bind(Date);
  const S = Math.floor(realNow() / MIN) * MIN + 20000; // story start, on a minute + 20 s
  let m = 0; // virtual minutes since S
  let beatAt = realNow();
  // Seconds stay alive between beats, never more than half a minute.
  Date.now = () => S + m * MIN + Math.min(30000, realNow() - beatAt);
  const at = (minutes) => new Date(S + minutes * MIN).toISOString();
  const V = () => S + m * MIN;
  const iso = (t) => new Date(t).toISOString();

  // The website keeps nothing in the browser: the panel's one remembered value (when it was
  // last opened) lives in memory for this page view only.
  const memory = new Map();
  const store = { getItem: (k) => (memory.has(k) ? memory.get(k) : null), setItem: (k, v) => { memory.set(k, String(v)); }, removeItem: (k) => { memory.delete(k); } };
  try { Object.defineProperty(window, 'localStorage', { configurable: true, get: () => store }); } catch {}

  // Settings saved in the demo's sheet drive the fixture, as they drive the reader.
  // A visitor can try the themes; the one they save lasts until they leave the page.
  const DEFAULTS = { stuckMinutes: 15, endedExpiryHours: 24, limitAlertPercent: 10, theme: { name: 'violet', appearance: 'system', colors: {} } };
  const clone = (value) => JSON.parse(JSON.stringify(value));
  let settings = clone(DEFAULTS);

  // ---- Fictional fixture -----------------------------------------------------------
  const NO = { question: false, approval: false, blocking: false };
  const opus = { provider: 'claudeAgent', model: 'claude-opus-5-5' };
  const sol = { provider: 'codex', model: 'gpt-6.1-sol' };
  const gemini = { provider: 'antigravity', model: 'gemini-3.8-flash' };

  function agent(id, project, title, who, o) {
    const running = o.state === 'running';
    const last = o.last != null ? o.last : V() - 4000;
    const silent = V() - last;
    const stuckAt = settings.stuckMinutes * MIN;
    const stuck = running && !o.asks && silent >= stuckAt;
    return {
      id, projectId: project, parentId: o.parent || null, title, state: o.state, provider: who.provider, model: who.model,
      runId: 'run-' + id, startedAt: at(o.start), lastActivityAt: iso(last),
      endedAt: o.end != null ? at(o.end) : null, endedAtSource: o.end != null ? 'latestRunCompletedAt' : null,
      waitingOnYou: o.asks ? { question: true, approval: false, blocking: true } : NO,
      stuck, liveness: running ? (silent >= stuckAt ? 'inactive' : 'recent') : 'recent',
      contextOnly: !!o.context, links: null, children: o.children || [],
    };
  }

  // Ended in the last 24 h, per project: [title, who, state, minutes before S].
  const ENDED = {
    tidepool: { title: 'Tidepool', done: [['Plan the offline sync release', opus, 'completed', 20, null],
      ['Tidepool: Map the sync states', sol, 'completed', 31, 't-plan'], ['Tidepool: Spike CRDT libraries', sol, 'completed', 36, 't-plan'],
      ['Tidepool: Draft the sync protocol notes', opus, 'completed', 44, 't-plan'], ['Tidepool: Profile cold start', sol, 'interrupted', 120, null],
      ['Tidepool: Fix the date picker on small screens', gemini, 'completed', 190, null], ['Tidepool: Bump the image library', sol, 'completed', 260, null]] },
    kestrel: { title: 'Kestrel API', done: [['Load test the token bucket on staging', sol, 'failed', 52, null],
      ['Load test the token bucket on staging', sol, 'failed', 55, null], ['Kestrel: Add request IDs to error logs', opus, 'completed', 140, null],
      ['Kestrel: Upgrade the Postgres driver', sol, 'completed', 300, null], ['Kestrel: Document the pagination cursor', gemini, 'completed', 410, null]] },
    lantern: { title: 'Lantern Docs', done: [['Lantern: Rewrite the quick start', opus, 'completed', 380, null],
      ['Lantern: Fix broken links in the API reference', gemini, 'completed', 520, null], ['Lantern: Add a search index', sol, 'completed', 700, null]] },
  };

  function endedProjects(extra) {
    return Object.entries(ENDED).map(([id, p]) => ({ id, title: p.title, icon: { kind: 'auto' },
      agents: [...p.done.map(([title, who, state, ago, parent], i) => agent(id + '-e' + i, id, title, who,
        { state, start: -ago - 9, end: -ago, last: S - ago * MIN, parent }))
        .filter((a) => Date.parse(a.endedAt) >= V() - settings.endedExpiryHours * 3600000), ...(extra[id] || [])] }))
      .filter((p) => p.agents.length);
  }

  // The story: what each agent is doing at virtual minute m.
  function storyProjects() {
    const act2 = m >= 30;
    // Goes quiet, speaks again later. Scenes pin it to one state at the current moment.
    const k1Last = scene === 'asks' ? V() - 3 * MIN : scene === 'stuck' ? V() - (settings.stuckMinutes + 1) * MIN
      : scene === 'calm' || scene === 'empty' ? V() - 20000 : act2 ? S + 40 * MIN : S - 4 * MIN;
    const c2Last = m < 3 && scene !== 'calm' && scene !== 'empty' ? S - 3 * MIN : V() - 2000; // quiet for a moment, then speaks
    const kids = [
      agent('t-sync', 'tidepool', 'Resolve sync conflicts in the notes editor', sol, { state: 'running', start: -18, parent: 't-plan' }),
      agent('t-photos', 'tidepool', 'Resume photo uploads after a dropped connection', opus, { state: 'running', start: -7, last: c2Last, parent: 't-plan' }),
    ];
    if (act2) kids.push(agent('t-tests', 'tidepool', 'Add tests for the merge rules', sol, { state: 'running', start: act2 ? 38 : -2, parent: 't-plan' }));
    return [
      { id: 'tidepool', title: 'Tidepool', icon: { kind: 'auto' }, agents: [
        agent('t-plan', 'tidepool', 'Plan the offline sync release', opus, { state: 'completed', start: -58, end: -20, last: S - 20 * MIN, context: true, children: kids })] },
      { id: 'kestrel', title: 'Kestrel API', icon: { kind: 'auto' }, agents: [
        agent('k-limit', 'kestrel', 'Find why the rate limiter answers 429 too early', gemini, { state: 'running', start: -41, last: k1Last, asks: scene === 'asks' })] },
    ];
  }

  function counts(projects, ended) {
    let running = 0; let asks = 0; let stuck = 0; let done = 0;
    const walk = (a) => { if (a.state === 'running') { running++; if (a.waitingOnYou.question) asks++; if (a.stuck) stuck++; } a.children.forEach(walk); };
    projects.forEach((p) => p.agents.forEach(walk));
    ended.forEach((p) => p.agents.forEach(function count(a) { if (!a.contextOnly && a.state !== 'running') done++; a.children.forEach(count); }));
    return { running, waitingOnYou: asks, stuck, ended: done };
  }

  function win(id, label, kind, left, resetsIn) {
    return { id, label, kind, remainingPercent: Math.max(0, Math.round(left)), resetsAt: iso(S + resetsIn * MIN), checkedAt: iso(V() - 2 * MIN) };
  }

  function limits() {
    const checked = iso(V() - 2 * MIN);
    const ok = (accounts) => ({ status: 'ok', attemptedAt: iso(V()), checkedAt: checked, reason: null, data: { accounts }, warnings: [] });
    const account = (id, label, windows, secondary) => ({ id, label, windows, status: 'ok', checkedAt: checked, reason: null, ...(secondary ? { secondaryWindows: secondary } : {}) });
    const codex = ok([
      account('codex', 'Codex 1', [win('primary', 'Weekly', 'weekly', scene === 'calm' ? 12 : 0, 3 * 1440 + 11 * 60 + 38)]),
      account('codex_secondary', 'Codex 2', [win('primary', 'Weekly', 'weekly', 64 - m * 0.4, 5 * 1440 + 2 * 60)]),
    ]);
    const claude = scene === 'limits'
      ? { status: 'unavailable', attemptedAt: iso(V() - MIN), checkedAt: null, reason: 'probe_failed', data: null, warnings: [] }
      : ok([account('claudeAgent', 'Claude 1', [win('five_hour', 'Session', 'five_hour', 41 - m * 0.5, 3 * 60 + 12), win('seven_day', 'Weekly', 'weekly', 72 - m * 0.2, 2 * 1440 + 9 * 60)])]);
    return { codex, claude };
  }

  function envelope() {
    const projects = scene === 'quiet' ? [] : storyProjects();
    const extra = scene === 'quiet' ? { tidepool: [agent('t-plan', 'tidepool', 'Plan the offline sync release', opus, { state: 'completed', start: -58, end: -20, last: S - 20 * MIN })] } : {};
    const ended = endedProjects(extra);
    const offline = scene === 'offline';
    const data = { environmentId: 'demo', omittedRows: 0, warnings: [], projects, ended, counts: counts(projects, ended) };
    return {
      version: 1, dtoVersion: 2, extensions: ['nullable_links'], platform: 'linux', checkedAt: iso(V()),
      settings: clone(settings), warnings: [],
      sources: [{
        source: { id: 'demo', harness: 't3', label: 'This computer', placement: 'local' },
        capabilities: { agents: true, lineage: true, limits: true, stuckDetection: true, asksYou: true, deepLinks: true },
        agents: offline ? { status: 'last_known', attemptedAt: iso(V()), checkedAt: iso(V() - 3 * MIN), reason: 'cannot_reach_t3', data }
          : { status: projects.length ? 'ok' : 'quiet', attemptedAt: iso(V()), checkedAt: iso(V()), reason: null, data },
        limits: limits(),
        coverage: { agents: 'complete', lineage: 'complete', asksYou: 'complete', stuck: 'complete', deepLinks: 'complete', limits: 'account_dependent' },
        warnings: [],
      }],
    };
  }

  // ---- The panel's API, answered locally ------------------------------------------
  const json = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200, headers: { 'Content-Type': 'application/json' } }));
  // On the website, the story's first read waits until the panel is in view, so its open
  // motion plays where someone is looking. Everywhere else it answers at once.
  let opened = null;
  const firstOpen = new Promise((resolve) => { opened = resolve; });
  const holdFirst = scene === 'story' && window.parent !== window && !reducedQuery.matches && !params.has('paused');
  window.fetch = (input, init) => {
    const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
    if (path.endsWith('/api/sources/v1/glance')) {
      const answer = () => { const e = envelope(); e.settings = clone(settings); return json(e); };
      // Every read waits while the first is held (the panel also polls every 20 s).
      if (holdFirst) return firstOpen.then(answer);
      return answer();
    }
    if (path.endsWith('/api/settings')) {
      if (init && init.method === 'POST') { try { settings = { ...settings, ...JSON.parse(init.body) }; } catch {} }
      return json({ version: 2, settings: clone(settings), defaults: clone(DEFAULTS), warnings: [] });
    }
    return json({ error: 'not_in_demo' }, 404);
  };

  // The native shells listen for height and close; the site page listens instead.
  window.webkit = { messageHandlers: { nagiPanel: { postMessage(message) {
    if (window.parent !== window) window.parent.postMessage({ nagiPanel: String(message), scene }, location.origin === 'null' ? '*' : location.origin);
  } } } };

  // The open motion plays when the last look was 30 minutes or more ago.
  try { localStorage.setItem('nagi-last-open', String(S - 45 * MIN)); } catch {}

  // The demo has no sources to manage, so Settings leaves out its Sources row.
  // Its settings last only as long as the page, and the sheet says so.
  document.addEventListener('DOMContentLoaded', () => {
    const row = document.querySelector('.sources-field'); if (row) row.hidden = true;
    const lede = document.getElementById('sheet-lede'); if (lede) lede.textContent = 'In this demo, settings last until you leave the page.';
  });

  // ---- The story ---------------------------------------------------------------------
  // Act 1: open; the now line sweeps across two agents that started since the last look.
  //        A minute a beat: one agent goes quiet until it is stuck; another speaks again.
  // Act 2: half an hour later, the panel opens again; a new agent branches from its parent.
  const BEATS = [
    ...Array.from({ length: 12 }, (_, i) => ({ m: i + 1, wait: i === 0 ? 2600 : 900 })),
    { m: 42, wait: 5000, reopen: true },
    // A short calm tail after the last reveal, then the story rests (Replay appears).
    ...Array.from({ length: 1 }, (_, i) => ({ m: 43 + i, wait: 3600 })),
  ];
  let beat = 0; let timer = null; let playing = false;
  const listeners = new Set();
  const emit = () => listeners.forEach((fn) => { try { fn({ playing, beat, done: beat >= BEATS.length }); } catch {} });
  function step() {
    const b = BEATS[beat];
    if (!b) { playing = false; emit(); return; }
    timer = setTimeout(() => {
      m = b.m; beat++; beatAt = realNow();
      const G = window.NagiGlance;
      if (G) (b.reopen ? G.reopen() : G.refresh());
      emit();
      if (playing) step();
    }, b.wait);
  }
  const SCENES = new Set(['story', 'still', 'calm', 'empty', 'asks', 'stuck', 'offline', 'limits', 'quiet']);
  const api = {
    play() { opened(); if (playing || beat >= BEATS.length) return; playing = true; emit(); step(); },
    pause() { playing = false; clearTimeout(timer); emit(); },
    replay() { try { localStorage.setItem('nagi-last-open', String(S - 45 * MIN)); } catch {} location.reload(); },
    // Cut to another scene on the next frame, as the product changes state (no transition).
    setScene(name) {
      if (!SCENES.has(name)) return;
      api.pause(); scene = name; if (name === 'still') m = 12;
      if (window.NagiGlance) window.NagiGlance.refresh();
    },
    get scene() { return scene; },
    // Another scene's API answer at this same moment, so the page can quote the panel's own
    // words (through NagiModel) without changing what the panel shows.
    envelope(name) {
      if (!SCENES.has(name)) return null;
      const keep = scene; scene = name;
      try { return envelope(); } finally { scene = keep; }
    },
    on(fn) { listeners.add(fn); fn({ playing, beat, done: beat >= BEATS.length }); return () => listeners.delete(fn); },
  };
  window.NagiDemo = Object.freeze(api);

  if (scene === 'still') m = 12;
  if (scene === 'still' || scene === 'stuck' || scene === 'asks' || scene === 'offline' || scene === 'limits' || scene === 'quiet') {
    try { localStorage.removeItem('nagi-last-open'); } catch {}
  }
  // Story autoplays once the panel has drawn, unless motion is reduced or the page asks it to wait.
  if (scene === 'story') {
    if (reducedQuery.matches || params.has('paused')) { m = 12; try { localStorage.removeItem('nagi-last-open'); } catch {} }
    else window.addEventListener('message', function start(event) {
      if (event.source === window.parent && event.data && event.data.nagiDemo === 'play') api.play();
    });
    document.addEventListener('DOMContentLoaded', () => {
      if (!reducedQuery.matches && !params.has('paused') && window.parent === window) api.play();
    });
  }
})();
