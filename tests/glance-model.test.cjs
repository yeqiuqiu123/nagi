'use strict';
// View-model tests for the glance panel: grouping, ended summary, state precedence,
// limits, settings clamping and the tray label. Fictional titles only.
process.env.TZ = 'Asia/Ho_Chi_Minh';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const M = require('../web/glance-model.js');

const NOW = Date.parse('2026-11-12T23:05:00Z'); // Fri 13 Nov 06:05 local
const at = (minutes) => new Date(NOW - minutes * 60000).toISOString();
let seq = 0;
function agent(title, state, o = {}) {
  const id = o.id || 'a' + (++seq);
  return {
    id, projectId: o.project || 'p', parentId: o.parent || null, title, state, provider: 'codex', model: o.model || 'gpt-6.1-sol', runId: 'r',
    startedAt: o.started == null ? at(10) : at(o.started), lastActivityAt: o.active == null ? at(0.05) : at(o.active),
    endedAt: o.ended == null ? null : at(o.ended), endedAtSource: o.ended == null ? null : 'latestRunCompletedAt',
    waitingOnYou: o.waiting || { question: false, approval: false, blocking: false }, stuck: o.stuck === undefined ? false : o.stuck,
    liveness: o.liveness || 'recent', contextOnly: !!o.context, links: { desktop: 't3code://threads/e/' + id, web: 'https://app.t3.codes/threads/e/' + id },
    children: o.children || [],
  };
}
function glance(projects, o = {}) {
  const counts = { running: 0, waitingOnYou: 0, stuck: 0, ended: 0, ...(o.counts || {}) };
  return { version: 2, platform: 'linux', checkedAt: new Date(NOW).toISOString(), settings: { stuckMinutes: 15, endedExpiryHours: 24, ...(o.settings || {}) }, warnings: [],
    agents: { status: o.status || 'ok', attemptedAt: o.attempted || new Date(NOW).toISOString(), checkedAt: o.checked || new Date(NOW).toISOString(), reason: o.reason || null,
      data: o.status && !['ok', 'quiet', 'last_known'].includes(o.status) ? null
        : { environmentId: 'e', projects, ended: o.ended || [], counts, omittedRows: o.omitted || 0, warnings: o.omitted ? ['rows_omitted'] : [] } } };
}
const win = (id, label, left, inHours) => ({ id, label, kind: 'weekly', remainingPercent: left, resetsAt: new Date(NOW + inHours * 3600000).toISOString(), checkedAt: at(2) });
function limits(o = {}) {
  const ok = (accounts) => ({ status: 'ok', attemptedAt: at(0), checkedAt: at(2), reason: null, warnings: [], data: { accounts } });
  return { version: 2, platform: 'linux', providers: {
    codex: o.codex || ok([{ id: 'c1', label: 'Codex 1', windows: [win('primary', 'Weekly', 67, 40)] }, { id: 'c2', label: 'Codex 2', windows: [win('primary', 'Weekly', 0, 90)] }]),
    claude: o.claude || ok([{ id: 'k1', label: 'Claude 1', windows: [win('five_hour', 'Session', 96, 1), win('seven_day', 'Weekly', 91, 40)], secondaryWindows: [win('seven_day_fable', 'Weekly · Fable', 97, 40)] }]),
  } };
}
const flat = (vm) => { const out = []; const walk = (r) => { out.push(r); r.children.forEach(walk); }; vm.projects.forEach((p) => p.rows.forEach(walk)); return out; };

test('projects order by their latest active start; siblings newest first; completed parents hold their branches', () => {
  const tree = [
    { id: 'old', title: 'Older Project', agents: [agent('Old parent', 'completed', { context: true, ended: 100, started: 200, children: [agent('Old child', 'running', { started: 180 })] })] },
    { id: 'new', title: 'Newer Project', agents: [
      agent('First top', 'running', { started: 30 }),
      agent('Parent', 'completed', { context: true, started: 60, ended: 50, children: [agent('Newer: early child', 'running', { started: 20 }), agent('Late child', 'running', { started: 5 })] }),
    ] },
  ];
  const vm = M.build(glance(tree, { counts: { running: 4 } }), limits(), { now: NOW });
  assert.deepEqual(vm.projects.map((p) => p.title), ['Newer Project', 'Older Project']);
  const rows = vm.projects[0].rows;
  assert.deepEqual(rows.map((r) => r.title), ['Parent', 'First top']); // the parent holds the newest child
  assert.equal(rows[0].kind, 'parent');
  assert.deepEqual(rows[0].meta, ['Sol', 'completed']);
  assert.deepEqual(rows[0].children.map((r) => r.title), ['Late child', 'Newer: early child']);
  assert.equal(rows[0].children[1].prefix, 'Newer:');
  assert.equal(rows[0].children[1].rest, 'early child');
  assert.equal(rows[0].children[0].depth, 2);
  assert.equal(vm.hero.num, '4'); // the count comes from the contract, never from completed parents
  assert.ok(flat(vm).filter((r) => r.kind === 'parent').every((r) => !r.silence && !r.stateWord));
});

test('state precedence: asks you outranks stuck; stuck only when stuck === true; unknown liveness never strokes', () => {
  const asksAndStuck = agent('Both', 'running', { active: 20, stuck: true, liveness: 'inactive', waiting: { question: true, approval: false, blocking: true } });
  const stuck = agent('Stuck', 'running', { active: 17, stuck: true, liveness: 'inactive', started: 210 });
  const unknown = agent('Unknown', 'running', { active: 40, stuck: null, liveness: 'unknown' });
  const childWait = agent('Waiting on child', 'running', { active: 30, stuck: false, liveness: 'child_wait' });
  const quiet = agent('Quiet', 'running', { active: 6 });
  const late = agent('Late', 'running', { active: 9 });
  const fresh = agent('Fresh', 'running', { active: 2 });
  const vm = M.build(glance([{ id: 'p', title: 'P', agents: [asksAndStuck, stuck, unknown, childWait, quiet, late, fresh] }], { counts: { running: 7, waitingOnYou: 1, stuck: 2 } }), limits(), { now: NOW });
  const by = Object.fromEntries(flat(vm).map((r) => [r.title, r]));
  assert.equal(by.Both.stateWord.cls, 'asks');
  assert.match(by.Both.stateWord.text, /^asks you · 20 m$/);
  assert.equal(by.Both.stuck, false);
  assert.equal(by.Both.silence, null); // rose and amber never share a row
  assert.equal(by.Stuck.stateWord.text, 'silent 17 m');
  assert.deepEqual(by.Stuck.meta, ['Sol', '3 h 30 m']);
  assert.deepEqual(by.Stuck.silence, { f: 1, cls: 'late' });
  assert.equal(by.Unknown.silence, null);
  assert.equal(by.Unknown.stateWord, null);
  assert.equal(by.Unknown.meta.at(-1), '40 m ago');
  assert.equal(by['Waiting on child'].silence, null);
  assert.equal(by.Quiet.silence.cls, 'quiet'); // 6/15 is past a third, under half
  assert.equal(by.Late.silence.cls, 'late'); // 9/15 is past half
  assert.equal(by.Fresh.silence.cls, 'hidden'); // under a third is not drawn
  assert.deepEqual(vm.hero.words.map((w) => w.text), ['1 asks you', '2 stuck']);
  assert.equal(vm.heroLabel, '7 running, 1 asks you, 2 stuck');
});

