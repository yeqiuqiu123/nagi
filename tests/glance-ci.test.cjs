'use strict';
// CI view-model tests: GitHub checks and deployments on rows and in the header, pull requests
// waiting on the owner, what ended agents produced, machine load, the GH rail chip and the
// link rule. Every outcome in design/ci-contract.md. Invented repositories and titles only.
process.env.TZ = 'Asia/Ho_Chi_Minh';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vmod = require('node:vm');
const M = require('../web/glance-model.js');
const C = require('../web/glance-ci.js');

const NOW = Date.parse('2026-11-12T23:05:00Z'); // 06:05 local
const at = (minutes) => new Date(NOW - minutes * 60000).toISOString();
const GIB = 1024 ** 3;
const TP = 'tidepool-labs/tidepool';
const gh = (rest) => 'https://github.com/' + TP + '/' + rest;
const ok = (data, o = {}) => ({ status: o.status || 'ok', attemptedAt: at(0), checkedAt: o.checked || at(0), reason: o.reason || null, data });
const down = (reason, o = {}) => ({ status: o.status || 'unavailable', attemptedAt: o.attempted || at(0), checkedAt: o.checked || null, reason, data: null });
const checks = (state, total, passed, failed, url = gh('pull/128')) => ok({ state, total, passed, failed, running: Math.max(0, total - passed - failed), url, updatedAt: at(1) });
const deploy = (state, environment = 'preview') => ok({ environment, state, url: gh('deployments'), updatedAt: at(2) });
const noDeploy = () => ({ status: 'quiet', attemptedAt: at(0), checkedAt: at(0), reason: null, data: null });
const row = (ids, ci, o = {}) => ({ repo: TP, branch: o.branch || 'feature/' + ids[0], agentIds: ids,
  pr: o.pr === null ? null : { number: o.pr || 128, url: gh('pull/' + (o.pr || 128)) }, ci, deploy: o.deploy || noDeploy() });
const ciFeed = (rows, o = {}) => ok({ rows, omitted: !!o.omitted }, o);

// A sources envelope with running agents r1..r3 and ended agents e1..e6, read through the real model.
function agent(id, title, state, o = {}) {
  return { id, projectId: 'p', parentId: null, title, state, provider: 'codex', model: 'gpt-6.1-sol', runId: 'r',
    startedAt: at(o.started || 10), lastActivityAt: at(0.05), endedAt: o.ended == null ? null : at(o.ended), endedAtSource: o.ended == null ? null : 'latestRunCompletedAt',
    waitingOnYou: { question: false, approval: false, blocking: false }, stuck: false, liveness: 'recent', contextOnly: !!o.context,
    links: { desktop: 't3code://threads/e/' + id, web: null }, children: o.children || [] };
}
function envelope(many) {
  const running = [{ id: 'tidepool', title: 'Tidepool', agents: [agent('r1', 'Resolve sync conflicts', 'running'),
    agent('ctx', 'Plan the release', 'completed', { context: true, ended: 30, children: [agent('r2', 'Resume photo uploads', 'running')] })] },
  { id: 'kestrel', title: 'Kestrel API', agents: [agent('r3', 'Rate limiter', 'running')] }];
  const ended = [{ id: 'tidepool', title: 'Tidepool', agents: ['e1', 'e2', 'e3', 'e4', 'e5', 'e6'].map((id, i) => agent(id, 'Ended ' + id, i === 4 ? 'failed' : 'completed', { ended: 20 + i, started: 60 })) }];
  const agents = { status: 'ok', attemptedAt: at(0), checkedAt: at(0), reason: null,
    data: { environmentId: 'e', projects: running, ended, counts: { running: 3, waitingOnYou: 0, stuck: 0, ended: 6 }, omittedRows: 0, warnings: [] } };
  const src = (id, a) => ({ source: { id, harness: 't3', label: id === 'here' ? 'This computer' : 'Computer 2', placement: 'local' }, agents: a, limits: {}, coverage: {}, warnings: [] });
  const quiet = { ...agents, status: 'quiet', data: { ...agents.data, projects: [], ended: [], counts: { running: 0, waitingOnYou: 0, stuck: 0, ended: 0 } } };
  return { version: 1, platform: 'linux', checkedAt: at(0), settings: { stuckMinutes: 15, endedExpiryHours: 24 }, warnings: [],
    sources: many ? [src('here', agents), src('other', quiet)] : [src('here', agents)] };
}
const ctxOf = (many) => { const env = envelope(many); return { now: NOW, vm: M.buildSources(env, { now: NOW }).vm }; };
const build = (feeds, ctx) => C.build(feeds, ctx || ctxOf(false));

// Every string the panel could print or say.
function strings(value, out = []) {
  if (typeof value === 'string') out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => strings(v, out));
  else if (value && typeof value === 'object') Object.entries(value).forEach(([k, v]) => { if (k !== 'href' && k !== 'key' && k !== 'state' && k !== 'kind') strings(v, out); });
  return out;
}
const REASONS = ['disabled', 'checking', 'coverage_incomplete', 'not_github', 'gh_missing', 'gh_signed_out', 'cannot_reach_github', 'rate_limited',
  'branch_unavailable', 'invalid_response', 'cannot_read_machine', 'reader_down', 'review_requested', 'changes_requested', 'ready_to_merge', 'in_progress'];
