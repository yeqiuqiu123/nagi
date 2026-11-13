'use strict';
// Lifecycle tests for the setup sheet (web/glance-setup.js) on a tiny fake DOM: pasted links
// are forgotten, manual addresses connect, checkboxes keep keyboard focus, failed first reads
// say so, and a Tailscale name is never saved as a label. Fictional names only.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const M = require('../web/glance-model.js');

const SCRIPT = fs.readFileSync(path.join(__dirname, '../web/glance-setup.js'), 'utf8');
const LINK = 'http://100.80.1.2:3773/pair#token=fictional-secret';

// ---- Fake DOM ---------------------------------------------------------------------------
class Node {
  constructor(doc, tag) {
    this.ownerDocument = doc; this.tagName = tag.toUpperCase(); this.children = []; this.parent = null;
    this.attrs = new Map(); this.listeners = {}; this.dataset = {}; this._text = '';
    this.hidden = false; this.disabled = false; this.checked = false; this.value = ''; this.inert = false;
    this.offsetHeight = 0; this.offsetParent = {};
    const self = this;
    this.classList = {
      add: (...names) => { const set = new Set(self.className.split(' ').filter(Boolean)); names.forEach((n) => set.add(n)); self.className = [...set].join(' '); },
      remove: (name) => { self.className = self.className.split(' ').filter((n) => n && n !== name).join(' '); },
      toggle: (name, on) => { if (on === undefined) on = !self.classList.contains(name); if (on) self.classList.add(name); else self.classList.remove(name); },
      contains: (name) => self.className.split(' ').includes(name),
    };
    this.className = '';
  }
  get id() { return this.attrs.get('id') || ''; }
  setAttribute(name, value) {
    if (name === 'hidden' || name === 'disabled' || name === 'checked') this[name] = true;
    else if (name === 'value') this.value = value;
    else this.attrs.set(name, String(value));
  }
  getAttribute(name) { return this.attrs.has(name) ? this.attrs.get(name) : null; }
  hasAttribute(name) { return this.attrs.has(name) || ((name === 'hidden' || name === 'disabled') && this[name]); }
  set textContent(value) { this._text = String(value); this.children.forEach((c) => { c.parent = null; }); this.children = []; }
  get textContent() { return [this._text, ...this.children.map((c) => c.textContent)].filter(Boolean).join(' '); }
  append(...nodes) {
    for (const node of nodes) {
      if (typeof node === 'string') { this._text += node; continue; }
      if (node.parent) node.parent.children = node.parent.children.filter((c) => c !== node);
      node.parent = this; this.children.push(node);
    }
  }
  replaceChildren(...nodes) { this.children.forEach((c) => { c.parent = null; }); this.children = []; this._text = ''; this.append(...nodes); }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === this.ownerDocument.root; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type, extra = {}) {
    const event = { type, target: this, detail: 0, key: extra.key, shiftKey: false, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, ...extra };
    for (let n = this; n; n = n.parent) (n.listeners[type] || []).forEach((fn) => fn(event));
    return event;
  }
  click() { return this.dispatch('click', { detail: 1 }); }
  focus() { this.ownerDocument.activeElement = this; }
  *walk() { for (const c of this.children) { yield c; yield* c.walk(); } }
  querySelectorAll(selector) { const groups = parse(selector); return [...this.walk()].filter((el) => groups.some((g) => matches(el, g, this))); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

// Selectors used by the sheet: #id, tag, .class, [attr], [attr="v"], :not(:disabled), descendants, commas.
function parse(selector) {
  return selector.split(',').map((group) => group.trim().split(/\s+/).map((part) => {
    const test = { tag: null, ids: [], classes: [], attrs: [], enabledOnly: false };
    const re = /^([a-z0-9]+)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]|(:not\(:disabled\))/gi;
    let m;
    while ((m = re.exec(part)) && m[0]) {
      if (m[1]) test.tag = m[1].toUpperCase();
      else if (m[2]) test.ids.push(m[2]);
      else if (m[3]) test.classes.push(m[3]);
      else if (m[4]) test.attrs.push([m[4], m[5]]);
      else if (m[6]) test.enabledOnly = true;
    }
    return test;
  }));
}
function one(el, t) {
  if (t.tag && el.tagName !== t.tag) return false;
  if (t.ids.some((id) => el.id !== id)) return false;
  if (t.classes.some((c) => !el.classList.contains(c))) return false;
  if (t.attrs.some(([name, value]) => (value === undefined ? !el.hasAttribute(name) : el.getAttribute(name) !== value))) return false;
  return !(t.enabledOnly && el.disabled);
}
function matches(el, chain, scope) {
  if (!one(el, chain[chain.length - 1])) return false;
  let i = chain.length - 2;
  for (let n = el.parent; n && n !== scope.parent && i >= 0; n = n.parent) if (one(n, chain[i])) i--;
  return i < 0;
}

