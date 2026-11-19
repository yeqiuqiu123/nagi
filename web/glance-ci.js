'use strict';
// Nagi CI view model: turns the GitHub CI, pull request, ended-results and machine routes
// (design/ci-contract.md, Sources v1) into marks the panel draws without thinking. Pure; no DOM.
// Times print in local time. Nothing here invents a number: a read that failed says so with
// the time it tried, and a route this reader doesn't have draws nothing at all.
//
// NagiCI.build(feeds, ctx)
//   feeds = { ci, pulls, ended, machine }, each one of
//     Outcome  {status, attemptedAt, checkedAt, reason, data}: the route's `ci`/`pulls`/`ended`/`machine`
//     null     the route answered 404 (a reader without the feature)
//     undefined the fetch failed (the reader itself didn't answer)
//   ctx = { now, vm, prev? }
//     vm        NagiModel.buildSources(envelope).vm: `vm.list[].rows[]` (and their children) are the
//               running rows; their `id` is the raw agent id, the same string as the contract's
//               `agentIds`, with no source prefix. `vm.endedAll.groups[].agents` lists every ended
//               thread's id and title, which is what Ended results join to.
//     prev      the last feeds that did answer, { ci, pulls, ended, machine }. When a feed is
//               undefined, a previous reading is shown dated (as of its own check) and a previous
//               404 or "off" stays silent. With no previous reading, an undefined feed draws nothing.
//
// Returns
// {
//   available: bool,           // false when every feed is null (no routes): draw nothing at all
//   byAgent: { [agentId]: { ci: Mark|null, deploy: Mark|null } },   // trailing marks; look up by row id
//            // (every agent id in a CI row, so ended agents' ids may appear too)
//   header: null | {
//     ring: { segments: [{ state: 'failed'|'running'|'passed', n }], // failed, running, passed; no zeros
//             failed: int,       // red count beside the ring (0: none)
//             unknown: bool,     // the CI feed couldn't be read: a dashed ring with `?`, no segments
//             dated: bool,       // a reading kept from earlier: segments in grey
//             label },           // spoken sentence
//     deploy: Mark|null,         // only when deploying (running), failed or waiting
//     target: agentId|null },    // first failed row's agent shown in the list, else first running
//   pulls: null | {
//     count: int|null,           // only a successful outcome counts; null otherwise
//     partial: bool,             // `omitted`: the count carries `+`
//     dated: bool, asOf: 'as of HH:MM'|'',
//     flag: '1 PR'|'2 PRs'|'2+ PRs'|null,   // null when there is no count or it is 0
//     rows: [{ key, title, href, why: 'review'|'changes'|'merge', repo, number, mark: Mark|null, label }],
//     failed: null | { words } },            // `couldn't check · tried HH:MM`
//   results: null | {
//     count: int|null, partial: bool, dated: bool, asOf,
//     marks: [Mark],             // one per distinct PR: needs you, failed, running, passed/merged, rest
//     byAgent: { [agentId]: { number, word: 'merged'|'open'|'draft'|'closed'|'changes'|'merge'|null,
//                             mark: Mark|null, href, label } },
//     byProject: { [endedGroupKey]: [{ agentId, title, number, word, mark, href, label }] },
//                // keys match vm.endedAll.groups[].key; empty without vm.endedAll
//     failed: null | { words } },
//   load: null | {
//     rings: [{ key: 'cpu'|'memory'|'gpu', pct: number|null, f: 0..1|null, high: bool }],
//            // CPU outside, memory, GPU innermost and only when there is one; f null = dashed
//     rows: [{ name: 'CPU'|'Memory'|'GPU', value, pct, more }],
//            // value `31%` | `couldn't read` | `12% · 3.1 of 24 GB`; pct `12%`|null; more `3.1 of 24 GB`|''
//     dated: bool, asOf: 'as of HH:MM'|'', failed: null | { words }, label },
//   rail: null | { state: 'absent'|'down'|'checking'|'dated'|'partial', words, detail, said },
//            // what the `GH` chip says; null when GitHub is off or has nothing to explain
// }
//
// Mark = { kind: 'ci'|'deploy'|'pr', state, f: number|null, dated: bool, href: string|null, label, title,
//          needs?: 'changes'|'merge' }   // `needs` only on Ended result marks that wait on the owner
//   kind 'ci'     state passed|failed|running|cancelled|unknown|merged; f = finished share while running
//   kind 'deploy' state success|failed|running|waiting|inactive|unknown
//   kind 'pr'     state open|merged|closed|draft: a pull request with no checks, linking to the PR
//   unknown: href null, title `couldn't check · tried HH:MM`; dated: grey, title says `as of HH:MM`.
//   label is the full spoken sentence, title the short tooltip. href passes safeGithub() or is null.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.NagiCI = api;
})(typeof self !== 'undefined' ? self : this, function () {
  const ms = (iso) => { const t = typeof iso === 'string' ? Date.parse(iso) : NaN; return Number.isFinite(t) ? t : null; };
  const pad = (n) => String(n).padStart(2, '0');
  const hm = (t) => { const d = new Date(t); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
  const obj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const int = (v) => (Number.isInteger(v) && v >= 0 ? v : null);
  const num = (v) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null);

  // ---- Links -------------------------------------------------------------------------
  // The one rule for a GitHub link, mirrored in nagi_links.github_link and
  // SourceLinks.githubLink: https, host exactly github.com, no credentials, port, query or
  // fragment, no percent signs, nothing below 33, at most 2048 characters, and a path of
  // /owner/repo alone or followed by one of the routes the panel links to: pull/<n>,
  // actions, actions/runs/<n> or deployments. GitHub's own first segments (sign-in, SSO,
  // settings) are refused whatever follows.
  const OWNER = /^[A-Za-z0-9-]{1,39}$/;
  const REPO = /^[A-Za-z0-9._-]{1,100}$/;
  const ROUTE = /^(?:pull\/[1-9][0-9]{0,18}|actions(?:\/runs\/[1-9][0-9]{0,18})?|deployments)$/;
  const RESERVED = new Set(['orgs', 'organizations', 'enterprises', 'login', 'logout', 'session', 'sessions', 'settings',
    'account', 'users', 'apps', 'marketplace', 'oauth', 'join', 'signup', 'sso', 'sponsors', 'codespaces']);
  function safeGithub(value) {
    if (typeof value !== 'string' || value.length > 2048) return null;
    // A branch with no pull request is linked to its repository's Actions page filtered by
    // branch. The filter is a query, which the shells never open, so the link goes to the
    // Actions page itself: one click short, never a dead mark.
    const actions = /^(https:\/\/github\.com\/[^/?#]+\/[^/?#]+\/actions)\?query=branch%3A[A-Za-z0-9._%+-]{1,300}$/.exec(value);
    if (actions) value = actions[1];
    for (let i = 0; i < value.length; i++) if (value.charCodeAt(i) < 33) return null;
    if (/[%?#\\@]/.test(value)) return null;
    const m = /^https:\/\/github\.com(\/.*)$/.exec(value);
    if (!m) return null;
    const [owner, repo, ...rest] = m[1].split('/').slice(1);
    if (repo === undefined || !OWNER.test(owner) || !REPO.test(repo)) return null;
    if (RESERVED.has(owner.toLowerCase()) || repo === '.' || repo === '..') return null;
    if (rest.length && !ROUTE.test(rest.join('/'))) return null;
    return 'https://github.com/' + [owner, repo, ...rest].join('/');
  }

  // ---- Feeds -------------------------------------------------------------------------
  const STATUSES = new Set(['ok', 'quiet', 'unavailable', 'last_known', 'not_set_up', 'unsupported']);
  // An undefined feed (the reader didn't answer) shows its previous reading, dated. A feed
  // last known to be absent (null) or off stays silent. With no earlier reading at all the
  // failure is kept, with the time it was tried: a read that failed is never the same as a
  // reader that has nothing to say. A malformed outcome is a read that failed.
  function resolve(feed, prev, now) {
    if (feed === null) return null;
    if (feed === undefined) {
      if (prev === null) return null;
      if (!obj(prev)) return { status: 'unavailable', attemptedAt: new Date(now).toISOString(), checkedAt: null, reason: 'reader_down', data: null };
      if ((prev.status === 'ok' || prev.status === 'quiet' || prev.status === 'last_known') && prev.data != null) {
        return { status: 'last_known', attemptedAt: new Date(now).toISOString(), checkedAt: prev.checkedAt, reason: 'reader_down', data: prev.data };
      }
      if (prev.status === 'not_set_up' || prev.status === 'unsupported') return prev;
      return { status: 'unavailable', attemptedAt: new Date(now).toISOString(), checkedAt: prev.checkedAt || null, reason: 'reader_down', data: null };
    }
    if (!obj(feed) || !STATUSES.has(feed.status)) return { status: 'unavailable', attemptedAt: new Date(now).toISOString(), checkedAt: null, reason: 'invalid_response', data: null };
    return feed;
  }
  const live = (o) => o && (o.status === 'ok' || o.status === 'quiet') && obj(o.data);
  const dated = (o) => o && o.status === 'last_known' && obj(o.data);
  const readable = (o) => live(o) || dated(o);
  const off = (o) => !o || o.status === 'not_set_up' || o.status === 'unsupported';
  const checking = (o) => o && o.status === 'unavailable' && o.reason === 'checking';
  const tried = (o, now) => "couldn't check · tried " + hm(ms(o && o.attemptedAt) != null ? ms(o.attemptedAt) : now);
  const asOf = (o) => (ms(o && o.checkedAt) != null ? 'as of ' + hm(ms(o.checkedAt)) : '');
  const failedWords = (o, now) => (checking(o) ? 'checking…' : tried(o, now));

  // ---- Marks -------------------------------------------------------------------------
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many);
  const PR = (pr) => (pr ? ' Pull request ' + pr.number + '.' : '');
  const PR_SHORT = (pr) => (pr ? ' · #' + pr.number : '');
  const opens = (href) => (href ? ' Opens on GitHub.' : '');
  // `when` is the dated suffix: '' when fresh, else `as of HH:MM`.
  function finish(mark, when) {
    if (when) { mark.dated = true; mark.title += ' · ' + when; mark.label += ' ' + when.charAt(0).toUpperCase() + when.slice(1) + '.'; }
    mark.label += opens(mark.href);
    return mark;
  }
  function unknownMark(kind, o, now, what) {
    const words = tried(o, now);
    return { kind, state: 'unknown', f: null, dated: false, href: null, title: words, label: what + ": couldn't check, tried " + hm(ms(o && o.attemptedAt) != null ? ms(o.attemptedAt) : now) + '.' };
  }
  // A checks mark from a full rollup (agent rows) or a bare state string (PR feeds).
  function checksMark(state, counts, href, pr, when, merged) {
    const c = counts || {};
    const total = int(c.total); const passed = int(c.passed); const failed = int(c.failed);
    const of = (n) => (n != null && total ? n + ' of ' + total : null);
    let title; let label; let f = null; let s = state;
    if (state === 'failed') {
      title = of(failed) ? of(failed) + ' failed' : 'Checks failed';
      label = 'Checks failed' + (of(failed) ? ', ' + of(failed) : '') + '.';
    } else if (state === 'running') {
      const done = passed != null && failed != null ? passed + failed : null;
      if (total && done != null) f = Math.min(1, done / total);
      title = of(done) ? of(done) + ' finished' : 'Checks running';
      label = 'Checks running' + (of(done) ? ', ' + of(done) + ' finished' : '') + '.';
    } else if (state === 'passed') {
      if (merged) { s = 'merged'; title = 'Merged, checks passed'; label = 'Merged, checks passed.'; }
      else { title = of(passed) ? of(passed) + ' passed' : 'Checks passed'; label = 'Checks passed' + (of(passed) ? ', ' + of(passed) : '') + '.'; }
    } else if (state === 'cancelled') {
      title = 'Checks cancelled'; label = 'Checks cancelled.';
    } else return null;
    return finish({ kind: 'ci', state: s, f, dated: false, href, title: title + PR_SHORT(pr), label: label + PR(pr) }, when);
  }
  function prMark(state, href, pr, when) {
    const word = { open: 'open', merged: 'merged', closed: 'closed', draft: 'a draft' }[state];
    return finish({ kind: 'pr', state, f: null, dated: false, href, title: 'No checks' + PR_SHORT(pr),
      label: 'Pull request ' + pr.number + ', ' + word + ', no checks.' }, when);
  }

  const DEPLOY = { success: 'success', failure: 'failed', error: 'failed', queued: 'running', pending: 'running', in_progress: 'running',
    waiting: 'waiting', inactive: 'inactive', unknown: 'unknown' };
  function deployMark(o, now, feedWhen) {
    if (!obj(o)) return null;
    if (o.status === 'quiet' || ((o.status === 'ok' || o.status === 'last_known') && o.data == null)) return null; // no deployment
    if (!readable(o)) return unknownMark('deploy', o, now, 'Deployment');
    const d = o.data;
    const state = DEPLOY[d.state] || 'unknown';
    const env = typeof d.environment === 'string' && /^[A-Za-z][A-Za-z0-9 _-]{0,39}$/.test(d.environment) && d.environment !== 'Deployment' ? d.environment : null;
    const to = env ? ' to ' + env : '';
    const said = { success: 'Deployed' + to + '.', failed: 'Deployment' + to + ' failed.', running: 'Deploying' + to + '.',
      waiting: 'Deployment' + to + ' waiting for approval.', inactive: 'Deployment' + to + ' inactive.', unknown: 'Deployment' + to + ', state unknown.' }[state];
    const short = { success: 'deployed', failed: 'failed', running: 'deploying', waiting: 'waiting for approval', inactive: 'inactive', unknown: 'state unknown' }[state];
    return finish({ kind: 'deploy', state, f: null, dated: false, href: safeGithub(d.url), title: (env || 'Deployment') + ' · ' + short, label: said },
      feedWhen || (o.status === 'last_known' ? asOf(o) : ''));
  }
  function rowChecks(row, now, feedWhen) {
    const o = row.ci;
    const pr = obj(row.pr) && int(row.pr.number) ? { number: row.pr.number, href: safeGithub(row.pr.url) } : null;
    if (!obj(o)) return null;
    const when = feedWhen || (o.status === 'last_known' ? asOf(o) : '');
    if (o.status === 'quiet' || (readable(o) && o.data.state === 'none')) return pr ? prMark('open', pr.href, pr, when) : null;
    if (!readable(o)) return unknownMark('ci', o, now, 'Checks');
    const mark = checksMark(o.data.state, o.data, safeGithub(o.data.url) || (pr && pr.href) || null, pr, when, false);
    return mark || (pr ? prMark('open', pr.href, pr, when) : null);
  }

  // ---- Joins -------------------------------------------------------------------------
  // Running rows: every row in the watch list, at any depth. Ids are raw agent ids.
  function visibleIds(vm) {
    const ids = new Set();
    const walk = (r) => { if (r && r.id != null) ids.add(String(r.id)); ((r && r.children) || []).forEach(walk); };
    ((vm && vm.list) || []).forEach((p) => (p.rows || []).forEach(walk));
    return ids;
  }
  // Ended agents from the view model's Ended groups, keyed by agent id, with the group's key
  // (the project id, prefixed with the source id when several sources are connected).
  function endedAgents(vm) {
    const out = new Map();
    for (const g of (vm && vm.endedAll && vm.endedAll.groups) || []) {
      for (const a of g.agents || []) if (!out.has(String(a.id))) out.set(String(a.id), { title: a.title, key: g.key });
    }
    return out;
  }

  // ---- Checks: rows and header ---------------------------------------------------------
  function checks(ci, now, vm) {
    const byAgent = {};
    if (!ci || off(ci) || checking(ci)) return { byAgent, header: null };
    if (!readable(ci)) {
      const words = tried(ci, now);
      return { byAgent, header: { ring: { segments: [], failed: 0, unknown: true, dated: false, label: 'Checks: ' + words.replace(' · ', ', ') + '.' }, deploy: null, target: null } };
    }
    const when = dated(ci) ? asOf(ci) : '';
    const rows = Array.isArray(ci.data.rows) ? ci.data.rows.filter(obj) : [];
    const shown = visibleIds(vm);
    const count = { failed: 0, running: 0, passed: 0, unknown: 0 };
    const failedRows = []; const runningRows = [];
    let deploy = null;
    const DEPLOY_RANK = { failed: 0, waiting: 1, running: 2 };
    for (const row of rows) {
      const ids = Array.isArray(row.agentIds) ? row.agentIds.filter((x) => typeof x === 'string') : [];
      const mark = rowChecks(row, now, when);
      const dmark = deployMark(row.deploy, now, when);
      for (const id of ids) if (!byAgent[id]) byAgent[id] = { ci: mark, deploy: dmark };
      if (mark && mark.kind === 'ci') {
        if (mark.state in count) count[mark.state]++;
        if (mark.state === 'failed') failedRows.push(ids);
        if (mark.state === 'running') runningRows.push(ids);
      }
      if (dmark && dmark.state in DEPLOY_RANK && (!deploy || DEPLOY_RANK[dmark.state] < DEPLOY_RANK[deploy.state])) deploy = dmark;
    }
    const segments = ['failed', 'running', 'passed'].filter((s) => count[s]).map((state) => ({ state, n: count[state] }));
    if (!segments.length && !deploy) return { byAgent, header: null };
    // Pressing the ring brings the first failed row into view, else the first running one.
    const pick = (list) => { for (const ids of list) { const id = ids.find((x) => !vm || shown.has(x)); if (id) return id; } return null; };
    const target = pick(failedRows) || pick(runningRows);
    const branches = count.failed + count.running + count.passed;
    const parts = [count.failed && count.failed + ' failed', count.running && count.running + ' running', count.passed && count.passed + ' passed',
      count.unknown && count.unknown + " couldn't be checked"].filter(Boolean);
    const label = segments.length
      ? (segments.length === 1 && count.passed && !count.unknown ? 'Checks passed on ' + plural(branches, 'branch', 'branches')
        : 'Checks on ' + plural(branches, 'branch', 'branches') + ': ' + parts.join(', ')) + '.' + (when ? ' ' + when.charAt(0).toUpperCase() + when.slice(1) + '.' : '')
      : '';
    return { byAgent, header: { ring: { segments, failed: count.failed, unknown: false, dated: !!when, label }, deploy, target } };
  }

  // ---- Pull requests waiting on the owner ------------------------------------------------
  const WHY = { review_requested: 'review', changes_requested: 'changes', ready_to_merge: 'merge' };
  const WHY_SAID = { review: 'Waiting on your review', changes: 'Changes requested', merge: 'Ready to merge' };
  // A PR feed's checks: a bare state string, or null when its checks couldn't be read.
  function stateMark(state, o, now, href, pr, when, merged) {
    if (state === null) return unknownMark('ci', o, now, 'Checks');
    if (state === 'none' || state === undefined) return null;
    return checksMark(state, null, href, pr, when, merged) || unknownMark('ci', o, now, 'Checks');
  }
  function pulls(o, now) {
    if (!o || off(o) || checking(o)) return null;
    if (!readable(o)) return { count: null, partial: false, dated: false, asOf: '', flag: null, rows: [], failed: { words: tried(o, now) } };
    const when = dated(o) ? asOf(o) : '';
    const raw = Array.isArray(o.data.rows) ? o.data.rows : [];
    const rows = [];
    for (const r of raw) {
      if (!obj(r) || !int(r.number) || !WHY[r.why] || typeof r.repo !== 'string' || !/^[^/]+\/[^/]+$/.test(r.repo)) continue;
      const why = WHY[r.why];
      const href = safeGithub(r.url);
      const repo = r.repo.split('/')[1];
      const title = typeof r.title === 'string' && r.title ? r.title : 'Pull request #' + r.number;
      // The row is the pull request: its mark needn't repeat the number.
      const mark = stateMark(r.ci, o, now, href, null, when, false);
      rows.push({ key: r.repo + '#' + r.number, title, href, why, repo, number: r.number, mark,
        label: title + '. ' + WHY_SAID[why] + '. ' + repo + ', pull request ' + r.number + '.' + (mark ? ' ' + mark.label.replace(/ Opens on GitHub\.$/, '') : '') + opens(href) });
    }
    const partial = o.data.omitted === true || rows.length < raw.length;
    // Only a successful outcome contributes a count to what waits on the owner.
    const count = live(o) ? rows.length : null;
    const flag = !count ? null : partial ? count + '+ PRs' : plural(count, 'PR', 'PRs');
    return { count, partial, dated: !!when, asOf: when, flag, rows, failed: null };
  }

  // ---- What finished agents produced ----------------------------------------------------
  const MERGE_WORD = { merged: 'merged', open: 'open', draft: 'draft', closed: 'closed', changes_requested: 'changes', ready_to_merge: 'merge' };
  const NEEDS = { changes_requested: 'changes', ready_to_merge: 'merge' };
  const WORD_SAID = { merged: 'merged', open: 'open', draft: 'a draft', closed: 'closed', changes: 'changes requested', merge: 'ready to merge' };
  const PR_STATE = { merged: 'merged', closed: 'closed', draft: 'draft' };
  function results(o, now, vm) {
    if (!o || off(o) || checking(o)) return null;
    if (!readable(o)) return { count: null, partial: false, dated: false, asOf: '', marks: [], byAgent: {}, byProject: {}, failed: { words: tried(o, now) } };
    const when = dated(o) ? asOf(o) : '';
    const ended = vm ? endedAgents(vm) : null;
    const raw = Array.isArray(o.data.rows) ? o.data.rows : [];
    const byAgent = {}; const byProject = {}; const prs = new Map();
    let dropped = false;
    for (const r of raw) {
      if (!obj(r) || typeof r.agentId !== 'string' || !int(r.number) || typeof r.repo !== 'string') { dropped = true; continue; }
      // Join by agent id to an Ended row; a row with no ended agent here is not drawn.
      if (ended && !ended.has(r.agentId)) continue;
      const href = safeGithub(r.url);
      const word = MERGE_WORD[r.mergeState] || null;
      const pr = { number: r.number };
      let mark = r.ci === 'none' ? prMark(PR_STATE[r.mergeState] || 'open', href, pr, when)
        : stateMark(r.ci, o, now, href, pr, when, r.mergeState === 'merged');
      if (mark && NEEDS[r.mergeState]) mark = { ...mark, needs: NEEDS[r.mergeState] };
      const label = 'Pull request ' + r.number + (word ? ', ' + WORD_SAID[word] : '') + '.' + (mark ? ' ' + mark.label.replace(/ Pull request \d+\.| Opens on GitHub\./g, '') : '') + opens(href);
      const entry = { number: r.number, word, mark, href, label };
      if (!byAgent[r.agentId]) byAgent[r.agentId] = entry;
      const key = r.repo + '#' + r.number;
      if (!prs.has(key)) prs.set(key, { mark, merge: r.mergeState });
      const agent = ended && ended.get(r.agentId);
      if (agent) (byProject[agent.key] = byProject[agent.key] || []).push({ agentId: r.agentId, title: agent.title, ...entry });
    }
    // Needs you first, then failed, running, passed (merged with it), then the rest.
    const rank = (x) => (NEEDS[x.merge] ? 0 : !x.mark ? 5 : x.mark.state === 'failed' ? 1 : x.mark.state === 'running' ? 2
      : x.mark.state === 'passed' || x.mark.state === 'merged' ? 3 : 4);
    const ordered = [...prs.values()].map((x, i) => ({ x, i })).sort((a, b) => (rank(a.x) - rank(b.x)) || (a.i - b.i)).map((e) => e.x);
    const marks = ordered.map((x) => x.mark).filter(Boolean);
    return { count: prs.size, partial: o.data.omitted === true || dropped, dated: !!when, asOf: when, marks, byAgent, byProject, failed: null };
  }

  // ---- Machine load ------------------------------------------------------------------
  const GIB = 1024 * 1024 * 1024;
  const gb = (bytes) => { const v = bytes / GIB; return v < 100 ? (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, '') : String(Math.round(v)); };
  const pctText = (p) => Math.round(p) + '%';
  function load(o, now) {
    if (!o || off(o) || checking(o)) return null;
    if (!readable(o)) {
      const words = tried(o, now);
      return { rings: [{ key: 'cpu', pct: null, f: null, high: false }, { key: 'memory', pct: null, f: null, high: false }], rows: [], dated: false, asOf: '',
        failed: { words }, label: "Machine load: couldn't check, tried " + hm(ms(o.attemptedAt) != null ? ms(o.attemptedAt) : now) + '.' };
    }
    const d = o.data;
    const ring = (key, p) => ({ key, pct: p, f: p == null ? null : Math.min(1, p / 100), high: p != null && p >= 90 });
    const cpu = num(d.cpuLoadPercent); const mem = num(d.memoryPressurePercent);
    const rings = [ring('cpu', cpu), ring('memory', mem)];
    const reading = (name, p, more) => ({ name, pct: p == null ? null : pctText(p), more: more || '',
      value: [p == null ? "couldn't read" : pctText(p), more].filter(Boolean).join(' · ') });
    const rows = [reading('CPU', cpu), reading('Memory', mem)];
    const said = [['CPU', cpu], ['memory', mem]];
    // No GPU means no third ring and no row, never a zero.
    if (obj(d.gpu)) {
      const util = num(d.gpu.utilizationPercent); const used = num(d.gpu.memoryUsedBytes); const total = num(d.gpu.memoryTotalBytes);
      rings.push(ring('gpu', util));
      const memText = used != null && total ? gb(used) + ' of ' + gb(total) + ' GB' : '';
      rows.push(reading('GPU', util, memText));
      said.push(['GPU', util, memText]);
    }
    const when = dated(o) ? asOf(o) : '';
    const label = 'Machine load: ' + said.map(([n, p, m]) => n + ' ' + (p == null ? "couldn't read" : pctText(p) + (p >= 90 ? ', high' : '')) + (m ? ', ' + m.replace(' GB', ' gigabytes') : '')).join(', ') + '.'
      + (when ? ' ' + when.charAt(0).toUpperCase() + when.slice(1) + '.' : '');
    return { rings, rows, dated: !!when, asOf: when, failed: null, label };
  }

  // ---- The GH chip on the source rail ---------------------------------------------------
  // The rail prints `GitHub` in bold before the detail, so the detail never repeats the name.
  const DOWN_DETAIL = {
    cannot_reach_github: "Couldn't reach github.com.",
    rate_limited: 'Asked by GitHub to slow down. Nagi will try again.',
    invalid_response: "Its answer couldn't be read.",
    coverage_incomplete: "Some checks couldn't be read.",
    repo_not_found: "A watched repository couldn't be found on GitHub.",
    branch_unavailable: "A watched branch couldn't be found on GitHub.",
    not_github: "A watched project isn't on GitHub.",
    reader_down: "Nagi's local reader isn't answering.",
  };
  function rail(ci, others, now) {
    if (!ci) return null;
    const make = (state, words, detail) => ({ state, words, detail, said: 'GitHub: ' + words + '.' + (detail ? ' ' + detail : '') });
    if (ci.status === 'not_set_up' || ci.status === 'unsupported') {
      if (ci.reason === 'disabled') return null; // off is silent
      if (ci.reason === 'gh_missing') return make('absent', 'not set up', "The GitHub CLI isn't installed on this computer.");
      if (ci.reason === 'gh_signed_out') return make('absent', 'not set up', 'Sign in with gh auth login to show checks and pull requests.');
      return make('absent', 'not set up', 'Not set up on this computer.');
    }
    if (checking(ci)) return make('checking', 'checking…', '');
    if (!readable(ci)) {
      const last = ms(ci.checkedAt) != null ? ' Last read ' + hm(ms(ci.checkedAt)) + '.' : '';
      return make('down', tried(ci, now), (DOWN_DETAIL[ci.reason] || "Couldn't be read.") + last);
    }
    if (dated(ci)) {
      const at = ms(ci.checkedAt);
      return make('dated', at != null ? 'last seen ' + hm(at) : 'last seen earlier', (DOWN_DETAIL[ci.reason] || "Couldn't be read.") + ' Tried ' + hm(ms(ci.attemptedAt) != null ? ms(ci.attemptedAt) : now) + '.');
    }
    const partial = [ci, ...others].some((o) => readable(o) && (o.data.omitted === true || o.reason === 'coverage_incomplete'));
    if (partial) return make('partial', 'partial list', "Some branches or pull requests couldn't be read, so counts may be higher.");
    return null;
  }

  function build(feeds, ctx) {
    feeds = feeds || {}; ctx = ctx || {};
    const now = ctx.now != null ? ctx.now : Date.now();
    const prev = ctx.prev || {};
    const f = {};
    for (const key of ['ci', 'pulls', 'ended', 'machine']) f[key] = resolve(feeds[key], prev[key], now);
    const available = ['ci', 'pulls', 'ended', 'machine'].some((k) => f[k] != null);
    if (!available) return { available: false, byAgent: {}, header: null, pulls: null, results: null, load: null, rail: null };
    const c = checks(f.ci, now, ctx.vm);
    return {
      available, byAgent: c.byAgent, header: c.header,
      pulls: pulls(f.pulls, now), results: results(f.ended, now, ctx.vm), load: load(f.machine, now),
      rail: rail(f.ci, [f.pulls, f.ended], now),
    };
  }

  return { build, safeGithub, hm };
});