function honest(result) {
  for (const s of strings(result)) {
    for (const r of REASONS) assert.ok(!s.includes(r), 'raw code ' + r + ' in: ' + s);
    assert.ok(!/null|undefined|NaN/.test(s), 'placeholder in: ' + s);
  }
}

test('no routes at all draws nothing; a reader that never answered draws nothing either', () => {
  assert.deepEqual(build({ ci: null, pulls: null, ended: null, machine: null }),
    { available: false, byAgent: {}, header: null, pulls: null, results: null, load: null, rail: null });
  assert.equal(build({}).available, false);
  assert.equal(build({ ci: null, pulls: null, ended: null, machine: ok({ cpuLoadPercent: 10, memoryPressurePercent: 20, gpu: null }) }).available, true);
});

test('checks on a row: running, passed, failed and cancelled, each a link with a label and tooltip', () => {
  const r = build({ ci: ciFeed([
    row(['r1'], checks('running', 12, 7, 0), { pr: 131 }),
    row(['r2'], checks('failed', 12, 9, 2)),
    row(['r3'], checks('passed', 12, 12, 0), { pr: null, branch: 'main' }),
    row(['e1'], checks('cancelled', 4, 1, 0)),
  ]) });
  const running = r.byAgent.r1.ci;
  assert.deepEqual({ kind: running.kind, state: running.state, dated: running.dated }, { kind: 'ci', state: 'running', dated: false });
  assert.equal(running.f, 7 / 12);
  assert.equal(running.title, '7 of 12 finished · #131');
  assert.equal(running.label, 'Checks running, 7 of 12 finished. Pull request 131. Opens on GitHub.');
  const failed = r.byAgent.r2.ci;
  assert.equal(failed.state, 'failed');
  assert.equal(failed.title, '2 of 12 failed · #128');
  assert.equal(failed.label, 'Checks failed, 2 of 12. Pull request 128. Opens on GitHub.');
  assert.equal(failed.href, gh('pull/128'));
  assert.equal(failed.f, null);
  const passed = r.byAgent.r3.ci;
  assert.equal(passed.title, '12 of 12 passed'); // a branch with no PR: no number
  assert.equal(passed.label, 'Checks passed, 12 of 12. Opens on GitHub.');
  assert.equal(r.byAgent.e1.ci.state, 'cancelled');
  assert.equal(r.byAgent.e1.ci.label, 'Checks cancelled. Pull request 128. Opens on GitHub.');
  assert.equal(r.byAgent.r1.deploy, null);
  honest(r);
});

test('running with no checks counted yet has no arc fraction; no checks draws no mark, or the PR when there is one', () => {
  const r = build({ ci: ciFeed([
    row(['r1'], checks('running', 0, 0, 0)),
    row(['r2'], checks('none', 0, 0, 0), { pr: null }),
    row(['r3'], checks('none', 0, 0, 0), { pr: 140 }),
  ]) });
  assert.equal(r.byAgent.r1.ci.f, null);
  assert.equal(r.byAgent.r1.ci.title, 'Checks running · #128');
  assert.equal(r.byAgent.r2.ci, null);
  assert.deepEqual({ kind: r.byAgent.r3.ci.kind, state: r.byAgent.r3.ci.state, href: r.byAgent.r3.ci.href }, { kind: 'pr', state: 'open', href: gh('pull/140') });
  assert.equal(r.byAgent.r3.ci.label, 'Pull request 140, open, no checks. Opens on GitHub.');
  honest(r);
});

test('a branch without a PR links to nothing: the actions URL carries a query and is refused', () => {
  const url = 'https://github.com/' + TP + '/actions?query=branch%3Afeature%2Fx';
  const r = build({ ci: ciFeed([row(['r1'], checks('failed', 3, 1, 2, url), { pr: null })]) });
  assert.equal(r.byAgent.r1.ci.href, null);
  assert.equal(r.byAgent.r1.ci.label, 'Checks failed, 2 of 3.');
});

test('deployments map to six states; quiet is no mark; the header shows only one in flight, failed or waiting', () => {
  const states = { success: 'success', failure: 'failed', error: 'failed', queued: 'running', pending: 'running', in_progress: 'running', waiting: 'waiting', inactive: 'inactive', unknown: 'unknown' };
  for (const [raw, want] of Object.entries(states)) {
    const r = build({ ci: ciFeed([row(['r1'], checks('passed', 1, 1, 0), { deploy: deploy(raw) })]) });
    assert.equal(r.byAgent.r1.deploy.state, want, raw);
    assert.equal(r.byAgent.r1.deploy.kind, 'deploy');
    assert.equal(r.byAgent.r1.deploy.href, gh('deployments'));
    assert.equal(r.header.deploy ? r.header.deploy.state : null, ['running', 'failed', 'waiting'].includes(want) ? want : null, raw);
    honest(r);
  }
  const ok1 = build({ ci: ciFeed([row(['r1'], checks('passed', 1, 1, 0), { deploy: deploy('success') })]) }).byAgent.r1.deploy;
  assert.equal(ok1.label, 'Deployed to preview. Opens on GitHub.');
  assert.equal(ok1.title, 'preview · deployed');
  const generic = build({ ci: ciFeed([row(['r1'], checks('passed', 1, 1, 0), { deploy: deploy('waiting', 'Deployment') })]) }).byAgent.r1.deploy;
  assert.equal(generic.label, 'Deployment waiting for approval. Opens on GitHub.');
  assert.equal(build({ ci: ciFeed([row(['r1'], checks('passed', 1, 1, 0))]) }).byAgent.r1.deploy, null);
  // The loudest deployment wins the header: failed, then waiting, then deploying.
  const r = build({ ci: ciFeed([row(['r1'], checks('passed', 1, 1, 0), { deploy: deploy('in_progress') }),
    row(['r2'], checks('passed', 1, 1, 0), { deploy: deploy('waiting') }), row(['r3'], checks('passed', 1, 1, 0), { deploy: deploy('error', 'staging') })]) });
  assert.equal(r.header.deploy.state, 'failed');
  assert.equal(r.header.deploy.label, 'Deployment to staging failed. Opens on GitHub.');
});