// ---- Fake reader --------------------------------------------------------------------------
const PEER = { peerRef: 'peer-ref-1', label: 'Studio Mac', online: true };
function reader({ firstRead = 'ok', failTest = null } = {}) {
  const calls = [];
  const sources = [];
  let revision = 1;
  const reply = (status, data) => ({ ok: status < 400, status, json: async () => data });
  const fetch = async (url, init = {}) => {
    const route = url.replace('/api/sources/v1', '');
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ route, body });
    if (route === '') return reply(200, { version: 1, revision, sources });
    if (route === '/catalog') return reply(200, { harnesses: [{ id: 't3', displayName: 'T3 Code', available: true, capabilities: { agents: true }, copyKey: 't3_protocol2' }] });
    if (route === '/discover') {
      return body.placement.kind === 'local'
        ? reply(200, { candidates: [{ harness: 't3', running: 'yes', installed: 'yes' }], peers: [], warnings: [] })
        : reply(200, { candidates: [], peers: [PEER], warnings: [] });
    }
    if (route === '/test') {
      if (failTest) return reply(422, { error: failTest });
      return reply(200, { testId: 'test-' + calls.length, agents: { status: 'not_set_up' } });
    }
    if (route === '/connect') {
      const configuration = calls.filter((c) => c.route === '/test').pop().body.configuration;
      const source = { id: 'src-' + (sources.length + 1), harness: 't3', label: configuration.label, placement: 'tailscale' };
      revision += 1;
      const agents = firstRead === 'ok' ? { status: 'quiet', checkedAt: new Date().toISOString(), data: { counts: { running: 0 } } }
        : firstRead === 'failed' ? { status: 'unavailable', reason: 'cannot_reach_source', attemptedAt: new Date().toISOString() }
          : { status: 'unavailable', reason: 'checking' };
      sources.push({ source, agents, limits: {} });
      return reply(200, { source, revision });
    }
    return reply(404, { error: 'not_found' });
  };
  return { fetch, calls, sources };
}

function load(api) {
  const doc = { activeElement: null };
  const root = new Node(doc, 'body');
  doc.root = root;
  doc.createElement = (tag) => new Node(doc, tag);
  const panel = doc.createElement('div'); panel.setAttribute('id', 'panel'); root.append(panel);
  const opener = doc.createElement('button'); panel.append(opener); opener.focus();
  doc.getElementById = (id) => root.querySelector('#' + id);
  const icons = { monogram: () => doc.createElement('span') };
  const window = { NagiModel: M, NagiIcons: icons };
  const context = vm.createContext({ window, document: doc, fetch: api.fetch, matchMedia: () => ({ matches: true }),
    setTimeout: (fn) => setImmediate(fn), console });
  vm.runInContext(SCRIPT, context);
  const setup = window.NagiSetup;
  const host = { sources: () => ({ sources: api.sources }), refresh() {}, opener: () => opener };
  const sheet = () => panel.querySelector('.setup-sheet');
  const $ = (selector) => sheet().querySelector(selector);
  const button = (text) => sheet().querySelectorAll('button').find((b) => b._text === text);
  return { doc, setup, host, sheet, $, button, opener };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));
async function until(check) { for (let i = 0; i < 200; i++) { if (check()) return; await settle(); } assert.fail('never settled'); }
const title = (env) => env.$('#setup-title')._text;

// Open → pick T3 → pick places → arrive at step 3.
async function toConnect(env, places) {
  env.setup.open(env.host, { instant: true });
  await until(() => env.button('Continue') && !env.button('Continue').disabled);
  env.button('Continue').click();
  await until(() => env.$('#where-local'));
  for (const id of places) { const box = env.$('#' + id); box.checked = true; box.dispatch('change'); }
  env.button('Continue').click();
  assert.equal(title(env), 'Connect');
}
function paste(env, row, value) {
  const field = env.$('#target-' + row + '-pairing');
  field.value = value; field.dispatch('input');
}