test('last-known rows are dated and carry no alarms, strokes or rose time', () => {
  const rows = [agent('Was stuck', 'running', { active: 20, stuck: true, liveness: 'inactive', started: 30 })];
  const g = glance([{ id: 'p', title: 'P', agents: rows }], { status: 'last_known', checked: at(3), attempted: at(0), counts: { running: 1, stuck: 1 } });
  const vm = M.build(g, limits(), { now: NOW });
  assert.equal(vm.mode, 'dated');
  assert.equal(vm.hero.alert, "Can't reach T3 Code");
  assert.deepEqual(vm.hero.subs, ['tried 06:05 · list from 06:02', 'limits from 06:03']);
  assert.equal(vm.hero.time, '');
  assert.equal(vm.hero.dim, true);
  assert.deepEqual(vm.hero.words, []);
  const r = vm.projects[0].rows[0];
  assert.equal(r.silence, null);
  assert.equal(r.stateWord, null);
  assert.deepEqual(r.meta, ['Sol', '27 m', 'last seen 06:02']);
});

test('source outcomes stay distinct', () => {
  const mode = (o) => M.build(glance([], o), limits(), { now: NOW });
  assert.equal(mode({ status: 'quiet' }).hero.num, '0');
  assert.equal(mode({ status: 'quiet' }).message, 'Nothing ran in the last 24 h.');
  // Not set up is calm and distinct from a failure: no attempt time, no alarm styling.
  const unset = mode({ status: 'not_set_up', reason: 'not_configured' });
  assert.match(unset.message, /T3 Code isn't connected on this computer/);
  assert.equal(unset.hero.alert, 'T3 Code not set up');
  assert.deepEqual(unset.hero.subs, []);
  assert.equal(unset.hero.calm, true);
  assert.equal(unset.hero.quiet, true);
  const never = mode({ status: 'unavailable', reason: 'cannot_reach_t3' });
  assert.equal(never.hero.num, '—');
  assert.equal(never.hero.quiet, true); // a quiet dash, never a 56 px slab
  assert.equal(never.hero.calm, false); // a real failure keeps its weight
  assert.equal(never.hero.alert, "Can't reach T3 Code");
  assert.deepEqual(never.hero.subs, ['tried 06:05']);
  assert.match(never.message, /hasn't read T3 Code/);
  assert.equal(mode({ status: 'unavailable', reason: 'checking' }).hero.alert, 'Checking T3 Code…');
  assert.match(mode({ status: 'unsupported', reason: 'protocol_unsupported' }).message, /isn't supported/);
  const omitted = M.build(glance([], { omitted: 2 }), limits(), { now: NOW });
  assert.equal(omitted.omitted, "2 threads couldn't be read.");
});

test('ended summary: count from the contract, thread and sub-agent split, failed and stopped listed, completed only counted', () => {
  const ended = [
    { id: 'x', title: 'X Project', agents: [agent('Parent', 'completed', { ended: 300, children: [
      agent('Probe', 'failed', { ended: 120, parent: 'pp' }), agent('Probe', 'failed', { ended: 118, parent: 'pp' }), agent('Probe', 'failed', { ended: 119, parent: 'pp' }),
      agent('Done', 'completed', { ended: 200 }), agent('Halted', 'interrupted', { ended: 60 })] })] },
    { id: 'y', title: 'No project', agents: [agent('Night job', 'completed', { ended: 600 })] },
    { id: 'z', title: 'Context Only', agents: [agent('Running parent', 'running', { context: true, children: [agent('Old done', 'completed', { ended: 10 })] })] },
  ];
  const vm = M.build(glance([], { status: 'quiet', ended, counts: { ended: 8 } }), limits(), { now: NOW });
  const e = vm.ended;
  assert.equal(e.count, 8);
  assert.equal(e.since, 'Thu 06:05');
  assert.equal(e.split, '2 threads and 6 sub-agents');
  assert.equal(e.projects, 'X Project, no project, Context Only');
  assert.deepEqual(e.groups.map((g) => g.title), ['Context Only', 'X Project', 'no project']); // latest end first
  const x = e.groups[1];
  assert.equal(x.summary, '2 completed, 3 failed, 1 stopped · 01:05–05:05');
  assert.deepEqual(x.problems.map((p) => p.title), ['Halted', '3 × Probe']);
  assert.equal(x.problems[1].meta, 'Sol · failed 04:05–04:07');
  assert.equal(x.problems[0].meta, 'Sol · stopped 05:05');
  assert.equal(e.groups[2].summary, '1 completed · Thu 20:05'); // another day keeps its weekday
  assert.equal(vm.hero.subs[0], 'nothing running since 05:55');
  assert.equal(M.build(glance([], { status: 'quiet' }), limits(), { now: NOW }).ended, null); // empty: the line is absent
});

test('ended ranges that cross days take day prefixes', () => {
  const ended = [{ id: 'x', title: 'X', agents: [agent('A', 'completed', { ended: 60 * 8 }), agent('B', 'completed', { ended: 30 })] }];
  const vm = M.build(glance([], { status: 'quiet', ended, counts: { ended: 2 } }), limits(), { now: NOW });
  assert.equal(vm.ended.groups[0].summary, '2 completed · Thu 22:05–Fri 05:35');
});

test('limits: one line per account, lowest first; model windows stay their own rows; failures never print 0', () => {
  const vm = M.build(glance([], { status: 'quiet' }), limits(), { now: NOW });
  assert.deepEqual(vm.limits.map((l) => l.name), ['Codex 2', 'Codex 1', 'Claude 1']);
  assert.equal(vm.limits[0].pct, 0);
  assert.equal(vm.limits[0].empty, true);
  assert.equal(vm.limits[0].date, 'until Tue 17 Nov 00:05'); // `empty` replaces `0% left`
  assert.equal(vm.limits[0].label, 'Codex 2: empty until Tue 17 Nov 00:05');
  const claude = vm.limits[2];
  assert.equal(claude.head, true); // several windows: the account heads its own lines
  assert.equal(claude.pct, null);
  assert.deepEqual(claude.subs.map((x) => [x.name, x.pct, x.date]), [['Weekly', 91, 'Sat 14 Nov 22:05'], ['Session', 96, 'today 07:05'], ['Weekly · Fable', 97, 'Sat 14 Nov 22:05']]);
  assert.equal(vm.limits[1].name, 'Codex 1');
  assert.equal(vm.limits[1].date, 'Sat 14 Nov 22:05'); // one window: no window name, % left, date
  const failed = M.build(glance([], { status: 'quiet' }), limits({
    codex: { status: 'unavailable', attemptedAt: at(2), checkedAt: null, reason: 'probe_failed', warnings: [], data: null },
    claude: { status: 'not_set_up', attemptedAt: at(0), checkedAt: null, reason: 'not_installed', warnings: ['invalid_window'], data: null } }), { now: NOW });
  assert.deepEqual(failed.limits.map((l) => [l.name, l.pct, l.date]), [['Codex', null, "couldn't check · tried 06:03"], ['Claude', null, 'not set up on this computer']]);
  assert.equal(failed.limitNote, "Some limit windows couldn't be read.");
  assert.equal(M.percent(0.4), 1);
  assert.equal(M.percent(99.6), 99);
  assert.equal(M.percent(0), 0);
  const dated = limits();
  dated.providers.codex.status = 'last_known';
  assert.equal(M.build(glance([], { status: 'quiet' }), dated, { now: NOW }).limits[0].stamp, 'as of 06:03'); // kept whole by the renderer
  // A limits read that fails after a good one says so once, with both times.
  const down = M.build(glance([], { status: 'quiet' }), limits(), { now: NOW, limitsDownAt: NOW });
  assert.equal(down.limitNote, "couldn't refresh · tried 06:05 · as of 06:03");
  assert.equal(down.limits[0].stamp, '');
});

test('settings clamp to the contract bounds and report the nearest allowed value', () => {
  assert.deepEqual(M.clampSetting('stuckMinutes', '0'), { value: 5, clamped: true, invalid: false });
  assert.deepEqual(M.clampSetting('endedExpiryHours', '999'), { value: 168, clamped: true, invalid: false });
  assert.deepEqual(M.clampSetting('stuckMinutes', '30'), { value: 30, clamped: false, invalid: false });
  assert.deepEqual(M.clampSetting('stuckMinutes', '7.6'), { value: 8, clamped: false, invalid: false });
  assert.deepEqual(M.clampSetting('endedExpiryHours', 'soon', 48), { value: 48, clamped: false, invalid: true });
  const html = fs.readFileSync(path.join(__dirname, '../web/glance-v2.html'), 'utf8');
  assert.match(html, /id="stuck-minutes"[^>]*min="5" max="120"/);
  assert.match(html, /id="ended-hours"[^>]*min="1" max="168"/);
  assert.doesNotMatch(fs.readFileSync(path.join(__dirname, '../web/glance-v2.js'), 'utf8'), /innerHTML/);
});

test('tray label priority matches the shared case table', () => {
  const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'tray-label-cases.json'), 'utf8'));
  for (const c of cases) {
    const g = glance([], { status: c.agents.status, reason: c.agents.reason, counts: c.agents.counts });
    const l = limits();
    if (!c.empty) l.providers.codex.data.accounts[1].windows[0].remainingPercent = 12;
    if (c.limits === 'last_known') l.providers.codex.status = 'last_known';
    if (c.limits === 'account_last_known') l.providers.codex.data.accounts[1].status = 'last_known';
    if (c.limits === 'expired') l.providers.codex.data.accounts[1].windows[0].resetsAt = at(5);
    assert.equal(M.trayLabel(g, l, NOW), c.expect, c.name);
  }
});