test('one branch that could not be read is that row alone, dashed with the time it tried', () => {
  const r = build({ ci: ciFeed([
    row(['r1'], down('branch_unavailable', { attempted: at(3) })),
    row(['r2'], checks('passed', 5, 5, 0), { deploy: down('rate_limited', { attempted: at(3) }) }),
  ]) });
  const m = r.byAgent.r1.ci;
  assert.deepEqual({ state: m.state, href: m.href, f: m.f, title: m.title }, { state: 'unknown', href: null, f: null, title: "couldn't check · tried 06:02" });
  assert.equal(m.label, "Checks: couldn't check, tried 06:02.");
  assert.equal(r.byAgent.r2.deploy.state, 'unknown');
  assert.equal(r.byAgent.r2.deploy.href, null);
  assert.equal(r.header.ring.label, "Checks on 1 branch: 1 passed, 1 couldn't be checked.");
  assert.equal(r.rail, null);
  honest(r);
});

test('a row reading kept from earlier keeps its state, dated', () => {
  const r = build({ ci: ciFeed([row(['r1'], { ...checks('failed', 4, 2, 2), status: 'last_known', checkedAt: at(25), reason: 'cannot_reach_github' })]) });
  const m = r.byAgent.r1.ci;
  assert.equal(m.state, 'failed');
  assert.equal(m.dated, true);
  assert.equal(m.title, '2 of 4 failed · #128 · as of 05:40');
  assert.equal(m.label, 'Checks failed, 2 of 4. Pull request 128. As of 05:40. Opens on GitHub.');
  honest(r);
});

test('header ring: a segment count per watched branch, the red count, and the first failed row as target', () => {
  const r = build({ ci: ciFeed([
    row(['gone'], checks('failed', 3, 1, 2)), // an agent not in the list: counted, never a target
    row(['r3'], checks('passed', 2, 2, 0)),
    row(['r1', 'r2'], checks('failed', 12, 10, 2)),
    row(['e2'], checks('running', 4, 1, 0)),
    row(['e3'], checks('passed', 4, 4, 0)),
  ]) });
  assert.deepEqual(r.header.ring.segments, [{ state: 'failed', n: 2 }, { state: 'running', n: 1 }, { state: 'passed', n: 2 }]);
  assert.equal(r.header.ring.failed, 2);
  assert.equal(r.header.ring.unknown, false);
  assert.equal(r.header.target, 'r1');
  assert.equal(r.header.ring.label, 'Checks on 5 branches: 2 failed, 1 running, 2 passed.');
  assert.equal(r.byAgent.r2.ci.state, 'failed'); // every agent on the branch gets the mark
  const green = build({ ci: ciFeed([row(['r1'], checks('passed', 2, 2, 0)), row(['r2'], checks('passed', 1, 1, 0))]) });
  assert.deepEqual(green.header.ring.segments, [{ state: 'passed', n: 2 }]);
  assert.equal(green.header.ring.failed, 0);
  assert.equal(green.header.target, null);
  assert.equal(green.header.ring.label, 'Checks passed on 2 branches.');
  const running = build({ ci: ciFeed([row(['r3'], checks('running', 2, 0, 0))]) });
  assert.equal(running.header.target, 'r3');
  // A quiet discovery, or rows with no checks at all, draw no ring.
  assert.equal(build({ ci: { ...ciFeed([]), status: 'quiet' } }).header, null);
  assert.equal(build({ ci: ciFeed([row(['r1'], checks('none', 0, 0, 0), { pr: null })]) }).header, null);
});

test('not set up: off is silent; a missing or signed-out gh says what to do', () => {
  const off = build({ ci: down('disabled', { status: 'not_set_up' }), pulls: down('disabled', { status: 'not_set_up' }), ended: down('disabled', { status: 'not_set_up' }), machine: null });
  assert.equal(off.available, true);
  assert.deepEqual([off.header, off.pulls, off.results, off.rail, off.load], [null, null, null, null, null]);
  assert.deepEqual(off.byAgent, {});
  const missing = build({ ci: down('gh_missing', { status: 'not_set_up' }) }).rail;
  assert.deepEqual(missing, { state: 'absent', words: 'not set up', detail: "The GitHub CLI isn't installed on this computer.",
    said: "GitHub: not set up. The GitHub CLI isn't installed on this computer." });
  const out = build({ ci: down('gh_signed_out', { status: 'not_set_up' }), pulls: down('gh_signed_out', { status: 'not_set_up' }) });
  assert.equal(out.rail.detail, 'Sign in with gh auth login to show checks and pull requests.');
  assert.equal(out.header, null);
  assert.equal(out.pulls, null);
  honest(out);
});

