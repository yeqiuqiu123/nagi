'use strict';
// Nagi setup: the four-step "add a source" sheet and Settings → Sources. Loaded on demand.
// Binding contract: design/sources-api.md (API v1). Read-only connections only; the owner
// starts every network step, connect is never retried automatically, and no token, address
// or path is ever shown. Keyboard paths open, step and close on the next frame.
(() => {
  const M = window.NagiModel;
  const I = window.NagiIcons;
  const API = '/api/sources/v1';
  const POST_HEADERS = { 'Content-Type': 'application/json', 'X-Progress-Desk': '1' };
  const T3_PORT = 3773;
  // Apps Nagi reads straight from this computer's own files: no pairing, no other computers.
  const DIRECT = { claude: 'direct', codex: 'rollouts', cursor: 'hooks' };
  const isDirect = (app) => Object.prototype.hasOwnProperty.call(DIRECT, app);
  // What connecting changes, said before the owner chooses Connect (the explicit opt-in).
  const CONSENT = {
    claude: 'To show your limits, Nagi reads your Claude Code sign-in and sends it only to Anthropic. To see sessions, it adds small hooks to Claude Code\u2019s settings that note when a session starts and stops, never what you write. Disconnect removes the hooks.',
    codex: 'Nagi reads the session logs Codex keeps on this computer. To show your limits, Nagi reads your Codex sign-in and sends it only to OpenAI. Nagi never refreshes or saves your sign-in.',
    cursor: 'To show your monthly limit, Nagi reads your Cursor sign-in and sends it only to Cursor. To see activity, it adds small hooks to Cursor\u2019s settings that note when a chat starts and stops, never what you write. Nagi sees recent activity only; sub-agents and questions for you aren\u2019t shown yet. If T3 Code also runs Cursor here, a chat may appear under both. Disconnect removes the hooks.',
  };

  // ---- Plain words ------------------------------------------------------------------
  const CAPABILITY_WORDS = [['agents', 'Running agents'], ['lineage', 'Sub-agents'], ['limits', 'Limits'],
    ['asksYou', 'Questions for you'], ['stuckDetection', 'Stuck alerts'], ['deepLinks', 'Open in the app']];
  const COPY = {
    t3_protocol2: "Reads T3 Code's own read-only connection.",
    openbot_export_required: "Needs OpenBot's activity export.",
    pi_sidecar_required: 'Needs a small Pi helper.',
    omp_pi_family_planned: 'Part of the Pi family; it will use the Pi helper.',
    codex_passive_limits_planned: "Limits from Codex's own logs are planned.",
    claude_sidecar_required: 'Needs a Claude Code hook helper.',
    claude_direct: 'Running sessions from Claude Code on this computer, and your Claude limits.',
    codex_direct: "Running sessions from Codex's own logs on this computer, and your Codex limits.",
    cursor_direct: 'Recent Cursor activity on this computer, and your monthly limit.',
    hermes_scoped_export_required: 'Needs a scoped Hermes export.',
    openclaw_scoped_gateway_required: 'Needs a scoped OpenClaw gateway.',
    opencode_versioned_adapter_required: 'Needs a tested OpenCode adapter.',
  };
  // Closed error codes → what happened and what to do next. Never echoes server text.
  const ERRORS = {
    invalid_request: "Nagi didn't accept that setup. Go back and try again.",
    owner_required: 'Nagi needs to confirm it is you. Close the panel and open it again.',
    origin_denied: "This window isn't allowed to change Nagi's setup. Open Nagi from its own icon.",
    not_found: "That app isn't part of this version of Nagi.",
    method_not_allowed: "Nagi didn't accept that setup. Go back and try again.",
    test_expired: 'The check expired. Choose Connect to test again.',
    configuration_changed: 'Your sources changed in the meantime. Choose Connect to test again.',
    source_exists: 'That computer is already connected. You can manage it in Settings → Sources.',
    peer_expired: 'The list of computers is out of date. Go back and look again.',
    request_too_large: 'That pairing link is too long. Copy it again from T3.',
    pairing_invalid: "That pairing link didn't work. In T3 on that computer, make a new one: Settings → Connections → Pair a device.",
    scope_mismatch: "T3 offered something other than read-only access, so Nagi didn't connect. Make a new pairing link and try again.",
    connection_failed: "Nagi couldn't finish connecting. Check that T3 Code is running there, then choose Connect again.",
    local_pairing_unavailable: "T3 Code on this computer couldn't give Nagi a read-only connection. Open T3 Code, then choose Connect again.",
    hook_install_failed: "Nagi couldn't add its hooks to the app's settings, so nothing there changed. Check that its settings file is a normal file you own, then choose Try again.",
    hook_remove_failed: "Nagi couldn't remove its hooks from the app's settings, so it stays connected. Choose Disconnect again.",
    storage_unavailable: "Nagi couldn't save the connection. Check that the disk isn't full, then try again.",
    capacity_reached: 'Nagi already reads as many sources as it can. Disconnect one first.',
    network: "Nagi's reader didn't answer. Wait a moment, then try again.",
  };
  const errorWords = (code) => ERRORS[code] || ERRORS.network;
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many);

  function testWords(result, name) {
    name = name || 'T3 Code';
    if (result.testId) return name + ' answered. Connecting read-only…';
    if (result.agents && result.agents.reason === 'local_data_missing') return 'Nagi couldn\u2019t find ' + name + ' on this computer. Use ' + name + ' once here, then choose Try again.';
    const status = result.agents && result.agents.status;
    if (status === 'unsupported') return 'Nagi can\u2019t read this version of ' + name + ' yet.';
    return name + " didn't answer there. Make sure it is open on that computer, then choose Try again.";
  }

  function sourceState(read) {
    const a = read.agents || {};
    const tried = a.attemptedAt ? ' · tried ' + M.hm(Date.parse(a.attemptedAt)) : '';
    const counts = (a.data && a.data.counts) || {};
    if (a.status === 'ok') return 'Reading · ' + plural(counts.running || 0, 'running agent', 'running agents');
    if (a.status === 'quiet') return 'Reading · nothing running';
    if (a.status === 'unavailable' && a.reason === 'checking') return 'Checking…';
    if (a.status === 'last_known') return "Can't reach it · last read " + M.hm(Date.parse(a.checkedAt)) + tried;
    if (a.status === 'not_set_up') return 'Not set up';
    if (a.status === 'unsupported') return "This version isn't supported";
    return "Can't reach it" + tried;
  }

  function foundWords(read) {
    const a = read.agents || {};
    if (a.status !== 'ok' && a.status !== 'quiet') return null;
    const running = ((a.data && a.data.counts) || {}).running || 0;
    let accounts = 0;
    for (const key of Object.keys(read.limits || {})) {
      const p = read.limits[key];
      if (p && (p.status === 'ok' || p.status === 'last_known') && p.data) accounts += (p.data.accounts || []).length;
    }
    return 'Found ' + plural(running, 'running agent', 'running agents') + ' and ' + plural(accounts, 'limit account', 'limit accounts') + '.';
  }

  // ---- DOM ------------------------------------------------------------------------------
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
    return el;
  }
  const icon = (name) => { const id = M.projectIdentity(name); const el = I.monogram(id.monogram, id.color); el.classList.add('pi-inline'); el.setAttribute('aria-hidden', 'true'); return el; };

  const panel = document.getElementById('panel');
  const layer = h('div', { class: 'sheet-layer setup-layer', id: 'setup-layer', hidden: true },
    h('div', { class: 'scrim', 'aria-hidden': 'true', onclick: () => close({ instant: false }) }));
  const sheet = h('div', { class: 'sheet setup-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'setup-title' });
  layer.append(sheet);
  panel.append(layer);

  // ---- Network ------------------------------------------------------------------------
  async function call(path, body) {
    let response;
    try {
      response = await fetch(API + path, body === undefined ? { cache: 'no-store' }
        : { method: 'POST', cache: 'no-store', headers: POST_HEADERS, body: JSON.stringify(body) });
    } catch { return { ok: false, code: 'network' }; }
    let data = null;
    try { data = await response.json(); } catch {}
    if (response.ok && data) return { ok: true, data };
    const code = data && typeof data.error === 'string' && Object.prototype.hasOwnProperty.call(ERRORS, data.error) ? data.error
      : response.status === 401 ? 'owner_required' : 'network';
    return { ok: false, code, status: response.status };
  }

  // ---- State -----------------------------------------------------------------------------
  let host = null;
  let state = null;
  let opener = null;

  function show(options) {
    opener = document.activeElement;
    layer.classList.toggle('instant', !options || options.instant !== false);
    layer.hidden = false;
    void layer.offsetHeight; // start the transition from the closed state
    layer.dataset.open = 'true';
    panel.querySelectorAll('.pinned, .scroll').forEach((el) => { el.inert = true; });
  }

  function close(options) {
    if (layer.hidden) return;
    const instant = !options || options.instant !== false;
    layer.classList.toggle('instant', instant);
    layer.dataset.open = 'false';
    panel.querySelectorAll('.pinned, .scroll').forEach((el) => { el.inert = false; });
    const done = () => { if (layer.dataset.open !== 'true') { layer.hidden = true; sheet.replaceChildren(); } };
    if (instant || matchMedia('(prefers-reduced-motion: reduce)').matches) done(); else setTimeout(done, 200);
    const back = opener && opener.isConnected ? opener : host && host.opener();
    if (back) back.focus({ preventScroll: true });
    state = null;
    pairings.clear(); // closing (button, scrim or Esc) forgets every pasted link
    if (host) host.refresh();
  }

  // Re-render without losing the keyboard's place: focus returns to the same control by id.
  function renderKeeping(id) {
    render();
    const again = id && sheet.querySelector('#' + id);
    if (again) again.focus({ preventScroll: true });
  }
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function frame(title, step, body, actions) {
    const heading = h('h2', { id: 'setup-title', tabindex: '-1', text: title });
    // replaceChildren would print false/null as text, so empty slots are dropped first.
    sheet.replaceChildren(...[
      step ? h('p', { class: 'setup-step', text: typeof step === 'string' ? step : 'Step ' + step + ' of 4' }) : null,
      heading,
      ...body,
      h('div', { class: 'sheet-actions' }, actions)].filter((el) => el != null && el !== false));
    return heading;
  }

  function focusFirst(fallback) {
    const target = sheet.querySelector('[data-autofocus]') || fallback;
    if (target) target.focus({ preventScroll: true });
  }

  const button = (text, attrs) => h('button', { type: 'button', class: 'btn' + (attrs && attrs.primary ? ' default' : ''), ...attrs, primary: null, text });
  const grow = () => h('span', { class: 'grow' });
  const live = (text, kind) => h('p', { class: kind === 'error' ? 'setup-error' : 'setup-status', role: kind === 'error' ? 'alert' : 'status', text });

  // ---- Step 1: which agent apps ---------------------------------------------------------
  function stepApps() {
    const items = state.catalog.map((app) => {
      const id = 'app-' + app.id;
      const words = app.available
        ? CAPABILITY_WORDS.filter(([k]) => app.capabilities[k]).map(([, w]) => w).join(', ')
        : COPY[app.copyKey] || 'Coming soon.';
      return h('li', { class: 'choice' + (app.available ? '' : ' unavailable') },
        h('input', { type: 'checkbox', id, checked: state.apps.has(app.id), disabled: !app.available, 'aria-describedby': id + '-what',
          onchange: (event) => { if (event.target.checked) state.apps.add(app.id); else state.apps.delete(app.id); renderKeeping(event.target.id); } }),
        icon(app.displayName),
        h('label', { for: id, class: 'choice-text' },
          h('span', { class: 'choice-name', text: app.displayName }),
          !app.available && h('span', { class: 'badge', text: 'Coming soon' }),
          app.available && app.beta && h('span', { class: 'badge', text: 'Beta' }),
          h('span', { class: 'choice-what', id: id + '-what', text: words })));
    });
    const heading = frame('Which agent apps?', 1, [
      h('p', { class: 'sheet-lede', text: 'Nagi only reads them. It never sends, stops or approves anything.' }),
      h('ul', { class: 'choices', 'aria-label': 'Agent apps' }, items)],
      [button('Cancel', { onclick: (e) => close({ instant: e.detail === 0 }) }), grow(),
        button('Continue', { primary: true, disabled: !state.apps.size, onclick: () => {
          state.order = state.catalog.filter((c) => c.available && state.apps.has(c.id)).map((c) => c.id);
          state.appIndex = 0; go('where');
        } })]);
    return heading;
  }

  // ---- Step 2: where does each app run (one app at a time, several places each) ---------------
  const currentApp = () => state.order[state.appIndex];
  const appName = (id) => (state.catalog.find((c) => c.id === id) || {}).displayName || M.harnessName(id);

  async function discover(app) {
    const d = state.disc[app] = { discovering: true, local: null, peers: [], tailscaleMissing: false, error: null };
    render();
    const direct = isDirect(app);
    const [local, remote] = await Promise.all([call('/discover', { adapterIds: [app], placement: { kind: direct ? 'this_computer' : 'local' } }),
      direct ? Promise.resolve({ ok: true, data: { peers: [], warnings: [] } }) : call('/discover', { adapterIds: [app], placement: { kind: 'tailscale' } })]);
    if (!state || state.disc[app] !== d) return;
    d.discovering = false;
    d.local = local.ok ? local.data.candidates.find((c) => c.harness === app) || null : null;
    d.peers = remote.ok ? remote.data.peers : [];
    d.tailscaleMissing = !remote.ok || remote.data.warnings.includes('tailscale_unavailable');
    d.error = !local.ok && !remote.ok ? local.code : direct && !local.ok ? local.code : null;
    // Only one place is possible for a direct app; choose it for the owner when it is there.
    if (direct && d.local && d.local.installed === 'yes') (state.picks[app] || (state.picks[app] = new Set())).add('local');
    render();
  }

  function localWords(name, c) {
    if (!c) return 'Not checked yet';
    if ((c.evidence || []).includes('data_found')) return 'Found ' + name + ' on this computer';
    if (c.running === 'yes') return name + ' is running here';
    if (c.installed === 'yes') return 'Installed here. Open ' + name + ' to connect';
    if (c.installed === 'no') return name + ' isn’t installed here';
    return name + ' wasn’t found running here';
  }

  function stepWhere() {
    const app = currentApp();
    const name = appName(app);
    const d = state.disc[app];
    const picks = state.picks[app] || (state.picks[app] = new Set());
    const many = state.order.length > 1;
    const back = () => { if (state.appIndex > 0) { state.appIndex -= 1; go('where'); } else go('apps'); };
    const next = () => { if (state.appIndex < state.order.length - 1) { state.appIndex += 1; go('where'); } else go('connect'); };
    const label = 'Step 2 of 4 · ' + name + (many ? ' (' + (state.appIndex + 1) + ' of ' + state.order.length + ' apps)' : '');
    if (!d || d.discovering) {
      return frame('Where does ' + name + ' run?', label, [live('Looking on this computer and your Tailscale network…')],
        [button('Back', { onclick: back }), grow(), button('Continue', { primary: true, disabled: true })]);
    }
    const option = (value, title, sub) => {
      const id = 'where-' + value.replace(/[^a-z0-9]/gi, '');
      return h('li', { class: 'choice plain' },
        h('input', { type: 'checkbox', id, checked: picks.has(value), 'aria-describedby': id + '-what',
          onchange: (event) => { if (event.target.checked) picks.add(value); else picks.delete(value); renderKeeping(event.target.id); } }),
        h('label', { for: id, class: 'choice-text' }, h('span', { class: 'choice-name', text: title }), h('span', { class: 'choice-what', id: id + '-what', text: sub })));
    };
    const direct = isDirect(app);
    const items = [option('local', 'This computer', localWords(name, d.local))];
    if (!direct) {
      for (const peer of d.peers) items.push(option('peer:' + peer.peerRef, peer.label, peer.online ? 'On your Tailscale network · online' : 'On your Tailscale network · offline'));
      items.push(option('address', 'Enter an address', 'Paste a pairing link from a computer that isn’t listed'));
    }
    return frame('Where does ' + name + ' run?', label, [
      h('p', { class: 'sheet-lede', text: direct
        ? 'Nagi reads ' + name + ' on this computer. For another computer, install Nagi there too.'
        : 'Choose every computer where ' + name + ' runs. You can pick more than one.' }),
      d.error && live(errorWords(d.error), 'error'),
      h('ul', { class: 'choices', 'aria-label': 'Computers for ' + name }, items),
      !direct && d.tailscaleMissing && h('p', { class: 'help', text: 'Tailscale isn’t running here, so other computers can’t be listed.' })],
      [button('Back', { onclick: back }), grow(),
        button('Look again', { onclick: () => discover(app) }),
        button(state.appIndex < state.order.length - 1 ? 'Next app' : 'Continue', { primary: true, disabled: !picks.size, onclick: next })]);
  }

  // ---- Step 3: connect each place, one at a time ----------------------------------------------
  const pairings = new Map(); // place key → pasted link; memory only, cleared as soon as it is used

  function planTargets() {
    const taken = new Set(((host.sources() || {}).sources || []).map((s) => s.source.label));
    const previous = new Map((state.targets || []).map((t) => [t.key, t]));
    // Names of places kept from an earlier pass stay theirs, so a new place never repeats one.
    for (const app of state.order) for (const key of state.picks[app] || []) { const old = previous.get(app + '|' + key); if (old) taken.add(old.label); }
    const nextComputer = () => { for (let n = 2; n < 60; n++) if (!taken.has('Computer ' + n)) { taken.add('Computer ' + n); return 'Computer ' + n; } return 'Another computer'; };
    const placesByApp = {};
    for (const app of state.order) {
      const d = state.disc[app] || { peers: [] };
      placesByApp[app] = [...(state.picks[app] || [])].map((key) => {
        if (key === 'local') return { key, label: 'This computer', defaultLabel: 'This computer' };
        const kept = previous.get(app + '|' + key);
        if (key === 'address') return { key, label: 'An address', context: 'entered address', defaultLabel: kept ? kept.label : nextComputer() };
        const peer = d.peers.find((x) => 'peer:' + x.peerRef === key) || {};
        // A Tailscale name is never saved as a label unless the owner types it: the saved name
        // stays generic, and the wizard alone shows the discovered name beside it for context.
        return { key, label: peer.label || 'Another computer', context: peer.label || null, peerRef: peer.peerRef, defaultLabel: kept ? kept.label : nextComputer() };
      });
    }
    state.targets = M.setupTargets(state.order, placesByApp, state.catalog).map((t) => previous.get(t.key) || t);
    // A place the owner dropped takes its pasted link with it.
    const keep = new Set(state.targets.map((t) => t.key));
    for (const key of [...pairings.keys()]) if (!keep.has(key)) pairings.delete(key);
  }

  // A re-render keeps a pasted link in its field (as a property, never an attribute), so what the
  // owner sees is always exactly what Connect would use.
  function secretField(t, attrs) {
    const input = h('input', attrs);
    input.value = pairings.get(t.key) || '';
    return input;
  }

  // The name Nagi will save, with the discovered name beside it for context (wizard only).
  const shown = (t, saved) => (saved || (t.label || '').trim() || t.placeLabel) + (t.context ? ' (' + t.context + ')' : '');

  // A T3 link carries its own address; a bare code needs the computer's address too.
  const isLink = (value) => /^\s*(https?:\/\/|t3code:\/\/)/i.test(value || '');
  function originFor(address) {
    let value = (address || '').trim().replace(/\/+$/, '');
    if (!value) return null;
    if (!/^https?:\/\//i.test(value)) value = (/\.ts\.net(:\d+)?$/i.test(value) ? 'https://' : 'http://') + value;
    value = value.replace(/^(https?:\/\/)([^/]+)$/i, (m, scheme, hostPort) => scheme.toLowerCase() + hostPort.toLowerCase());
    if (/^http:\/\/[^/:]+$/.test(value)) value += ':' + T3_PORT;
    return value;
  }

  function targetWords(t) {
    if (t.status === 'connecting') return 'Testing, then connecting read-only…';
    if (t.status === 'connected') return t.words || 'Connected.';
    if (t.status === 'skipped') return 'Skipped. You can add it later from Settings → Sources.';
    if (t.status === 'failed') {
      if (t.manual && t.error === 'pairing_invalid') return 'That link or address isn’t on this computer or your Tailscale network, or the link has expired. In T3 on that computer: Settings → Connections → Pair a device.';
      return ERRORS[t.error] ? errorWords(t.error) : t.error;
    }
    if (t.manual) return 'Paste its pairing link from T3 on that computer, then connect.';
    return t.remote ? 'Paste its pairing link, then connect.' : 'Ready to connect.';
  }

  function stepConnect() {
    const busy = !!state.busy;
    const rows = state.targets.map((t, i) => {
      const id = 'target-' + i;
      const open = t.status === 'ready' || t.status === 'failed';
      return h('li', { class: 'target-row', 'data-status': t.status, 'aria-labelledby': id + '-name' },
        icon(t.appName),
        h('div', { class: 'choice-text' },
          h('span', { class: 'choice-name', id: id + '-name', text: t.appName + ' · ' + shown(t) }),
          h('span', { class: t.status === 'failed' ? 'choice-what target-error' : 'choice-what', role: t.status === 'failed' ? 'alert' : 'status', text: targetWords(t) }),
          open && CONSENT[t.app] && h('p', { class: 'help consent', id: id + '-consent', text: CONSENT[t.app] }),
          open && (t.remote || t.manual) && h('div', { class: 'field stacked compact' },
            h('label', { for: id + '-pairing', text: 'Pairing link' }),
            secretField(t, { id: id + '-pairing', type: 'password', autocomplete: 'off', spellcheck: 'false', disabled: busy, 'aria-describedby': id + '-help',
              oninput: (e) => {
                pairings.set(t.key, e.target.value);
                if (!t.manual) return;
                // The address field appears only when the paste is a bare code, not a full link.
                t.needsAddress = !!e.target.value.trim() && !isLink(e.target.value);
                const box = sheet.querySelector('#' + id + '-address-box');
                if (box) box.hidden = !t.needsAddress;
              } }),
            h('p', { class: 'help', id: id + '-help', text: 'In T3 on that computer: Settings → Connections → Pair a device.' })),
          open && t.manual && h('div', { class: 'field stacked compact', id: id + '-address-box', hidden: !t.needsAddress },
            h('label', { for: id + '-address', text: 'Its address' }),
            h('input', { id: id + '-address', type: 'text', autocomplete: 'off', spellcheck: 'false', disabled: busy, value: t.address || '', 'aria-describedby': id + '-address-help',
              oninput: (e) => { t.address = e.target.value; } }),
            h('p', { class: 'help', id: id + '-address-help', text: 'Only needed for a code on its own: the computer’s Tailscale name or address.' })),
          open && h('div', { class: 'field stacked compact' },
            h('label', { for: id + '-name-field', text: 'Name in Nagi' }),
            h('input', { id: id + '-name-field', type: 'text', autocomplete: 'off', maxlength: '80', value: t.label, disabled: busy,
              oninput: (e) => { t.label = e.target.value; } })),
          open && h('div', { class: 'target-actions' },
            button(t.status === 'failed' ? 'Try again' : 'Connect', { disabled: busy, 'aria-describedby': id + '-name' + (CONSENT[t.app] ? ' ' + id + '-consent' : ''), onclick: () => runTargets([t], true) }),
            button('Skip', { disabled: busy, 'aria-describedby': id + '-name', onclick: () => { t.status = 'skipped'; pairings.delete(t.key); render(); focusFirst(sheet.querySelector('#setup-title')); } }))));
    });
    const ready = state.targets.filter((t) => t.status === 'ready' && !CONSENT[t.app]).length;
    return frame('Connect', 'Step 3 of 4', [
      h('p', { class: 'sheet-lede', text: 'Each place connects read-only, one at a time.' }),
      h('ul', { class: 'source-rows targets', 'aria-label': 'Places to connect' }, rows)],
      [button('Back', { disabled: busy, onclick: () => { pairings.clear(); state.appIndex = state.order.length - 1; go('where'); } }), grow(),
        ready > 1 && button('Connect all', { disabled: busy, onclick: () => runTargets(state.targets.filter((t) => !CONSENT[t.app]), false) }),
        button('Continue', { primary: true, disabled: busy, 'data-autofocus': true, onclick: () => go('done') })]);
  }

  // Strictly sequential: one test-then-connect at a time, never in parallel, never retried by Nagi.
  async function runTargets(targets, again) {
    if (state.busy) return;
    if (again) targets.forEach((t) => { if (t.status === 'failed') t.status = 'ready'; });
    state.busy = true;
    await M.connectInSequence(targets, connectOne, () => render());
    if (!state) return;
    state.busy = false;
    render();
    const next = sheet.querySelector('.target-row[data-status="failed"] input, .target-row[data-status="ready"] button, #setup-title');
    if (next) next.focus({ preventScroll: true });
  }

  async function connectOne(t) {
    const pairing = (pairings.get(t.key) || '').trim();
    pairings.delete(t.key); // the pasted link never outlives one attempt, successful or not
    if ((t.remote || t.manual) && !pairing) return { ok: false, words: 'Paste its pairing link, then choose Try again.' };
    if (!(t.label || '').trim()) return { ok: false, words: 'Give it a name in Nagi, then choose Try again.' };
    const placement = isDirect(t.app) ? { kind: 'this_computer' } : t.remote ? { kind: 'tailscale', peerRef: t.peerRef } : t.manual ? { kind: 'manual' } : { kind: 'local' };
    const configuration = isDirect(t.app)
      ? { adapterId: t.app, label: t.label.trim(), placement, mode: DIRECT[t.app], options: {} }
      : { adapterId: t.app, label: t.label.trim(), placement, mode: 'protocol2', options: { port: T3_PORT } };
    if (t.manual && !isLink(pairing)) {
      const origin = originFor(t.address);
      if (!origin) return { ok: false, words: 'That’s a code on its own. Add the computer’s Tailscale name or address, or paste the full pairing link.' };
      configuration.options.origin = origin;
    }
    if (t.remote || t.manual) configuration.pairing = pairing;
    const list = await call('', undefined);
    const tested = await call('/test', { configuration });
    if (!tested.ok) return { ok: false, code: tested.code };
    if (!tested.data.testId) return { ok: false, words: testWords(tested.data, t.appName) };
    const connected = await call('/connect', { testId: tested.data.testId, expectedRevision: list.ok ? list.data.revision : 0 });
    if (!connected.ok) return { ok: false, code: connected.code };
    return { ok: true, source: connected.data.source, words: 'Connected.' };
  }

  // ---- Step 4: done ------------------------------------------------------------------------------
  async function readConnected() {
    // Truth only: what Nagi actually read for each new source, or that it is still reading.
    // A source still being checked keeps waiting; a finished read, good or bad, is shown as it is.
    for (let i = 0; i < 8 && state && state.step === 'done'; i++) {
      const waiting = state.targets.filter((t) => t.status === 'connected' && t.source && !t.found);
      if (!waiting.length) return;
      const list = await call('', undefined);
      if (!state) return;
      for (const t of waiting) {
        const read = list.ok ? list.data.sources.find((s) => s.source.id === t.source.id) : null;
        const agents = read && read.agents;
        if (!agents || (agents.status === 'unavailable' && agents.reason === 'checking')) continue;
        t.found = foundWords(read) || sourceState(read) + '.';
      }
      render();
      await wait(1000);
    }
    if (!state || state.step !== 'done') return;
    state.targets.filter((t) => t.status === 'connected' && t.source && !t.found)
      .forEach((t) => { t.found = 'Still checking. It appears in the glance as soon as Nagi has read it.'; });
    render();
  }

  function stepDone() {
    const lines = state.targets.map((t) => {
      const connected = t.status === 'connected';
      const name = t.appName + ' · ' + shown(t, connected && t.source ? t.source.label : null);
      const what = connected ? (t.found || 'Reading it for the first time…')
        : t.status === 'skipped' ? 'You can add it later from Settings → Sources.'
          : t.status === 'failed' ? targetWords(t) + ' Choose Add another to try again.' : 'Not tried. Choose Add another to connect it.';
      return h('li', { class: 'summary-row' },
        icon(t.appName),
        h('div', { class: 'choice-text' },
          h('span', { class: 'choice-name', text: name + ' · ' + (connected ? 'connected' : t.status === 'skipped' ? 'skipped' : 'not connected') }),
          h('span', { class: 'choice-what', text: what })));
    });
    const count = state.targets.filter((t) => t.status === 'connected').length;
    return frame('Done', 'Step 4 of 4', [
      h('p', { class: 'sheet-lede', role: 'status', text: count ? plural(count, 'source', 'sources') + ' connected.' : 'Nothing was connected this time.' }),
      h('ul', { class: 'source-rows', 'aria-label': 'Setup summary' }, lines)],
      [button('Add another', { onclick: () => restart() }), grow(),
        button('View agents', { primary: true, 'data-autofocus': true, onclick: (e) => close({ instant: e.detail === 0 }) })]);
  }

  // ---- Settings → Sources --------------------------------------------------------------------
  async function loadSources() {
    const list = await call('', undefined);
    if (!state) return;
    state.list = list.ok ? list.data : null;
    state.listError = list.ok ? null : list.code;
    render();
  }

  function stepSources() {
    const rows = [];
    const sources = state.list ? state.list.sources : [];
    for (const read of sources) {
      const tag = read.source;
      const name = M.harnessName(tag.harness);
      const confirming = state.confirm === tag.id;
      rows.push(h('li', { class: 'source-row' },
        icon(name),
        h('div', { class: 'choice-text' },
          h('span', { class: 'choice-name', text: name + ' · ' + tag.label }),
          h('span', { class: 'choice-what', text: sourceState(read) })),
        !confirming && button('Disconnect', { 'aria-label': 'Disconnect ' + name + ' on ' + tag.label, onclick: () => { state.confirm = tag.id; state.error = null; render(); focusFirst(); } }),
        confirming && h('div', { class: 'confirm', role: 'group', 'aria-label': 'Confirm disconnect' },
          h('p', { class: 'help', text: 'Stop reading ' + name + ' on ' + tag.label + '? Its agents leave the glance. '
            + (tag.harness === 'claude' || tag.harness === 'cursor' ? 'Nagi removes its hooks from ' + name + '\u2019s settings and leaves everything else as it was.' : 'Nothing changes in ' + name + '.') }),
          h('div', { class: 'confirm-actions' },
            button('Keep', { onclick: () => { state.confirm = null; render(); } }),
            button(state.pending ? 'Disconnecting…' : 'Disconnect', { primary: true, 'data-autofocus': true, disabled: !!state.pending, onclick: () => disconnect(tag.id) })))));
    }
    const body = [h('p', { class: 'sheet-lede', text: 'Nagi reads these, read-only.' })];
    if (state.listError) body.push(live(errorWords(state.listError), 'error'));
    else if (!state.list) body.push(live('Loading…'));
    else if (!rows.length) body.push(h('p', { class: 'help', text: 'Nothing connected yet.' }));
    else body.push(h('ul', { class: 'source-rows', 'aria-label': 'Connected sources' }, rows));
    if (state.error) body.push(live(errorWords(state.error), 'error'));
    return frame('Sources', null, body,
      [button('Add a source…', { onclick: () => restart() }), grow(),
        button('Done', { primary: true, 'data-autofocus': !state.confirm, onclick: (e) => close({ instant: e.detail === 0 }) })]);
  }

  async function disconnect(id) {
    if (state.pending) return;
    state.pending = true; render();
    const list = await call('', undefined);
    const result = list.ok ? await call('/disconnect', { sourceId: id, expectedRevision: list.data.revision }) : list;
    if (!state) return;
    state.pending = false; state.confirm = null;
    state.error = result.ok ? null : result.code;
    await loadSources();
    host.refresh();
  }

  // ---- Flow ------------------------------------------------------------------------------------
  function render() {
    if (!state) return null;
    const step = state.step;
    return step === 'apps' ? stepApps() : step === 'where' ? stepWhere() : step === 'connect' ? stepConnect()
      : step === 'done' ? stepDone() : stepSources();
  }

  function go(step) {
    state.step = step;
    state.error = null;
    if (step === 'connect') planTargets();
    const heading = render();
    if (step === 'where' && !state.disc[currentApp()]) discover(currentApp());
    if (step === 'done') { pairings.clear(); readConnected(); }
    // Steps change on the next frame; focus moves to the step's first control (or its title).
    focusFirst(heading);
  }

  async function startCatalog() {
    const catalog = await call('/catalog', undefined);
    if (!state) return;
    state.catalog = catalog.ok ? catalog.data.harnesses : [];
    if (!catalog.ok) state.error = catalog.code;
    state.catalog.filter((a) => a.available).forEach((a) => state.apps.add(a.id));
    if (state.step === 'apps') { render(); focusFirst(sheet.querySelector('#setup-title')); }
  }

  const fresh = (step) => ({ step, catalog: [], apps: new Set(), order: [], appIndex: 0, disc: {}, picks: {}, targets: [], list: null });

  // Add another: a clean run of the four steps, keeping the catalog already loaded.
  function restart() {
    const catalog = state.catalog;
    state = fresh('apps'); state.catalog = catalog;
    catalog.filter((a) => a.available).forEach((a) => state.apps.add(a.id));
    pairings.clear();
    go('apps');
  }

  function open(nextHost, options) {
    host = nextHost;
    state = fresh('apps');
    show(options);
    focusFirst(render());
    startCatalog();
  }

  function openSources(nextHost, options) {
    host = nextHost;
    state = fresh('sources');
    show(options);
    focusFirst(render());
    loadSources();
    startCatalog();
  }

  // Esc closes the setup (instantly); Tab stays inside the sheet.
  layer.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close({ instant: true }); return; }
    if (event.key !== 'Tab') return;
    const items = [...sheet.querySelectorAll('button:not(:disabled), input:not(:disabled), [tabindex="-1"]#setup-title')].filter((el) => el.offsetParent !== null);
    const i = items.indexOf(document.activeElement);
    if (event.shiftKey && i <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
    else if (!event.shiftKey && i === items.length - 1) { event.preventDefault(); items[0].focus(); }
  });

  // pendingSecrets is a count only, for lifecycle tests; no pasted value ever leaves this module.
  window.NagiSetup = Object.freeze({ open, openSources, isOpen: () => !layer.hidden, pendingSecrets: () => pairings.size });
})();