test('the open motion only marks rows started since the last open', () => {
  const rows = [agent('Old', 'running', { started: 90 }), agent('New', 'running', { started: 10 })];
  const vm = M.build(glance([{ id: 'p', title: 'P', agents: rows }], { counts: { running: 2 } }), limits(), { now: NOW, lastOpen: NOW - 40 * 60000 });
  assert.deepEqual(flat(vm).filter((r) => r.isNew).map((r) => r.title), ['New']);
  assert.equal(vm.newRows, 1);
  assert.equal(M.build(glance([{ id: 'p', title: 'P', agents: rows }]), limits(), { now: NOW }).newRows, 0);
});

test('queued rows are not running; quiet under a minute reads as just now', () => {
  const rows = [agent('Running', 'running', { active: 0.2 }), agent('Queued', 'queued'), agent('Starting', 'starting'), agent('Asks', 'waiting', { waiting: { question: true, approval: false, blocking: true } })];
  const vm = M.build(glance([{ id: 'p', title: 'P', agents: rows }], { counts: { running: 1, waitingOnYou: 1 } }), limits(), { now: NOW });
  const by = Object.fromEntries(flat(vm).map((r) => [r.title, r]));
  assert.equal(by.Running.pending, false);
  assert.equal(by.Queued.pending, true);
  assert.equal(by.Starting.pending, true);
  assert.equal(by.Asks.pending, false); // asks you keeps its rose node
  assert.deepEqual(by.Queued.meta, ['Sol', 'queued']);
  const calm = M.build(glance([{ id: 'p', title: 'P', agents: [agent('A', 'running', { active: 0.5 })] }], { counts: { running: 1 } }), limits(), { now: NOW });
  assert.deepEqual(calm.hero.subs, ['all active just now']);
  const slower = M.build(glance([{ id: 'p', title: 'P', agents: [agent('A', 'running', { active: 3 })] }], { counts: { running: 1 } }), limits(), { now: NOW });
  assert.deepEqual(slower.hero.subs, ['all spoke in the last 3 m']);
});