test('GitHub unreachable: a dashed ring, the attempt time in the rail, no row marks and no counts', () => {
  const r = build({ ci: down('cannot_reach_github', { checked: at(40) }), pulls: down('cannot_reach_github'), ended: down('rate_limited') });
  assert.deepEqual(r.header.ring, { segments: [], failed: 0, unknown: true, dated: false, label: "Checks: couldn't check, tried 06:05." });
  assert.deepEqual(r.byAgent, {});
  assert.equal(r.rail.state, 'down');
  assert.equal(r.rail.words, "couldn't check · tried 06:05");
  assert.equal(r.rail.detail, "Couldn't reach github.com. Last read 05:25.");
  assert.deepEqual(r.pulls, { count: null, partial: false, dated: false, asOf: '', flag: null, rows: [], failed: { words: "couldn't check · tried 06:05" } });
  assert.equal(r.results.count, null);
  assert.deepEqual(r.results.failed, { words: "couldn't check · tried 06:05" });
  honest(r);
  for (const reason of ['rate_limited', 'invalid_response', 'coverage_incomplete', 'something_new']) honest(build({ ci: down(reason) }));
  // The first read in flight is not a failure: the rail says checking and nothing else is drawn.
  const first = build({ ci: down('checking'), pulls: down('checking'), ended: down('checking') });
  assert.deepEqual(first.rail, { state: 'checking', words: 'checking…', detail: '', said: 'GitHub: checking….' });
  assert.deepEqual([first.header, first.pulls, first.results], [null, null, null]);
});

test('a whole CI reading kept from earlier: grey marks, a dated ring, last seen in the rail', () => {
  const r = build({ ci: ciFeed([row(['r1'], checks('failed', 4, 2, 2)), row(['r2'], checks('passed', 1, 1, 0))], { status: 'last_known', checked: at(40), reason: 'cannot_reach_github' }) });
  assert.equal(r.byAgent.r1.ci.dated, true);
  assert.equal(r.byAgent.r1.ci.title, '2 of 4 failed · #128 · as of 05:25');
  assert.equal(r.header.ring.dated, true);
  assert.equal(r.header.ring.label, 'Checks on 2 branches: 1 failed, 1 passed. As of 05:25.');
  assert.deepEqual({ state: r.rail.state, words: r.rail.words }, { state: 'dated', words: 'last seen 05:25' });
  assert.equal(r.rail.detail, "Couldn't reach github.com. Tried 06:05.");
  honest(r);
});

test('when the reader stops answering, the last reading is shown dated, and a 404 or off stays silent', () => {
  const prev = { ci: ciFeed([row(['r1'], checks('passed', 2, 2, 0))], { checked: at(5) }), pulls: null, ended: down('disabled', { status: 'not_set_up' }),
    machine: ok({ cpuLoadPercent: 40, memoryPressurePercent: 50, gpu: null }, { checked: at(1) }) };
  const r = C.build({}, { ...ctxOf(false), prev });
  assert.equal(r.available, true);
  assert.equal(r.byAgent.r1.ci.dated, true);
  assert.equal(r.byAgent.r1.ci.title, '2 of 2 passed · #128 · as of 06:00');
  assert.equal(r.rail.state, 'dated');
  assert.equal(r.rail.detail, "Nagi's local reader isn't answering. Tried 06:05.");
  assert.equal(r.pulls, null);
  assert.equal(r.results, null);
  assert.equal(r.load.dated, true);
  assert.equal(r.load.label, 'Machine load: CPU 40%, memory 50%. As of 06:04.');
  honest(r);
  const failedBefore = C.build({ ci: undefined }, { ...ctxOf(false), prev: { ci: down('cannot_reach_github', { attempted: at(1) }) } });
  assert.equal(failedBefore.header.ring.unknown, true);
  assert.equal(failedBefore.rail.words, "couldn't check · tried 06:05");
});