// ---- Tests ----------------------------------------------------------------------------------
test('a Tailscale name is context in the wizard, never the saved label', async () => {
  const api = reader();
  const env = load(api);
  await toConnect(env, ['where-peerpeerref1']);
  assert.equal(env.$('#target-0-name')._text, 'T3 Code · Computer 2 (Studio Mac)');
  assert.equal(env.$('#target-0-name-field').value, 'Computer 2');
  paste(env, 0, LINK);
  env.button('Connect').click();
  await until(() => api.calls.some((c) => c.route === '/connect'));
  const tested = api.calls.find((c) => c.route === '/test').body.configuration;
  assert.equal(tested.label, 'Computer 2');
  assert.deepEqual(tested.placement, { kind: 'tailscale', peerRef: 'peer-ref-1' });
  assert.equal(api.sources[0].source.label, 'Computer 2');
  await until(() => !env.button('Connect'));
  env.button('Continue').click();
  await until(() => /Found/.test(env.sheet().textContent));
  assert.match(env.sheet().textContent, /T3 Code · Computer 2 \(Studio Mac\) · connected/);
});

test('a name the owner types is the one saved', async () => {
  const api = reader();
  const env = load(api);
  await toConnect(env, ['where-peerpeerref1']);
  const name = env.$('#target-0-name-field');
  name.value = 'Studio'; name.dispatch('input');
  paste(env, 0, LINK);
  env.button('Connect').click();
  await until(() => api.sources.length === 1);
  assert.equal(api.sources[0].source.label, 'Studio');
});

test('pasted links are forgotten on Esc, close, skip, back and after connecting', async () => {
  const api = reader();
  let env = load(api);
  await toConnect(env, ['where-peerpeerref1']);
  paste(env, 0, LINK);
  assert.equal(env.setup.pendingSecrets(), 1);
  env.sheet().parent.dispatch('keydown', { key: 'Escape' });
  assert.equal(env.setup.isOpen(), false);
  assert.equal(env.setup.pendingSecrets(), 0);

  env = load(api);
  await toConnect(env, ['where-peerpeerref1']);
  paste(env, 0, LINK);
  env.button('Skip').click();
  assert.equal(env.setup.pendingSecrets(), 0);

  env = load(api);
  await toConnect(env, ['where-peerpeerref1']);
  paste(env, 0, LINK);
  env.button('Back').click();
  assert.equal(env.setup.pendingSecrets(), 0);
  env.button('Continue').click();
  assert.equal(env.$('#target-0-pairing').value, '', 'nothing pasted earlier comes back');

  env = load(api);
  await toConnect(env, ['where-peerpeerref1', 'where-address']);
  paste(env, 0, LINK);
  paste(env, 1, LINK.replace('100.80.1.2', '100.80.1.3'));
  env.button('Continue').click(); // abandon step 3 with links still pasted
  assert.equal(title(env), 'Done');
  assert.equal(env.setup.pendingSecrets(), 0);

  env = load(reader());
  await toConnect(env, ['where-peerpeerref1']);
  paste(env, 0, LINK);
  env.button('Connect').click();
  assert.equal(env.setup.pendingSecrets(), 0, 'gone as soon as the attempt starts');
});

test('a re-render keeps the field and the remembered link in step', async () => {
  const env = load(reader());
  await toConnect(env, ['where-local', 'where-peerpeerref1']);
  paste(env, 1, LINK);
  env.button('Connect').click(); // connects This computer; the sheet re-renders
  await until(() => env.$('.target-row[data-status="connected"]'));
  assert.equal(env.$('#target-1-pairing').value, LINK);
  assert.equal(env.setup.pendingSecrets(), 1);
});

test('Enter an address connects from a pasted link', async () => {
  const api = reader();
  const env = load(api);
  await toConnect(env, ['where-address']);
  assert.equal(env.$('#target-0-name')._text, 'T3 Code · Computer 2 (entered address)');
  assert.equal(env.$('#target-0-address-box').hidden, true, 'no address field until it is needed');
  paste(env, 0, LINK);
  assert.equal(env.$('#target-0-address-box').hidden, true);
  env.button('Connect').click();
  await until(() => api.sources.length === 1);
  const configuration = api.calls.find((c) => c.route === '/test').body.configuration;
  assert.deepEqual(configuration.placement, { kind: 'manual' });
  assert.equal(configuration.pairing, LINK);
  assert.deepEqual(configuration.options, { port: 3773 });
});