test("can't reach Nagi: a failed reader read after a good one dates everything and drops live words", () => {
  const rows = [agent('Busy', 'running', { active: 0.2, started: 30 }), agent('Asks', 'running', { waiting: { question: true, approval: false, blocking: true } })];
  const g = glance([{ id: 'p', title: 'P', agents: rows }], { checked: at(2), counts: { running: 2, waitingOnYou: 1 } });
  const vm = M.build(g, limits(), { now: NOW, readerDownAt: NOW });
  assert.equal(vm.mode, 'dated');
  assert.equal(vm.hero.dim, true);
  assert.equal(vm.hero.alert, "Can't reach Nagi");
  assert.deepEqual(vm.hero.subs, ['tried 06:05 · list from 06:03', 'limits from 06:03']);
  assert.equal(vm.hero.time, '');
  assert.deepEqual(vm.hero.words, []);
  assert.ok(flat(vm).every((r) => r.meta.at(-1) === 'last seen 06:03' && !r.stateWord && !r.silence));
  const never = M.build(null, null, { now: NOW, readerDownAt: NOW });
  assert.equal(never.hero.alert, "Can't reach Nagi");
  assert.deepEqual(never.hero.subs, ['tried 06:05']);
  assert.equal(never.message, "Nagi's local reader isn't answering.");
});

test('retained quota is dated, expired windows vanish, and omissions never claim nothing ran', () => {
  // A last-known 0 is a dated percentage, never the live `empty`.
  const dated = limits(); dated.providers.codex.status = 'last_known';
  const vm = M.build(glance([], { status: 'quiet' }), dated, { now: NOW });
  const codex2 = vm.limits.find((l) => l.name === 'Codex 2');
  assert.equal(codex2.empty, false); assert.equal(codex2.pct, 0); assert.equal(codex2.stamp, 'as of 06:03');
  // One account's own last-known state is dated by its own check, beside a fresh account.
  const partial = limits();
  Object.assign(partial.providers.codex.data.accounts[1], { status: 'last_known', checkedAt: at(40), reason: 'probe_failed' });
  const pv = M.build(glance([], { status: 'quiet' }), partial, { now: NOW });
  assert.equal(pv.limits.find((l) => l.name === 'Codex 2').stamp, 'as of 05:25');
  assert.equal(pv.limits.find((l) => l.name === 'Codex 1').stamp, '');
  Object.assign(partial.providers.codex.data.accounts[1], { status: 'unavailable', windows: [] });
  assert.deepEqual(M.build(glance([], { status: 'quiet' }), partial, { now: NOW }).limits.find((l) => l.name === 'Codex 2').date, "couldn't check · tried 06:05");
  // Windows that already reset never show; with none left, the account reads unavailable.
  const old = limits(); old.providers.codex.data.accounts[1].windows[0].resetsAt = at(5);
  const ov = M.build(glance([], { status: 'quiet' }), old, { now: NOW, readerDownAt: NOW });
  const line = ov.limits.find((l) => l.name === 'Codex 2');
  assert.equal(line.pct, null); assert.match(line.date, /^couldn't check · tried/);
  // Omitted threads: never "Nothing ran".
  const partialRead = M.build(glance([], { status: 'ok', omitted: 3 }), limits(), { now: NOW });
  assert.equal(partialRead.message, "Activity in the last 24 h couldn't be fully read.");
  assert.doesNotMatch(partialRead.message, /Nothing ran/);
});

test("project identity matches T3's projectIdentity.ts, case for case", () => {
  // tests/project-identity-cases.json is the output of T3's own projectIdentity.ts on these names
  // (four invented names were later checked against this port, which matched T3 on the rest).
  const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'project-identity-cases.json'), 'utf8'));
  assert.deepEqual(cases.Nagi, { monogram: 'NI', color: 'red' });
  assert.deepEqual(cases.KITE, { monogram: 'KE', color: 'amber' });
  for (const [name, expected] of Object.entries(cases)) assert.deepEqual(M.projectIdentity(name), expected, name);
  // Each project carries T3's icon, with the derived monogram as its fallback.
  const projects = [
    { id: 'a', title: 'Nagi', icon: { kind: 'favicon', key: 'f'.repeat(32) }, agents: [agent('A', 'running')] },
    { id: 'b', title: 'Odd', agents: [agent('B', 'running')] },
  ];
  const vm = M.build(glance(projects, { counts: { running: 2 } }), limits(), { now: NOW });
  const by = Object.fromEntries(vm.projects.map((p) => [p.title, p.icon]));
  assert.equal(by.Nagi.kind, 'favicon');
  assert.deepEqual(by.Nagi.fallback, { monogram: 'NI', color: 'red' });
  assert.equal(by.Odd.kind, 'auto');
});

test('provider brand colour is keyed by the T3 driver, never guessed', () => {
  assert.equal(M.providerKey('claudeAgent'), 'claude');
  assert.equal(M.providerKey('codex'), 'codex');
  assert.equal(M.providerKey('grok'), 'grok');
  assert.equal(M.providerKey('antigravity'), 'gemini');
  assert.equal(M.providerKey('somethingElse'), null);
  assert.equal(M.providerKey(null), null);
  assert.equal(M.providerKey('__proto__'), null);
  const claude = { ...agent('C', 'running'), provider: 'claudeAgent' };
  const vm = M.build(glance([{ id: 'p', title: 'P', agents: [claude, agent('X', 'running')] }], { counts: { running: 2 } }), limits(), { now: NOW });
  const by = Object.fromEntries(vm.projects[0].rows.map((r) => [r.title, r.provider]));
  assert.equal(by.C, 'claude');
  assert.equal(by.X, 'codex'); // the fixture agent's driver is codex
});