test('pull requests waiting: only a successful outcome counts, partial carries a plus, rows link out', () => {
  const rows = [
    { repo: 'tidepool-labs/lantern-docs', number: 91, title: 'Add a search index', url: 'https://github.com/tidepool-labs/lantern-docs/pull/91', why: 'review_requested', ci: 'running', updatedAt: at(5) },
    { repo: 'tidepool-labs/kestrel', number: 55, title: 'Upgrade the Postgres driver', url: 'https://github.com/tidepool-labs/kestrel/pull/55', why: 'ready_to_merge', ci: 'passed', updatedAt: at(9) },
    { repo: 'tidepool-labs/kestrel', number: 56, title: 'Pull request #56', url: 'https://github.com/tidepool-labs/kestrel/pull/56', why: 'changes_requested', ci: null, updatedAt: at(9) },
    { repo: 'tidepool-labs/kestrel', number: 57, title: 'Trim the README', url: 'https://github.com/tidepool-labs/kestrel/pull/57', why: 'review_requested', ci: 'none', updatedAt: at(9) },
  ];
  const r = build({ pulls: ok({ count: 4, rows, omitted: false }) }).pulls;
  assert.equal(r.count, 4);
  assert.equal(r.flag, '4 PRs');
  assert.equal(r.partial, false);
  assert.deepEqual(r.rows.map((x) => [x.key, x.why, x.repo, x.number, x.mark && x.mark.state]),
    [['tidepool-labs/lantern-docs#91', 'review', 'lantern-docs', 91, 'running'], ['tidepool-labs/kestrel#55', 'merge', 'kestrel', 55, 'passed'],
      ['tidepool-labs/kestrel#56', 'changes', 'kestrel', 56, 'unknown'], ['tidepool-labs/kestrel#57', 'review', 'kestrel', 57, null]]);
  assert.equal(r.rows[0].href, 'https://github.com/tidepool-labs/lantern-docs/pull/91');
  assert.equal(r.rows[0].label, 'Add a search index. Waiting on your review. lantern-docs, pull request 91. Checks running. Opens on GitHub.');
  assert.equal(r.rows[1].label, 'Upgrade the Postgres driver. Ready to merge. kestrel, pull request 55. Checks passed. Opens on GitHub.');
  assert.equal(r.rows[2].mark.href, null);
  honest(r);
  assert.equal(build({ pulls: ok({ count: 1, rows: rows.slice(0, 1), omitted: false }) }).pulls.flag, '1 PR');
  const partial = build({ pulls: ok({ count: 2, rows: rows.slice(0, 2), omitted: true }) }).pulls;
  assert.deepEqual([partial.count, partial.partial, partial.flag], [2, true, '2+ PRs']);
  const one = build({ pulls: ok({ count: 1, rows: rows.slice(0, 1), omitted: true }) }).pulls;
  assert.equal(one.flag, '1+ PRs');
  const none = build({ pulls: { ...ok({ count: 0, rows: [], omitted: false }), status: 'quiet' } }).pulls;
  assert.deepEqual([none.count, none.flag, none.rows], [0, null, []]);
  const dated = build({ pulls: ok({ count: 2, rows: rows.slice(0, 2), omitted: false }, { status: 'last_known', checked: at(30), reason: 'cannot_reach_github' }) }).pulls;
  assert.deepEqual([dated.count, dated.flag, dated.dated, dated.asOf, dated.rows.length], [null, null, true, 'as of 05:35', 2]);
  assert.equal(dated.rows[0].mark.dated, true);
  // A row that isn't a PR the contract describes is left out and the count says partial.
  const odd = build({ pulls: ok({ count: 2, rows: [rows[0], { ...rows[1], why: 'mystery' }], omitted: false }) }).pulls;
  assert.deepEqual([odd.count, odd.partial, odd.flag], [1, true, '1+ PRs']);
});

test('ended results: one mark per PR, needs you first, then failed, running, passed; merged and passed is solid', () => {
  const er = (agentId, number, ci, mergeState) => ({ agentId, repo: TP, number, title: 'Pull request #' + number, url: gh('pull/' + number), ci, mergeState, updatedAt: at(20) });
  const rows = [er('e1', 119, 'passed', 'merged'), er('e2', 120, 'running', 'draft'), er('e3', 121, 'failed', 'merged'), er('e4', 122, 'passed', 'open'),
    er('e5', 123, 'failed', 'open'), er('e6', 124, 'passed', 'ready_to_merge'), er('e6', 124, 'passed', 'ready_to_merge'), er('stranger', 999, 'failed', 'open'),
    er('r1', 125, 'passed', 'merged')];
  const r = build({ ended: ok({ rows, omitted: false }) }).results;
  // `stranger` and the running agent r1 are not Ended rows here, so they are not drawn.
  assert.equal(r.count, 6);
  assert.deepEqual(r.marks.map((m) => [m.title.split(' · #')[1], m.state, m.needs || null]),
    [['124', 'passed', 'merge'], ['121', 'failed', null], ['123', 'failed', null], ['120', 'running', null], ['119', 'merged', null], ['122', 'passed', null]]);
  assert.equal(r.byAgent.e1.mark.state, 'merged');
  assert.equal(r.byAgent.e1.mark.label, 'Merged, checks passed. Pull request 119. Opens on GitHub.');
  assert.deepEqual([r.byAgent.e1.word, r.byAgent.e2.word, r.byAgent.e3.word, r.byAgent.e6.word], ['merged', 'draft', 'merged', 'merge']);
  assert.equal(r.byAgent.e3.mark.state, 'failed'); // a failed check is failed whether merged or not
  assert.equal(r.byAgent.e2.label, 'Pull request 120, a draft. Checks running. Opens on GitHub.');
  assert.equal(r.byAgent.stranger, undefined);
  assert.deepEqual(Object.keys(r.byProject), ['tidepool']);
  assert.deepEqual(r.byProject.tidepool.map((x) => [x.agentId, x.title, x.number]).slice(0, 2), [['e1', 'Ended e1', 119], ['e2', 'Ended e2', 120]]);
  assert.equal(r.partial, false);
  honest(r);
  // Several sources: the group key carries the source id, as vm.endedAll.groups[].key does.
  const ctx = ctxOf(true);
  const multi = C.build({ ended: ok({ rows, omitted: true }) }, ctx).results;
  assert.deepEqual(Object.keys(multi.byProject), ['here:tidepool']);
  assert.ok(ctx.vm.endedAll.groups.some((g) => g.key === 'here:tidepool'));
  assert.equal(multi.partial, true);
  // A PR without checks still shows, as its PR state; checks that couldn't be read are dashed.
  const plain = build({ ended: ok({ rows: [er('e1', 7, 'none', 'merged'), er('e2', 8, null, 'closed'), er('e3', 9, 'none', 'unknown')], omitted: false }) }).results;
  assert.deepEqual(plain.marks.map((m) => [m.kind, m.state]), [['pr', 'merged'], ['ci', 'unknown'], ['pr', 'open']]);
  assert.equal(plain.byAgent.e3.word, null);
  assert.equal(plain.byAgent.e2.mark.href, null);
  honest(plain);
  // Without a view model every row is kept (nothing to join against).
  assert.equal(C.build({ ended: ok({ rows, omitted: false }) }, { now: NOW }).results.count, 8);
});