test('a bare code asks for the address and sends it as the origin', async () => {
  const api = reader();
  const env = load(api);
  await toConnect(env, ['where-address']);
  paste(env, 0, 'fictional-code');
  assert.equal(env.$('#target-0-address-box').hidden, false);
  env.button('Connect').click();
  await until(() => env.$('.target-row[data-status="failed"]'));
  assert.equal(api.calls.filter((c) => c.route === '/test').length, 0, 'nothing is sent without an address');
  assert.match(env.sheet().textContent, /Add the computer’s Tailscale name or address/);
  paste(env, 0, 'fictional-code');
  const address = env.$('#target-0-address');
  address.value = 'Studio.tail1234.TS.net'; address.dispatch('input');
  env.button('Try again').click();
  await until(() => api.sources.length === 1);
  const configuration = api.calls.find((c) => c.route === '/test').body.configuration;
  assert.equal(configuration.options.origin, 'https://studio.tail1234.ts.net');
  assert.equal(configuration.pairing, 'fictional-code');
});

test('a manual address that is not reachable fails in plain words', async () => {
  const env = load(reader({ failTest: 'pairing_invalid' }));
  await toConnect(env, ['where-address']);
  paste(env, 0, 'http://192.168.1.4:3773/pair#token=x');
  env.button('Connect').click();
  await until(() => env.$('.target-row[data-status="failed"]'));
  assert.match(env.sheet().textContent, /isn’t on this computer or your Tailscale network/);
  assert.equal(env.setup.pendingSecrets(), 0);
});

test('checkboxes keep keyboard focus when they change', async () => {
  const env = load(reader());
  env.setup.open(env.host, { instant: true });
  await until(() => env.$('#app-t3'));
  let box = env.$('#app-t3');
  box.focus(); box.checked = false; box.dispatch('change');
  assert.equal(env.doc.activeElement, env.$('#app-t3'));
  assert.ok(env.doc.activeElement.isConnected);
  box = env.$('#app-t3'); box.checked = true; box.dispatch('change');
  env.button('Continue').click();
  await until(() => env.$('#where-local'));
  box = env.$('#where-local');
  box.focus(); box.checked = true; box.dispatch('change');
  assert.equal(env.doc.activeElement, env.$('#where-local'));
  assert.ok(env.doc.activeElement.isConnected);
  assert.equal(env.$('#where-local').checked, true);
});