test('sources envelope: one source renders exactly as today; several stay source-local', () => {
  const tag = (id, label) => ({ id, harness: 't3', label, placement: 'local' });
  const g = glance([{ id: 'p', title: 'P', agents: [agent('A', 'running')] }], { counts: { running: 1 } });
  const read = (id, label, agents) => ({ source: tag(id, label), capabilities: {}, agents, limits: limits().providers, coverage: {}, warnings: [] });
  const env = (sources) => ({ version: 1, dtoVersion: 2, platform: 'linux', checkedAt: new Date(NOW).toISOString(), sources, settings: g.settings, warnings: [] });

  // Nothing connected: a calm invitation, not a failure, and no limit lines.
  const empty = M.buildSources(env([]), { now: NOW });
  assert.equal(empty.kind, 'empty');
  assert.equal(empty.vm.hero.alert, 'Nothing connected yet');
  assert.equal(empty.vm.hero.calm, true);
  assert.deepEqual(empty.vm.limits, []);

  // One source: the very same view model as today's glance.
  const single = M.buildSources(env([read('legacy-t3', 'This computer', g.agents)]), { now: NOW });
  assert.equal(single.kind, 'single');
  // The panel's composed view (dials, list, Ended, rail) is added on top of it, never in its place.
  const { dials, dialNotes, list, endedAll, rail, notes, unread, ...core } = JSON.parse(JSON.stringify(single.vm));
  assert.deepEqual(core, JSON.parse(JSON.stringify(M.build({ ...g, warnings: [] }, limits(), { now: NOW }))));
  assert.deepEqual(rail, []); // one source: no rail, no chips
  assert.ok(dials.every((d) => d.sources.length === 0)); // and no chips under the dials
  assert.equal(unread, 0);
  assert.deepEqual(list.map((p) => p.title), ['P']);

  // Two sources, one failing: counts sum only the fresh one; the failing one keeps its own truth.
  const dated = { ...g.agents, status: 'last_known', checkedAt: at(4), reason: 'cannot_reach_t3', data: { ...g.agents.data, counts: { running: 7, waitingOnYou: 0, stuck: 0, ended: 0 } } };
  const multi = M.buildSources(env([read('b', 'Computer 2', dated), read('a', 'This computer', g.agents)]), { now: NOW });
  assert.equal(multi.kind, 'multi');
  assert.equal(multi.vm.hero.num, '1');
  assert.deepEqual(multi.vm.hero.subs, ["1 of 2 sources can't be read right now"]);
  assert.deepEqual(multi.vm.groups.map((x) => x.name), ['T3 Code']);
  const [down, up] = multi.vm.groups[0].sources;
  assert.match(down.state, /^Can't reach T3 Code · tried 06:05 · list from 06:01/);
  assert.equal(up.state, '');
  assert.deepEqual(multi.vm.limitGroups.map((x) => x.label), ['T3 Code · Computer 2', 'T3 Code · This computer']);
  assert.equal(M.traySources(env([read('b', 'Computer 2', dated), read('a', 'This computer', g.agents)]), NOW), '1 · empty');
  assert.equal(M.traySources(env([]), NOW), '·');

  // Nagi's own reader failing after a good read dates everything, in every source.
  const off = M.buildSources(env([read('b', 'Computer 2', g.agents), read('a', 'This computer', g.agents)]), { now: NOW, readerDownAt: NOW });
  assert.equal(off.vm.hero.alert, "Can't reach Nagi");
  assert.ok(off.vm.groups[0].sources.every((s) => s.vm.mode === 'dated'));
});

test('setup plans one target per app and place, and connects them strictly one at a time', async () => {
  const catalog = [{ id: 't3', displayName: 'T3 Code' }, { id: 'pi', displayName: 'Pi' }];
  const targets = M.setupTargets(['t3', 'pi'], {
    t3: [{ key: 'local', label: 'This computer', defaultLabel: 'This computer' }, { key: 'peer:abc', label: 'Studio Mac', peerRef: 'abc', defaultLabel: 'Computer 2' }],
    pi: [{ key: 'local', label: 'This computer', defaultLabel: 'This computer' }],
  }, catalog);
  assert.deepEqual(targets.map((t) => [t.appName, t.placeLabel, t.remote, t.label]),
    [['T3 Code', 'This computer', false, 'This computer'], ['T3 Code', 'Studio Mac', true, 'Computer 2'], ['Pi', 'This computer', false, 'This computer']]);
  targets[2].status = 'skipped';
  let inFlight = 0; let most = 0; const calls = [];
  const connectOne = async (t) => {
    inFlight += 1; most = Math.max(most, inFlight); calls.push(t.key);
    await new Promise((r) => setTimeout(r, 5));
    inFlight -= 1;
    return t.remote ? { ok: false, code: 'pairing_invalid' } : { ok: true, source: { id: 'x', label: t.label } };
  };
  await M.connectInSequence(targets, connectOne);
  assert.equal(most, 1); // never in parallel
  assert.deepEqual(calls, ['t3|local', 't3|peer:abc']); // a skipped place never runs
  assert.deepEqual(targets.map((t) => t.status), ['connected', 'failed', 'skipped']);
  assert.equal(targets[1].error, 'pairing_invalid');
  await M.connectInSequence(targets, connectOne);
  assert.deepEqual(calls, ['t3|local', 't3|peer:abc']); // a failure waits for the owner's Try again
});

test('limits another source now measures leave no line; a direct source skips the provider it never reads', () => {
  const vm = M.build(glance([], { status: 'quiet' }), limits({
    codex: { status: 'unsupported', attemptedAt: at(0), checkedAt: null, reason: 'account_unsupported', warnings: [], data: null },
    claude: { status: 'unsupported', attemptedAt: at(0), checkedAt: null, reason: 'preferred_direct_source', warnings: [], data: null } }), { now: NOW });
  // T3's own unsupported account type still explains itself.
  assert.deepEqual(vm.limits.map((l) => [l.name, l.date]), [['Codex', 'no limits for this account type']]);
  const direct = { source: { id: 's1', harness: 'claude', label: 'This computer', placement: 'this_computer' },
    agents: { status: 'quiet', checkedAt: at(0), attemptedAt: at(0), data: { projects: [], ended: [], counts: { running: 0, waitingOnYou: 0, stuck: 0, ended: 0 }, omittedRows: 0, warnings: ['partial_coverage'] } },
    limits: { codex: { status: 'unsupported', attemptedAt: at(0), checkedAt: null, reason: 'account_unsupported', warnings: [], data: null } } };
  const one = M.buildSources({ version: 1, platform: 'linux', checkedAt: at(0), settings: { stuckMinutes: 15, endedExpiryHours: 24 }, warnings: [], sources: [direct] }, { now: NOW });
  assert.deepEqual(one.vm.limits.filter((l) => l.name === 'Codex'), []);
  // Hooks only see what happens after connecting: never "nothing ran in the last 24 h".
  assert.match(one.vm.message, /^Nothing seen from Claude Code yet/);
});

test('a direct source names itself when it fails', () => {
  const failed = { source: { id: 's1', harness: 'claude', label: 'This computer', placement: 'this_computer' },
    agents: { status: 'unavailable', reason: 'invalid_source', attemptedAt: at(0) }, limits: {} };
  const one = M.buildSources({ version: 1, platform: 'linux', checkedAt: at(0), settings: { stuckMinutes: 15, endedExpiryHours: 24 }, warnings: [], sources: [failed] }, { now: NOW });
  assert.equal(one.vm.hero.alert, "Can't reach Claude Code");
  assert.doesNotMatch(one.vm.message + one.vm.heroLabel, /T3/);
});

test('a Claude sign-in problem says what to do', () => {
  const vm = M.build(glance([], { status: 'quiet' }), limits({
    claude: { status: 'unavailable', attemptedAt: at(0), checkedAt: null, reason: 'claude_login_expired', warnings: [], data: null } }), { now: NOW });
  assert.deepEqual(vm.limits.filter((l) => l.name === 'Claude').map((l) => [l.name, l.date]), [['Claude', 'open Claude Code to sign in again']]);
});

test('a Codex sign-in problem says what to do', () => {
  const vm = M.build(glance([], { status: 'quiet' }), limits({
    codex: { status: 'unavailable', attemptedAt: at(0), checkedAt: null, reason: 'codex_usage_opt_in', warnings: [], data: null } }), { now: NOW });
  assert.deepEqual(vm.limits.filter((l) => l.name === 'Codex').map((l) => l.date), ['reconnect Codex in Settings → Sources to see limits']);
});

test('a Cursor source shows its own monthly line and nothing for providers it never reads', () => {
  const reset = new Date(NOW + 20 * 86400000).toISOString();
  const cursor = { source: { id: 's1', harness: 'cursor', label: 'This computer', placement: 'this_computer' },
    agents: { status: 'quiet', checkedAt: at(0), attemptedAt: at(0), data: { projects: [], ended: [], counts: { running: 0, waitingOnYou: 0, stuck: 0, ended: 0 }, omittedRows: 0, warnings: ['partial_coverage'] } },
    limits: { cursor: { status: 'ok', attemptedAt: at(0), checkedAt: at(0), warnings: [], data: { accounts: [
      { id: 'cursor-1', label: 'Cursor 1', status: 'ok', windows: [{ id: 'month', label: 'Month', remainingPercent: 62, resetsAt: reset, checkedAt: at(0) }], secondaryWindows: [] }] } } } };
  const one = M.buildSources({ version: 1, platform: 'linux', checkedAt: at(0), settings: { stuckMinutes: 15, endedExpiryHours: 24 }, warnings: [], sources: [cursor] }, { now: NOW });
  assert.deepEqual(one.vm.limits.map((l) => [l.name, l.pct]), [['Cursor 1', 62]]);
  // T3 never reports Cursor: no Cursor line appears there, and Codex/Claude keep theirs.
  const t3 = M.build(glance([], { status: 'quiet' }), limits({}), { now: NOW });
  assert.equal(t3.limits.some((l) => /Cursor/.test(l.name)), false);
  assert.equal(M.providerKey('claude'), 'claude'); // direct Claude rows keep Claude's colour
});

test('a Cursor count that may repeat a local T3 stays beside the total, in the panel and the tray', () => {
  const agents = (running) => ({ status: 'ok', checkedAt: at(0), attemptedAt: at(0), data: { projects: [], ended: [], counts: { running, waitingOnYou: 0, stuck: 0, ended: 0 }, omittedRows: 0, warnings: [] } });
  const env = { version: 1, platform: 'linux', checkedAt: at(0), settings: { stuckMinutes: 15, endedExpiryHours: 24 }, warnings: [], sources: [
    { source: { id: 'legacy-t3', harness: 't3', label: 'This computer', placement: 'local' }, agents: agents(1), limits: {} },
    { source: { id: 's2', harness: 'cursor', label: 'This computer', placement: 'this_computer' }, agents: agents(1), limits: {} }] };
  const multi = M.buildSources(env, { now: NOW });
  assert.equal(multi.vm.hero.num, '1');
  assert.ok(multi.vm.hero.subs.includes('1 more in Cursor, possibly the same as T3’s'));
  assert.equal(M.traySources(env, NOW), '1');
  // Without a local T3 there is nothing to repeat: Cursor counts in full.
  env.sources[0].source.placement = 'tailscale';
  assert.equal(M.buildSources(env, { now: NOW }).vm.hero.num, '2');
});

// ---- v3: dials, the status column, one list and the source rail ------------------------------
test('dials: one ring per account window, lowest account first; the tick is the time left in a known window', () => {
  const vm = M.buildSources({ version: 1, platform: 'linux', sources: [{ source: { id: 's', harness: 't3', label: 'This computer', placement: 'local' },
    agents: glance([], { status: 'quiet' }).agents, limits: limits().providers, coverage: {}, warnings: [] }], settings: { stuckMinutes: 15, endedExpiryHours: 24 }, warnings: [] }, { now: NOW }).vm;
  assert.deepEqual(vm.dials.map((d) => d.name), ['Codex 2', 'Codex 1', 'Claude 1']);
  const [empty, codex, claude] = vm.dials;
  assert.deepEqual(empty.cells.map((c) => [c.state, c.pct, c.w, c.d]), [['empty', 0, 'Weekly', 'Tue 00:05']]);
  assert.equal(empty.label, 'Codex 2: empty until Tue 17 Nov 00:05, checked 06:03.');
  assert.deepEqual(codex.cells.map((c) => [c.state, c.pct, c.d]), [['value', 67, 'Sat 22:05']]);
  // 40 of 168 hours are left in the week: the tick sits there, the arc at 67%.
  assert.ok(Math.abs(codex.cells[0].timeLeft - 40 / 168) < 1e-9);
  // Three windows stay three rings, never averaged; `Weekly · Fable` shortens to `Fable`.
  assert.deepEqual(claude.cells.map((c) => [c.w, c.pct, c.d]), [['Weekly', 91, 'Sat 22:05'], ['Session', 96, '07:05'], ['Fable', 97, 'Sat 22:05']]);
  assert.deepEqual(claude.rows.map((r) => [r.name, r.pct, r.date]), [['Weekly', 91, 'Sat 14 Nov 22:05'], ['Session', 96, 'today 07:05'], ['Weekly · Fable', 97, 'Sat 14 Nov 22:05']]);
  assert.equal(claude.about, 'checked 06:03');
  // A window whose length Nagi doesn't know, or a reset further off than the window, gets no tick.
  assert.equal(M.timeLeft('other', NOW + 3600000, NOW), null);
  assert.equal(M.timeLeft('five_hour', NOW + 9 * 3600000, NOW), null);
  assert.equal(M.timeLeft('five_hour', NOW + 2.5 * 3600000, NOW), 0.5);
});

test('dials: a failed read is a dashed ring with its time, never a value; a dated 0 is not empty; low follows the alert level', () => {
  const one = (providers, settings) => M.buildSources({ version: 1, platform: 'linux', sources: [{ source: { id: 's', harness: 't3', label: 'This computer', placement: 'local' },
    agents: glance([], { status: 'quiet' }).agents, limits: providers, coverage: {}, warnings: [] }], settings: { stuckMinutes: 15, endedExpiryHours: 24, ...(settings || {}) }, warnings: [] }, { now: NOW }).vm.dials;
  const failed = one(limits({ codex: { status: 'unavailable', attemptedAt: at(2), checkedAt: null, reason: 'probe_failed', warnings: [], data: null },
    claude: { status: 'not_set_up', attemptedAt: at(0), checkedAt: null, reason: 'not_installed', warnings: [], data: null } }).providers);
  assert.deepEqual(failed.map((d) => [d.name, d.cells[0].state, d.cells[0].pct, d.cells[0].timeLeft, d.cells[0].w, d.cells[0].d]),
    [['Codex', 'failed', null, null, "couldn't check", 'tried 06:03'], ['Claude', 'absent', null, null, 'not set up', '']]);
  assert.equal(failed[0].rows[0].date, "couldn't check · tried 06:03");
  // A sign-in the owner can fix says so, short under the ring and in full in the detail.
  const expired = one(limits({ claude: { status: 'unavailable', attemptedAt: at(1), checkedAt: null, reason: 'claude_login_expired', warnings: [], data: null } }).providers);
  const claude = expired.find((d) => d.name === 'Claude');
  assert.deepEqual([claude.cells[0].state, claude.cells[0].w, claude.rows[0].date], ['failed', 'sign in again', 'open Claude Code to sign in again']);
  // A retained 0 is a dated 0%, grey, with the time it was read: never `empty`, never low.
  const stale = limits(); stale.providers.codex.status = 'last_known';
  const dated = one(stale.providers).find((d) => d.name === 'Codex 2').cells[0];
  assert.deepEqual([dated.state, dated.pct, dated.d], ['dated', 0, 'as of 06:03']);
  // Low is the owner's own alert level (10% unless they changed it); with the alert off, the default.
  const low = (left, settings) => one(limits({ codex: { status: 'ok', attemptedAt: at(0), checkedAt: at(2), reason: null, warnings: [],
    data: { accounts: [{ id: 'c', label: 'Codex 1', windows: [win('primary', 'Weekly', left, 40)] }] } } }).providers, settings).find((d) => d.name === 'Codex 1').cells[0].state;
  assert.equal(low(10), 'low');
  assert.equal(low(11), 'value');
  assert.equal(low(25, { limitAlertPercent: 30 }), 'low');
  assert.equal(low(10, { limitAlertPercent: 'off' }), 'low');
});

test('the status column: a healthy row says only its model and run time; exceptions speak; what needs you sorts first', () => {
  const rows = [agent('Fresh', 'running', { active: 2, started: 7 }), agent('Quiet', 'running', { active: 6, started: 200 }),
    agent('Stuck', 'running', { active: 17, stuck: true, liveness: 'inactive', started: 210 }),
    agent('Asks', 'running', { active: 4, started: 41, waiting: { question: true, approval: false, blocking: true } }),
    agent('Queued', 'queued', { started: 1 }), agent('Unknown', 'running', { active: 40, stuck: null, liveness: 'unknown' })];
  const vm = M.build(glance([{ id: 'p', title: 'P', agents: rows }], { counts: { running: 5, waitingOnYou: 1, stuck: 1 } }), limits(), { now: NOW });
  const by = Object.fromEntries(flat(vm).map((r) => [r.title, r]));
  assert.deepEqual([by.Fresh.model, by.Fresh.run, by.Fresh.note], ['Sol', '7m', null]);
  // Growing silence is drawn by the row's node (6 of 15 minutes), not written.
  assert.deepEqual([by.Quiet.run, by.Quiet.note, by.Quiet.silence.f], ['3h 20m', null, 0.4]);
  assert.deepEqual(by.Stuck.note, { text: 'silent 17m', cls: 'stuck' });
  assert.deepEqual(by.Asks.note, { text: 'asks you · 4m', cls: 'asks' });
  assert.deepEqual([by.Queued.run, by.Queued.note], ['queued', null]);
  assert.deepEqual(by.Unknown.note, { text: '40m ago', cls: 'quiet' }); // unknown liveness is never called silent
  assert.deepEqual(vm.projects[0].rows.slice(0, 2).map((r) => r.title), ['Asks', 'Stuck']);
  assert.equal(M.short(45000), '45s');
  assert.equal(M.short(3 * 3600000), '3h');
  assert.equal(M.short(52 * 3600000 + 60000), '2d 4h');
});

test('several sources: one list and one Ended line, a rail that names what cannot be read, chips only where they disambiguate', () => {
  const tag = (id, harness, label) => ({ id, harness, label, placement: 'local' });
  const live = glance([{ id: 'p', title: 'Alpha', agents: [agent('A', 'running', { started: 30 })] }],
    { counts: { running: 1, ended: 3 }, ended: [{ id: 'p', title: 'Alpha', agents: [agent('Done', 'completed', { ended: 50 }), agent('Broke', 'failed', { ended: 40 }), agent('Halted', 'interrupted', { ended: 30 })] }] });
  const asking = glance([{ id: 'q', title: 'Beta', agents: [agent('B', 'running', { started: 90, active: 4, waiting: { question: true, approval: false, blocking: true } })] }], { counts: { running: 1, waitingOnYou: 1 } });
  const down = { ...live.agents, status: 'last_known', checkedAt: at(4), reason: 'cannot_reach_t3' };
  const unseen = { ...glance([], { status: 'quiet' }).agents }; unseen.data = { ...unseen.data, warnings: ['partial_coverage'] };
  const codexOnly = { codex: limits().providers.codex };
  const silent = { status: 'unsupported', attemptedAt: at(0), checkedAt: null, reason: 'preferred_direct_source', warnings: [], data: null };
  const env = { version: 1, platform: 'linux', settings: live.settings, warnings: [], sources: [
    { source: tag('a', 't3', 'This computer'), agents: live.agents, limits: limits().providers, coverage: {}, warnings: [] },
    { source: tag('b', 't3', 'Computer 2'), agents: down, limits: { codex: silent, claude: silent }, coverage: {}, warnings: [] },
    { source: tag('c', 'claude', 'This computer'), agents: asking.agents, limits: {}, coverage: {}, warnings: [] },
    { source: tag('d', 'codex', 'This computer'), agents: unseen, limits: codexOnly, coverage: {}, warnings: [] }] };
  const vm = M.buildSources(env, { now: NOW }).vm;
  // The row that asks you leads; the unreachable computer's dated rows come last.
  assert.deepEqual(vm.list.map((p) => [p.title, p.source.chip, p.dated]), [['Beta', 'CC', false], ['Alpha', 'T3', false], ['Alpha', 'T3·2', true]]);
  assert.equal(new Set(vm.list.map((p) => p.key)).size, 3);
  // Rail: a count when read, words only for an exception.
  assert.deepEqual(vm.rail.map((r) => [r.chip, r.state, r.count, r.words]),
    [['T3', 'live', 1, ''], ['T3·2', 'down', null, "can't reach · 06:05"], ['CC', 'live', 1, ''], ['CX', 'waiting', null, 'no sessions yet']]);
  assert.match(vm.rail[3].detail, /Nothing seen from Codex yet/);
  assert.equal(vm.rail[1].title, 'T3 Code · Computer 2');
  // T3 and Codex itself both read the same two Codex windows (same provider, window and reset
  // instant): each is one dial with both chips, never two rows. Claude was read by T3 only.
  const codex = vm.dials.filter((d) => d.provider === 'codex');
  assert.deepEqual(codex.map((d) => [d.name, d.cells.length, d.sources.map((t) => t.chip)]), [['Codex 2', 1, ['T3', 'CX']], ['Codex 1', 1, ['T3', 'CX']]]);
  assert.deepEqual(vm.dials.filter((d) => d.provider === 'claude').map((d) => d.sources.map((t) => t.chip)), [['T3']]);
  assert.equal(new Set(vm.dials.map((d) => d.key)).size, vm.dials.length);
  assert.match(codex[0].label, /read by T3 Code and Codex/);
  assert.equal(vm.unread, 1); // one source can't be reached: one short flag in the header
  // One Ended line: counts summed from each source's own, groups tagged with their source.
  assert.equal(vm.endedAll.count, 6);
  assert.deepEqual(vm.endedAll.totals, { completed: 2, failed: 2, stopped: 2 });
  assert.equal(vm.endedAll.problems, '2 failed, 2 stopped');
  assert.equal(vm.endedAll.span, '24 h');
  assert.deepEqual(vm.endedAll.groups.map((g) => g.source.chip).sort(), ['T3', 'T3·2']);
});

test('the same window read by two sources is one dial: the fresher reading shows, nothing is averaged, a failed read stays apart', () => {
  const tag = (id, harness) => ({ id, harness, label: 'This computer', placement: 'local' });
  const one = (left, checkedAgo, status) => ({ status: 'ok', attemptedAt: at(0), checkedAt: at(checkedAgo), reason: null, warnings: [],
    data: { accounts: [{ id: 'c', label: 'Codex 1', status: status || 'ok', checkedAt: at(checkedAgo), windows: [win('primary', 'Weekly', left, 40)] }] } });
  const env = (t3, cx, cc) => ({ version: 1, platform: 'linux', settings: { stuckMinutes: 15, endedExpiryHours: 24 }, warnings: [], sources: [
    { source: tag('a', 't3'), agents: glance([], { status: 'quiet' }).agents, limits: { codex: t3, claude: limits().providers.claude }, coverage: {}, warnings: [] },
    { source: tag('b', 'codex'), agents: glance([], { status: 'quiet' }).agents, limits: { codex: cx }, coverage: {}, warnings: [] },
    { source: tag('c', 'claude'), agents: glance([], { status: 'quiet' }).agents, limits: { claude: cc }, coverage: {}, warnings: [] }] });
  const failed = { status: 'unavailable', attemptedAt: at(2), checkedAt: null, reason: 'probe_failed', warnings: [], data: null };
  const dials = (e) => M.buildSources(e, { now: NOW }).vm.dials;
  // 87 read ten minutes ago by T3, 85 read a minute ago by Codex: one dial at 85, both chips.
  const merged = dials(env(one(87, 10), one(85, 1), failed)).filter((d) => d.provider === 'codex');
  assert.equal(merged.length, 1);
  assert.deepEqual([merged[0].cells[0].pct, merged[0].sources.map((t) => t.chip)], [85, ['T3', 'CX']]);
  assert.equal(merged[0].about, 'read by T3 Code and Codex · checked 06:04');
  // A dated reading never replaces a fresh one, however recent it claims to be.
  const dated = dials(env(one(87, 10), one(3, 1, 'last_known'), failed)).filter((d) => d.provider === 'codex');
  assert.deepEqual([dated.length, dated[0].cells[0].pct, dated[0].cells[0].state], [1, 87, 'value']);
  // A different reset instant is a different window: two dials.
  const other = one(40, 1); other.data.accounts[0].windows[0].resetsAt = new Date(NOW + 90 * 3600000).toISOString();
  assert.equal(dials(env(one(87, 10), other, failed)).filter((d) => d.provider === 'codex').length, 2);
  // Claude Code couldn't check: its dashed ring stays beside T3's Claude 1, with its own chip.
  const claude = dials(env(one(87, 10), one(85, 1), failed)).filter((d) => d.provider === 'claude');
  assert.deepEqual(claude.map((d) => [d.name, d.cells[0].state, d.sources.map((t) => t.chip)]), [['Claude 1', 'value', ['T3']], ['Claude', 'failed', ['CC']]]);
});

test('an empty list is a mark and a few words, with the sentence as its detail', () => {
  const say = (o, env) => M.build(glance([], o), limits(), { now: NOW, ...(env || {}) }).say;
  assert.deepEqual(say({ status: 'quiet' }), { icon: 'waves', words: 'Nothing ran in 24 h', detail: '' });
  assert.deepEqual([say({ status: 'not_set_up', reason: 'not_configured' }).icon, say({ status: 'not_set_up', reason: 'not_configured' }).words], ['plug', 'Not connected here']);
  assert.match(say({ status: 'not_set_up', reason: 'not_configured' }).detail, /isn't connected on this computer/);
  assert.deepEqual([say({ status: 'unavailable', reason: 'cannot_reach_t3' }).icon, say({ status: 'unavailable', reason: 'cannot_reach_t3' }).words], ['unplug', 'Not read yet']);
  assert.equal(say({ status: 'quiet', omitted: 2 }).words, 'Not fully read');
  assert.equal(M.build(glance([{ id: 'p', title: 'P', agents: [agent('A', 'running')] }], { counts: { running: 1 } }), limits(), { now: NOW }).say, null);
});
