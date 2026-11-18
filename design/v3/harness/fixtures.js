'use strict';
// Fixtures for the v3 design harness (serve.mjs loads this in place of nagi-auth.js).
// It answers the panel's API calls from invented data: no reader, no T3 Code, no network.
// Projects, titles, accounts and computers are fictional.
//
// ?scene= calm | asks | stuck | both | low | limitsfail | datedlimits | unreachable | never |
//         notsetup | checking | quiet | nothing | first | overflow | multi | friend | sixdials
// ?mac=1 shows the Mac density (pageZoom 0.85).   ?since=N pretends the last open was N minutes ago
// with every limit 12 points higher, so the open motion has something to show.
(() => {
  const params = new URLSearchParams(location.search);
  const scene = params.get('scene') || 'calm';
  if (params.get('mac')) { document.documentElement.style.zoom = '0.85'; document.documentElement.dataset.shell = 'mac'; }
  const NOW = Date.now();
  const MIN = 60000; const HOUR = 60 * MIN; const DAY = 24 * HOUR;
  const iso = (t) => new Date(t).toISOString();
  const ago = (minutes) => iso(NOW - minutes * MIN);
  const NO = { question: false, approval: false, blocking: false };
  const opus = { provider: 'claudeAgent', model: 'claude-opus-5-5' };
  const sol = { provider: 'codex', model: 'gpt-6.1-sol' };
  const gemini = { provider: 'antigravity', model: 'gemini-3.8-flash' };

  let seq = 0;
  function agent(title, who, o) {
    const id = o.id || 'a' + (++seq);
    const running = o.state === 'running';
    const last = o.last != null ? o.last : 0.1;
    return { id, projectId: o.project || 'p', parentId: o.parent || null, title, state: o.state, provider: who.provider, model: who.model, runId: 'run-' + id,
      startedAt: ago(o.start), lastActivityAt: ago(last), endedAt: o.end != null ? ago(o.end) : null, endedAtSource: o.end != null ? 'latestRunCompletedAt' : null,
      waitingOnYou: o.asks ? { question: true, approval: false, blocking: true } : NO,
      stuck: running && !o.asks && last >= 15, liveness: running ? (last >= 15 ? 'inactive' : 'recent') : 'recent',
      contextOnly: !!o.context, links: { desktop: 't3code://threads/demo/' + id, web: null }, children: o.children || [] };
  }

  const tree = (o) => [
    { id: 'tidepool', title: 'Tidepool', icon: { kind: 'auto' }, agents: [
      agent('Plan the offline sync release', opus, { state: 'completed', start: 58, end: 20, last: 20, context: true, children: [
        agent('Resolve sync conflicts in the notes editor', sol, { state: 'running', start: 18 }),
        agent('Resume photo uploads after a dropped connection', opus, { state: 'running', start: 7, last: o.photos != null ? o.photos : 0.2 })] })] },
    { id: 'kestrel', title: 'Kestrel API', icon: { kind: 'auto' }, agents: [
      agent('Find why the rate limiter answers 429 too early', gemini, { state: 'running', start: 41, last: o.kestrel != null ? o.kestrel : 0.05, asks: !!o.asks })] },
  ];
  const ended = () => [
    { id: 'tidepool', title: 'Tidepool', icon: { kind: 'auto' }, agents: [
      agent('Tidepool: Map the sync states', sol, { state: 'completed', start: 50, end: 31 }), agent('Tidepool: Spike CRDT libraries', sol, { state: 'completed', start: 60, end: 36 }),
      agent('Tidepool: Draft the sync protocol notes', opus, { state: 'completed', start: 70, end: 44 }), agent('Tidepool: Profile cold start', sol, { state: 'interrupted', start: 140, end: 120 }),
      agent('Tidepool: Fix the date picker on small screens', gemini, { state: 'completed', start: 200, end: 190 }), agent('Tidepool: Bump the image library', sol, { state: 'completed', start: 270, end: 260 })] },
    { id: 'kestrel', title: 'Kestrel API', icon: { kind: 'auto' }, agents: [
      agent('Load test the token bucket on staging', sol, { state: 'failed', start: 60, end: 52 }), agent('Load test the token bucket on staging', sol, { state: 'failed', start: 62, end: 55 }),
      agent('Kestrel: Add request IDs to error logs', opus, { state: 'completed', start: 150, end: 140 }), agent('Kestrel: Upgrade the Postgres driver', sol, { state: 'completed', start: 310, end: 300 }),
      agent('Kestrel: Document the pagination cursor', gemini, { state: 'completed', start: 420, end: 410 })] },
    { id: 'lantern', title: 'Lantern Docs', icon: { kind: 'auto' }, agents: [
      agent('Lantern: Rewrite the quick start', opus, { state: 'completed', start: 390, end: 380 }), agent('Lantern: Fix broken links in the API reference', gemini, { state: 'completed', start: 530, end: 520 }),
      agent('Lantern: Add a search index', sol, { state: 'completed', start: 710, end: 700 }), agent('Lantern: Regenerate the changelog', sol, { state: 'completed', start: 800, end: 790 })] },
  ];
  function counts(projects, done) {
    let running = 0; let asks = 0; let stuck = 0; let n = 0;
    const walk = (a) => { if (['running', 'queued', 'waiting'].includes(a.state)) { running++; if (a.waitingOnYou.question) asks++; if (a.stuck) stuck++; } a.children.forEach(walk); };
    projects.forEach((p) => p.agents.forEach(walk));
    done.forEach((p) => p.agents.forEach(function count(a) { if (!a.contextOnly && a.state !== 'running') n++; a.children.forEach(count); }));
    return { running, waitingOnYou: asks, stuck, ended: n };
  }
  const agents = (projects, done, o) => {
    const data = { environmentId: 'demo', omittedRows: 0, warnings: (o && o.warnings) || [], projects, ended: done, counts: counts(projects, done) };
    if (o && o.status === 'last_known') return { status: 'last_known', attemptedAt: iso(NOW), checkedAt: ago(3), reason: 'cannot_reach_t3', data };
    return { status: projects.length ? 'ok' : 'quiet', attemptedAt: iso(NOW), checkedAt: iso(NOW), reason: null, data };
  };
  const failedAgents = (status, reason) => ({ status, attemptedAt: ago(1), checkedAt: null, reason, data: null });

  // Limits. `drift` raises every percent, to stand for what the last open saw.
  const drift = 0;
  const win = (id, label, kind, left, resetsIn) => ({ id, label, kind, remainingPercent: Math.max(0, Math.min(100, left + drift)), resetsAt: iso(NOW + resetsIn), checkedAt: ago(2) });
  const ok = (accounts) => ({ status: 'ok', attemptedAt: iso(NOW), checkedAt: ago(2), reason: null, data: { accounts }, warnings: [] });
  const account = (id, label, windows, o) => ({ id, label, windows, status: 'ok', checkedAt: ago(2), reason: null, ...(o || {}) });
  const down = (reason) => ({ status: 'unavailable', attemptedAt: ago(1), checkedAt: null, reason: reason || 'probe_failed', data: null, warnings: [] });
  const silent = { status: 'unsupported', attemptedAt: iso(NOW), checkedAt: null, reason: 'preferred_direct_source', data: null, warnings: [] };
  const claude3 = (session, weekly, fable) => ok([account('claudeAgent', 'Claude 1', [win('five_hour', 'Session', 'five_hour', session, 1.7 * HOUR), win('seven_day', 'Weekly', 'weekly', weekly, 2 * DAY + 11 * HOUR)],
    { secondaryWindows: [win('seven_day_fable', 'Weekly · Fable', 'weekly', fable, 2 * DAY + 11 * HOUR)] })]);
  const codex2 = (one, two) => ok([account('codex', 'Codex 1', [win('primary', 'Weekly', 'weekly', one, 3 * DAY + 12 * HOUR)]), account('codex_secondary', 'Codex 2', [win('primary', 'Weekly', 'weekly', two, 5 * DAY + 2 * HOUR)])]);

  // Only T3 Code can open a thread; rows read from the other apps carry no link.
  const unlink = (a) => { a.links = null; a.children.forEach(unlink); };
  const source = (id, harness, label, a, limits, o) => { if (harness !== 't3' && a.data) [...a.data.projects, ...a.data.ended].forEach((p) => p.agents.forEach(unlink)); return sourceOf(id, harness, label, a, limits, o); };
  const sourceOf = (id, harness, label, a, limits, o) => ({ source: { id, harness, label, placement: (o && o.placement) || 'local' },
    capabilities: { agents: true, lineage: true, limits: true, stuckDetection: true, asksYou: true, deepLinks: true }, agents: a, limits, coverage: {}, warnings: [] });
  const t3 = (a, limits) => source('t3-local', 't3', 'This computer', a, limits);

  function sources() {
    const calmLimits = { codex: codex2(34, 67), claude: claude3(96, 91, 97) };
    switch (scene) {
      case 'asks': return [t3(agents(tree({ asks: true, kestrel: 4 }), ended()), calmLimits)];
      case 'stuck': return [t3(agents(tree({ kestrel: 17, photos: 6 }), ended()), calmLimits)];
      case 'both': return [t3(agents(tree({ asks: true, kestrel: 4, photos: 17 }), ended()), { codex: codex2(0, 67), claude: claude3(9, 72, 95) })];
      case 'low': return [t3(agents(tree({}), ended()), { codex: codex2(0, 64), claude: claude3(9, 72, 95) })];
      case 'limitsfail': return [t3(agents(tree({}), ended()), { codex: down(), claude: down('claude_login_expired') })];
      case 'datedlimits': return [t3(agents(tree({}), ended()), { codex: ok([account('codex', 'Codex 1', [win('primary', 'Weekly', 'weekly', 0, 3 * DAY)], { status: 'last_known', checkedAt: ago(40), reason: 'probe_failed' }),
        account('codex_secondary', 'Codex 2', [win('primary', 'Weekly', 'weekly', 67, 5 * DAY)])]), claude: { ...claude3(96, 91, 97), status: 'last_known', checkedAt: ago(25) } })];
      case 'unreachable': return [t3(agents(tree({ kestrel: 17 }), ended(), { status: 'last_known' }), calmLimits)];
      case 'never': return [t3(failedAgents('unavailable', 'cannot_reach_t3'), { codex: down(), claude: down() })];
      case 'notsetup': return [t3(failedAgents('not_set_up', 'not_configured'), { codex: { ...down(), status: 'not_set_up' }, claude: { ...down(), status: 'not_set_up' } })];
      case 'checking': return [t3(failedAgents('unavailable', 'checking'), {})];
      case 'quiet': return [t3(agents([], ended()), calmLimits)];
      case 'nothing': return [t3(agents([], []), calmLimits)];
      case 'partial': return [source('cc', 'claude', 'This computer', agents([], [], { warnings: ['partial_coverage'] }), { claude: claude3(96, 91, 97) })];
      case 'first': return [];
      case 'overflow': {
        const projects = tree({ kestrel: 17, photos: 6 });
        projects[0].agents[0].children.push(agent('Add tests for the merge rules', sol, { state: 'running', start: 3 }), agent('Tidepool: Re-run the migration dry run', sol, { state: 'queued', start: 1, last: 1 }));
        projects[1].agents.push(agent('Trace slow cold starts in the gateway and write up where the first request spends its time', opus, { state: 'running', start: 95, last: 2 }));
        projects.push({ id: 'lantern', title: 'Lantern Docs', icon: { kind: 'auto' }, agents: [
          agent('Rewrite the install guide for the new CLI', opus, { state: 'completed', start: 120, end: 80, last: 80, context: true, children: [
            agent('Lantern: Check every code sample still runs', sol, { state: 'running', start: 40, last: 0.3 }),
            agent('Lantern: Screenshots for the three setup paths', gemini, { state: 'running', start: 22, last: 9 })] }),
          agent('Translate the quick start', gemini, { state: 'running', start: 12, last: 0.2 })] });
        return [t3(agents(projects, ended()), { codex: codex2(34, 67), claude: claude3(41, 72, 95) })];
      }
      case 'friend': return [
        t3(agents([{ id: 'kestrel', title: 'Kestrel API', icon: { kind: 'auto' }, agents: [agent('Review the pagination coverage', opus, { state: 'running', start: 9, last: 0.05 })] }], ended()),
          { codex: ok([account('codex', 'Codex 1', [win('primary', 'Weekly', 'weekly', 87, DAY + 21 * HOUR)])]),
            claude: ok([account('claudeAgent', 'Claude 1', [win('seven_day', 'Weekly', 'weekly', 32, 2 * DAY + 11 * HOUR)], { secondaryWindows: [win('seven_day_fable', 'Weekly · Fable', 'weekly', 95, 2 * DAY + 11 * HOUR)] })]) }),
        source('cx', 'codex', 'This computer', agents([], [], { warnings: ['partial_coverage'] }), { codex: ok([account('codex-direct', 'Codex 1', [win('primary', 'Weekly', 'weekly', 87, DAY + 21 * HOUR)])]) }),
        source('cc', 'claude', 'This computer', agents([], [], { warnings: ['partial_coverage'] }), { claude: down() })];
      case 'sixdials':
      case 'multi': {
        const local = agents(tree({ asks: scene === 'multi', kestrel: scene === 'multi' ? 4 : 0.05, photos: 9 }), ended());
        const other = agents([{ id: 'ledger', title: 'Ledger', icon: { kind: 'auto' }, agents: [agent('Ledger: Quarterly close checklist', opus, { state: 'running', start: 22, last: 0.5 })] }], [], { status: 'last_known' });
        const cc = agents([{ id: 'harbor', title: 'Harbor Website', icon: { kind: 'auto' }, agents: [agent('Tidy the booking calendar keyboard paths', opus, { state: 'running', start: 12, last: 0.4 })] }], []);
        const list = [
          t3(local, { codex: codex2(0, 64), claude: silent }),
          source('cc', 'claude', 'This computer', cc, { claude: claude3(9, 72, 95) }),
          source('cx', 'codex', 'This computer', agents([], [], { warnings: ['partial_coverage'] }), { codex: scene === 'multi' ? down() : ok([account('codex-direct', 'Codex 1', [win('primary', 'Weekly', 'weekly', 12, 3 * DAY + 12 * HOUR)])]) })];
        if (scene === 'multi') list.splice(1, 0, source('t3-remote', 't3', 'Computer 2', other, { codex: silent, claude: silent }, { placement: 'tailscale' }));
        return list;
      }
      default: return [t3(agents(tree({}), ended()), calmLimits)];
    }
  }

  let settings = { stuckMinutes: 15, endedExpiryHours: 24, limitAlertPercent: 10 };
  let connected = null; // sources added through the setup sheet in this page view
  const envelope = () => ({ version: 1, dtoVersion: 2, extensions: ['nullable_links'], platform: 'linux', checkedAt: iso(NOW), settings: { ...settings }, warnings: [], sources: connected || sources() });

  const CATALOG = [['t3', 'T3 Code', true], ['claude', 'Claude Code', true], ['codex', 'Codex', true], ['cursor', 'Cursor', true, true],
    ['openbot', 'OpenBot'], ['pi', 'Pi'], ['omp', 'oh-my-pi'], ['hermes', 'Hermes'], ['openclaw', 'OpenClaw'], ['opencode', 'OpenCode']].map(([id, displayName, available, beta]) => ({
    id, displayName, available: !!available, beta: !!beta, status: available ? 'available' : 'planned', copyKey: available ? id + '_direct' : id + '_planned',
    capabilities: available ? { agents: true, lineage: id === 't3', limits: true, asksYou: id !== 'cursor', stuckDetection: id !== 'cursor', deepLinks: id === 't3' } : {} }));

  const json = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200, headers: { 'Content-Type': 'application/json' } }));
  let revision = 1;
  window.fetch = (input, init) => {
    const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
    const body = init && init.body ? JSON.parse(init.body) : null;
    if (path === '/api/sources/v1/glance') return scene === 'readerdown' ? json({ error: 'down' }, 503) : json(envelope());
    if (path === '/api/settings') {
      if (init && init.method === 'POST') settings = { ...settings, ...body };
      return json({ settings: { ...settings }, defaults: { stuckMinutes: 15, endedExpiryHours: 24, limitAlertPercent: 10 }, warnings: [] });
    }
    if (path === '/api/sources/v1') return json({ version: 1, revision, sources: envelope().sources });
    if (path === '/api/sources/v1/catalog') return json({ harnesses: CATALOG });
    if (path === '/api/sources/v1/discover') {
      const app = body.adapterIds[0];
      if (body.placement.kind === 'tailscale') return json({ candidates: [], peers: [{ peerRef: 'peer-1', label: 'Studio Mac', online: true }, { peerRef: 'peer-2', label: 'Office Linux', online: false }], warnings: [] });
      return json({ candidates: [{ harness: app, placement: 'this_computer', installed: 'yes', running: app === 't3' ? 'yes' : 'unknown', evidence: app === 't3' ? [] : ['data_found'] }], peers: [], warnings: [] });
    }
    if (path === '/api/sources/v1/test') return body.configuration.pairing === 'bad' ? json({ error: 'pairing_invalid' }, 422) : json({ testId: 'test-' + (++revision), agents: { status: 'quiet' } });
    if (path === '/api/sources/v1/connect') {
      connected = connected || sources();
      const tag = { id: 'new-' + revision, harness: 't3', label: 'This computer', placement: 'local' };
      connected.push(source(tag.id, tag.harness, tag.label, agents(tree({}), ended()), { codex: codex2(34, 67), claude: claude3(96, 91, 97) }));
      return json({ source: tag, revision: ++revision });
    }
    if (path === '/api/sources/v1/disconnect') { connected = (connected || sources()).filter((s) => s.source.id !== body.sourceId); return json({ revision: ++revision }); }
    return json({ error: 'not_found' }, 404);
  };

  // The native shells listen for height and close; here the last height is kept for the shot script.
  window.__nagi = { heights: [], closed: false };
  window.webkit = { messageHandlers: { nagiPanel: { postMessage(message) {
    const text = String(message);
    if (text.startsWith('height:')) window.__nagi.heights.push(Number(text.slice(7)));
    if (text === 'close') window.__nagi.closed = true;
  } } } };

  // ?since=N: as if the panel was last opened N minutes ago, when each limit stood 12 points higher.
  const since = Number(params.get('since'));
  try {
    if (since > 0) localStorage.setItem('nagi-last-open', String(NOW - since * MIN));
    else { localStorage.removeItem('nagi-last-open'); localStorage.removeItem('nagi-dials'); }
  } catch {}
  if (since > 0) {
    // The panel reads its remembered dials once, after the model has loaded: answer it then.
    const read = Storage.prototype.getItem;
    Storage.prototype.getItem = function (key) {
      if (key !== 'nagi-dials') return read.call(this, key);
      const before = {};
      window.NagiModel.buildSources(envelope(), { now: NOW }).vm.dials.forEach((g) => g.cells.forEach((c) => { if (c.pct > 0) before[g.key + ':' + c.w] = Math.min(100, c.pct + 12); }));
      return JSON.stringify(before);
    };
  }
})();