test('the view model exposes what CI joins to: raw ids on running rows, every ended thread per Ended group', () => {
  const { vm } = ctxOf(false);
  assert.ok(vm.list.some((p) => p.rows.some((r) => r.id === 'r1')), 'running rows carry the raw agent id');
  assert.deepEqual(vm.endedAll.groups[0].agents.map((a) => a.id), ['e1', 'e2', 'e3', 'e4', 'e5', 'e6']);
  assert.equal(vm.endedAll.groups[0].key, 'tidepool');
});

test('machine load: two rings without a GPU, three with one; CPU may exceed 100; a null reading is dashed', () => {
  const calm = build({ machine: ok({ cpuLoadPercent: 31, memoryPressurePercent: 58, gpu: null }) }).load;
  assert.deepEqual(calm.rings, [{ key: 'cpu', pct: 31, f: 0.31, high: false }, { key: 'memory', pct: 58, f: 0.58, high: false }]);
  assert.deepEqual(calm.rows, [{ name: 'CPU', pct: '31%', more: '', value: '31%' }, { name: 'Memory', pct: '58%', more: '', value: '58%' }]);
  assert.equal(calm.label, 'Machine load: CPU 31%, memory 58%.');
  assert.equal(calm.failed, null);
  const gpu = build({ machine: ok({ cpuLoadPercent: 44, memoryPressurePercent: 63, gpu: { utilizationPercent: 12, memoryUsedBytes: Math.round(3.1 * GIB), memoryTotalBytes: 24 * GIB } }) }).load;
  assert.deepEqual(gpu.rings.map((x) => x.key), ['cpu', 'memory', 'gpu']);
  assert.deepEqual(gpu.rows[2], { name: 'GPU', pct: '12%', more: '3.1 of 24 GB', value: '12% · 3.1 of 24 GB' });
  const hot = build({ machine: ok({ cpuLoadPercent: 142.4, memoryPressurePercent: 93, gpu: { utilizationPercent: 97, memoryUsedBytes: 0, memoryTotalBytes: 24 * GIB } }) }).load;
  assert.deepEqual(hot.rings[0], { key: 'cpu', pct: 142.4, f: 1, high: true });
  assert.equal(hot.rings[1].high, true);
  assert.equal(hot.rings[2].high, true);
  assert.equal(hot.rows[0].value, '142%');
  assert.equal(hot.label, 'Machine load: CPU 142%, high, memory 93%, high, GPU 97%, high, 0 of 24 gigabytes.');
  assert.equal(build({ machine: ok({ cpuLoadPercent: 89.9, memoryPressurePercent: 90, gpu: null }) }).load.rings.map((x) => x.high).join(), 'false,true');
  const partial = build({ machine: ok({ cpuLoadPercent: 38, memoryPressurePercent: null, gpu: null }) }).load;
  assert.deepEqual(partial.rings[1], { key: 'memory', pct: null, f: null, high: false });
  assert.deepEqual(partial.rows[1], { name: 'Memory', pct: null, more: '', value: "couldn't read" });
  assert.equal(partial.label, "Machine load: CPU 38%, memory couldn't read.");
  const gpuNull = build({ machine: ok({ cpuLoadPercent: 1, memoryPressurePercent: 2, gpu: { utilizationPercent: null, memoryUsedBytes: null, memoryTotalBytes: null } }) }).load;
  assert.deepEqual(gpuNull.rings[2], { key: 'gpu', pct: null, f: null, high: false });
  assert.deepEqual(gpuNull.rows[2], { name: 'GPU', pct: null, more: '', value: "couldn't read" });
  const failed = build({ machine: down('cannot_read_machine', { attempted: at(2) }) }).load;
  assert.deepEqual(failed.rings.map((x) => [x.key, x.f]), [['cpu', null], ['memory', null]]);
  assert.deepEqual(failed.rows, []);
  assert.deepEqual(failed.failed, { words: "couldn't check · tried 06:03" });
  for (const l of [calm, gpu, hot, partial, gpuNull, failed]) honest(l);
  // Nothing at zero stands in for what wasn't read.
  for (const l of [partial, gpuNull, failed]) for (const s of strings(l)) assert.ok(!/(^|\s)0%/.test(s), s);
  assert.equal(build({ machine: null, ci: down('disabled', { status: 'not_set_up' }) }).load, null);
  assert.equal(build({ machine: down('checking'), ci: null }).load, null);
});