test('a first read that failed says so instead of reading forever', async () => {
  const env = load(reader({ firstRead: 'failed' }));
  await toConnect(env, ['where-local']);
  env.button('Connect').click();
  await until(() => env.$('.target-row[data-status="connected"]'));
  env.button('Continue').click();
  await until(() => /Can’t reach it|Can't reach it/.test(env.sheet().textContent));
  assert.doesNotMatch(env.sheet().textContent, /Reading it for the first time/);
});

test('a first read still checking ends with honest words', async () => {
  const env = load(reader({ firstRead: 'checking' }));
  await toConnect(env, ['where-local']);
  env.button('Connect').click();
  await until(() => env.$('.target-row[data-status="connected"]'));
  env.button('Continue').click();
  await until(() => /Still checking/.test(env.sheet().textContent));
  assert.doesNotMatch(env.sheet().textContent, /Reading it for the first time/);
});

// ---- Direct apps on this computer ------------------------------------------------------------
function directReader() {
  const api = reader();
  const base = api.fetch;
  api.fetch = async (url, init = {}) => {
    const route = url.replace('/api/sources/v1', '');
    const body = init.body ? JSON.parse(init.body) : undefined;
    const reply = (status, data) => ({ ok: status < 400, status, json: async () => data });
    if (route === '/catalog') {
      api.calls.push({ route, body });
      return reply(200, { harnesses: [
        { id: 't3', displayName: 'T3 Code', available: true, capabilities: { agents: true }, copyKey: 't3_protocol2' },
        { id: 'claude', displayName: 'Claude Code', available: true, capabilities: { agents: true, limits: true }, copyKey: 'claude_direct' }] });
    }
    if (route === '/discover' && body.adapterIds[0] === 'claude') {
      api.calls.push({ route, body });
      return reply(200, { candidates: [{ harness: 'claude', placement: 'this_computer', installed: 'yes', running: 'unknown', evidence: ['data_found'] }], peers: [], warnings: [] });
    }
    return base(url, init);
  };
  return api;
}

test('Claude Code connects on this computer only, with no pairing and its consent shown first', async () => {
  const api = directReader();
  const env = load(api);
  env.setup.open(env.host, { instant: true });
  await until(() => env.$('#app-claude'));
  const t3 = env.$('#app-t3'); t3.checked = false; t3.dispatch('change');
  env.button('Continue').click();
  await until(() => env.$('#where-local') && env.$('#where-local').checked);
  // This computer only: no Tailscale lookup, no address option, and it is already chosen.
  assert.equal(api.calls.filter((c) => c.route === '/discover').length, 1);
  assert.deepEqual(api.calls.find((c) => c.route === '/discover').body.placement, { kind: 'this_computer' });
  assert.equal(env.$('#where-address'), null);
  assert.match(env.sheet().textContent, /Found Claude Code on this computer/);
  env.button('Continue').click();
  assert.equal(title(env), 'Connect');
  assert.equal(env.$('#target-0-pairing'), null);
  assert.match(env.$('#target-0-consent')._text, /sends it only to Anthropic/);
  assert.equal(env.button('Connect all'), undefined);
  env.button('Connect').click();
  await until(() => api.calls.some((c) => c.route === '/connect'));
  const tested = api.calls.find((c) => c.route === '/test').body.configuration;
  assert.deepEqual(tested, { adapterId: 'claude', label: 'This computer', placement: { kind: 'this_computer' }, mode: 'direct', options: {} });
});

test('a missing Claude Code says what to do, in plain words', async () => {
  const api = directReader();
  const base = api.fetch;
  api.fetch = async (url, init = {}) => (url.endsWith('/test')
    ? { ok: true, status: 200, json: async () => ({ agents: { status: 'unavailable', reason: 'local_data_missing' } }) }
    : base(url, init));
  const env = load(api);
  env.setup.open(env.host, { instant: true });
  await until(() => env.$('#app-claude'));
  const t3 = env.$('#app-t3'); t3.checked = false; t3.dispatch('change');
  env.button('Continue').click();
  await until(() => env.$('#where-local') && env.$('#where-local').checked);
  env.button('Continue').click();
  env.button('Connect').click();
  await until(() => /Use Claude Code once here/.test(env.sheet().textContent));
});

test('Cursor is marked beta and connects with hooks on this computer, its consent shown first', async () => {
  const api = directReader();
  const base = api.fetch;
  api.fetch = async (url, init = {}) => {
    const route = url.replace('/api/sources/v1', '');
    const body = init.body ? JSON.parse(init.body) : undefined;
    const reply = (status, data) => ({ ok: status < 400, status, json: async () => data });
    if (route === '/catalog') {
      api.calls.push({ route, body });
      return reply(200, { harnesses: [{ id: 'cursor', displayName: 'Cursor', available: true, beta: true, capabilities: { agents: true, limits: true }, copyKey: 'cursor_direct' }] });
    }
    if (route === '/discover') {
      api.calls.push({ route, body });
      return reply(200, { candidates: [{ harness: 'cursor', placement: 'this_computer', installed: 'yes', running: 'unknown', evidence: ['data_found'] }], peers: [], warnings: [] });
    }
    return base(url, init);
  };
  const env = load(api);
  env.setup.open(env.host, { instant: true });
  await until(() => env.$('#app-cursor'));
  assert.match(env.sheet().textContent, /Cursor Beta/);
  env.button('Continue').click();
  await until(() => env.$('#where-local') && env.$('#where-local').checked);
  env.button('Continue').click();
  assert.match(env.$('#target-0-consent')._text, /sends it only to Cursor/);
  env.button('Connect').click();
  await until(() => api.calls.some((c) => c.route === '/test'));
  assert.deepEqual(api.calls.find((c) => c.route === '/test').body.configuration,
    { adapterId: 'cursor', label: 'This computer', placement: { kind: 'this_computer' }, mode: 'hooks', options: {} });
});

test('the setup summary counts a Cursor limit account', async () => {
  const api = reader('ok');
  const env = load(api);
  await toConnect(env, ['where-local']);
  env.button('Connect').click();
  await until(() => api.sources.length === 1);
  api.sources[0].limits = { cursor: { status: 'ok', data: { accounts: [{ id: 'cursor-1', label: 'Cursor 1' }] } } };
  await until(() => !env.button('Connect'));
  env.button('Continue').click();
  await until(() => /Found/.test(env.sheet().textContent));
  assert.match(env.sheet().textContent, /1 limit account\b/);
});