test('omitted anywhere makes the rail say the list is partial', () => {
  const r = build({ ci: ciFeed([row(['r1'], checks('passed', 1, 1, 0))], { omitted: true }), pulls: ok({ count: 0, rows: [], omitted: false }) });
  assert.equal(r.rail.state, 'partial');
  assert.equal(r.rail.words, 'partial list');
  const fine = build({ ci: ciFeed([row(['r1'], checks('passed', 1, 1, 0))]), pulls: ok({ count: 0, rows: [], omitted: false }) });
  assert.equal(fine.rail, null);
  const viaPulls = build({ ci: ciFeed([]), pulls: ok({ count: 0, rows: [], omitted: true }) });
  assert.equal(viaPulls.rail.state, 'partial');
});

test('only plain GitHub links pass; anything else is dropped to null', () => {
  const good = ['https://github.com/o/r', 'https://github.com/o/r/pull/12', 'https://github.com/o/r/pull/12/checks', 'https://github.com/o/r/actions/runs/123',
    'https://github.com/o/r/commit/0123456789abcdef0123456789abcdef01234567/checks', 'https://github.com/o/r/deployments', 'https://github.com/o-1/r.e_p-o/a/b/c/d/e/f'];
  for (const url of good) assert.equal(C.safeGithub(url), url, url);
  const bad = ['http://github.com/o/r', 'https://github.com.evil.example/o/r', 'https://evil.example/github.com/o/r', 'https://user@github.com/o/r',
    'https://user:pw@github.com/o/r', 'https://github.com:443/o/r', 'https://github.com/o/r?tab=checks', 'https://github.com/o/r/pull/1?', 'https://github.com/o/r#top',
    'https://github.com/o/../r', 'https://github.com/o/r/..', 'https://github.com/o/r/./x', 'https://github.com/o/r%2Fpull', 'https://github.com/o/r/a/b/c/d/e/f/g',
    'https://github.com/o/r\n', 'https://github.com/o/r/\tx', 'https://github.com/o//r', 'https://github.com/o/r/', 'https://gist.github.com/o/r',
    'https://GITHUB.com/o/r', 'javascript:alert(1)', 'https://github.com/o', 'https://github.com/', 'https://github.com/o/r\\x', 'https://github.com/o/r/a b',
    'https://github.com/o/r/' + 'x'.repeat(201), 'https://github.com/' + 'o'.repeat(40) + '/r', 'https://github.com/o_x/r', 'https://github.com/o/r/' + 'a/'.repeat(1100) + 'a',
    'https://github.com/o/r/é', '', null, 42, {}];
  for (const url of bad) assert.equal(C.safeGithub(url), null, String(url));
  const evil = 'https://github.com.evil.example/' + TP + '/pull/1';
  const r = build({ ci: ciFeed([row(['r1'], checks('failed', 2, 1, 1, evil), { pr: null, deploy: { ...deploy('success'), data: { ...deploy('success').data, url: 'http://github.com/o/r/deployments' } } })]),
    pulls: ok({ count: 1, rows: [{ repo: TP, number: 3, title: 'Tidy', url: 'https://user@github.com/o/r/pull/3', why: 'review_requested', ci: 'passed', updatedAt: at(1) }], omitted: false }) });
  assert.equal(r.byAgent.r1.ci.href, null);
  assert.ok(!r.byAgent.r1.ci.label.includes('Opens on GitHub'));
  assert.equal(r.byAgent.r1.deploy.href, null);
  assert.equal(r.pulls.rows[0].href, null);
  assert.equal(r.pulls.rows[0].mark.href, null);
});

test('a malformed outcome is a read that failed, never a count', () => {
  const r = build({ ci: { status: 'weird' }, pulls: 'nope', ended: [], machine: ok(null) });
  assert.equal(r.header.ring.unknown, true);
  assert.deepEqual(r.pulls.failed, { words: "couldn't check · tried 06:05" });
  assert.equal(r.results.count, null);
  assert.ok(r.load.failed);
  honest(r);
});

// The design harness's fixtures answer the new routes, and their agent ids join the scene's agents.
test('harness fixtures: every ?ci= and ?load= state builds, and the mixed rows join running and ended agents', async () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'design', 'v3', 'harness', 'fixtures.js'), 'utf8');
  async function scene(query) {
    const store = new Map();
    const Storage = function () {};
    Storage.prototype.getItem = (k) => (store.has(k) ? store.get(k) : null);
    Storage.prototype.setItem = (k, v) => store.set(k, String(v));
    Storage.prototype.removeItem = (k) => store.delete(k);
    const sandbox = { URL, URLSearchParams, Response, JSON, Date, Math, Promise, Object, String, Number, Array, Set, Map,
      location: { search: '?' + query, href: 'http://127.0.0.1:8000/glance-v2.html?' + query },
      document: { documentElement: { style: {}, dataset: {} } }, Storage, localStorage: new Storage() };
    sandbox.window = sandbox;
    vmod.runInNewContext(source, sandbox);
    const get = async (p) => { const res = await sandbox.window.fetch(p); return res.status === 404 ? null : (await res.json()); };
    const env = await get('/api/sources/v1/glance');
    const pick = (body, key) => (body ? body[key] : null);
    const feeds = { ci: pick(await get('/api/sources/v1/ci'), 'ci'), pulls: pick(await get('/api/sources/v1/ci/pulls'), 'pulls'),
      ended: pick(await get('/api/sources/v1/ci/ended'), 'ended'), machine: pick(await get('/api/sources/v1/machine'), 'machine') };
    const now = Date.parse(env.checkedAt);
    const vm = M.buildSources(env, { now }).vm;
    return { env, feeds, vm, sandbox, get, result: C.build(feeds, { now, vm }) };
  }
  const mixed = await scene('ci=mixed');
  const ids = new Set();
  const walk = (r) => { ids.add(r.id); r.children.forEach(walk); };
  mixed.vm.list.forEach((p) => p.rows.forEach(walk));
  const marked = Object.keys(mixed.result.byAgent);
  assert.equal(marked.length, 3);
  for (const id of marked) assert.ok(ids.has(id), 'joins a running row: ' + id);
  assert.deepEqual(Object.values(mixed.result.byAgent).map((x) => [x.ci.state, x.deploy && x.deploy.state]).sort(),
    [['failed', 'running'], ['passed', 'success'], ['running', null]]);
  assert.deepEqual(mixed.result.header.ring.segments, [{ state: 'failed', n: 1 }, { state: 'running', n: 1 }, { state: 'passed', n: 1 }]);
  assert.ok(ids.has(mixed.result.header.target));
  assert.equal(mixed.result.pulls.flag, '2 PRs');
  assert.deepEqual(mixed.result.pulls.rows.map((r) => r.why), ['review', 'merge']);
  assert.equal(mixed.result.results.count, 6);
  assert.deepEqual(mixed.result.results.marks.map((m) => m.state), ['failed', 'running', 'merged', 'merged', 'merged', 'passed']);
  assert.deepEqual(Object.keys(mixed.result.results.byProject).sort(), ['kestrel', 'lantern', 'tidepool']);
  for (const g of Object.keys(mixed.result.results.byProject)) assert.ok(mixed.vm.endedAll.groups.some((x) => x.key === g), g);
  assert.equal(mixed.result.load, null); // no ?load=: the machine route answers 404
  honest(mixed.result);
  // Ids are stable from one read to the next.
  const again = await mixed.get('/api/sources/v1/glance');
  assert.deepEqual(again.sources[0].agents.data.projects[1].agents[0].id, mixed.env.sources[0].agents.data.projects[1].agents[0].id);
  // Settings: GET and POST {enabled} echoed; turning it off makes the feeds disabled.
  const posted = await (await mixed.sandbox.window.fetch('/api/sources/v1/ci/settings', { method: 'POST', body: JSON.stringify({ enabled: false }) })).json();
  assert.deepEqual(posted, { version: 1, enabled: false });
  assert.equal((await mixed.get('/api/sources/v1/ci')).ci.reason, 'disabled');

  const expect = {
    off: (r) => { assert.equal(r.rail, null); assert.equal(r.header, null); },
    none: (r) => assert.equal(r.available, false),
    green: (r) => { assert.deepEqual(r.header.ring.segments, [{ state: 'passed', n: 3 }]); assert.equal(r.pulls.count, 0); assert.equal(r.results.count, 3); },
    down: (r) => { assert.equal(r.header.ring.unknown, true); assert.equal(r.rail.state, 'down'); assert.ok(r.rail.detail.includes('Last read')); },
    dated: (r) => { assert.equal(r.header.ring.dated, true); assert.equal(r.rail.state, 'dated'); assert.equal(r.pulls.count, null); },
    signedout: (r) => assert.equal(r.rail.detail, 'Sign in with gh auth login to show checks and pull requests.'),
    rowdown: (r) => { const s = Object.values(r.byAgent); assert.ok(s.some((x) => x.ci.state === 'unknown')); assert.ok(s.some((x) => x.deploy && x.deploy.state === 'unknown')); },
    partial: (r) => { assert.equal(r.pulls.flag, '2+ PRs'); assert.equal(r.rail.state, 'partial'); },
  };
  for (const [ci, check] of Object.entries(expect)) { const s = await scene('ci=' + ci); check(s.result); honest(s.result); }
  const loads = { calm: 2, gpu: 3, hot: 3, partial: 2, down: 2 };
  for (const [load, rings] of Object.entries(loads)) {
    const s = await scene('load=' + load);
    assert.equal(s.result.load.rings.length, rings, load);
    honest(s.result);
  }
  assert.equal((await scene('load=hot')).result.load.rows[2].value, '97% · 22.8 of 24 GB');
  assert.equal((await scene('load=gpu')).result.load.rows[2].value, '12% · 3.1 of 24 GB');
});
