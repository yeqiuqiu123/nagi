'use strict';
// Nagi appearance: the theme, System · Light · Dark, and five colours. Loaded on demand from
// Settings → Appearance. Every choice previews on the live panel behind the sheet; Cancel, Esc
// and the scrim put the saved theme back; Save hands the whole choice to the reader, whose
// answer is the truth. Direction: design/themes/creative-direction.md.
(() => {
  const T = window.NagiTheme;
  const SVGNS = 'http://www.w3.org/2000/svg';
  const POST_HEADERS = { 'Content-Type': 'application/json', 'X-Progress-Desk': '1' };
  const APPEARANCES = [['system', 'System'], ['light', 'Light'], ['dark', 'Dark']];
  const ROLE_NAMES = { accent: 'Accent', claude: 'Claude', codex: 'Codex', gemini: 'Gemini', t3: 'T3' };
  // The token each role paints, so a row's dot is the colour really drawn.
  const TOKEN = { accent: 'accent', claude: 'pv-claude-node', codex: 'pv-codex-node', gemini: 'pv-gemini-node', t3: 'hx-t3' };
  const ACCENT_PRESETS = [['#409cff', 'Blue'], ['#a985f7', 'Purple'], ['#f472b6', 'Pink'], ['#f0524d', 'Red'], ['#f59e42', 'Orange'], ['#34c27a', 'Green'], ['#8e8e93', 'Graphite']];
  const PROVIDER_PRESETS = [['#d97757', 'Terracotta'], ['#10a37f', 'Green'], ['#4285f4', 'Blue'], ['#9a7bf0', 'Violet'], ['#2bb3c0', 'Teal'], ['#c95bd0', 'Magenta'], ['#8e8e93', 'Slate']];
  const presetsFor = (role) => (role === 'accent' ? ACCENT_PRESETS : PROVIDER_PRESETS);
  const DEFAULT_SETTING = () => ({ name: T.DEFAULT.name, appearance: T.DEFAULT.appearance, colors: {} });
  const HEX = /^#?([0-9a-f]{6})$/i;

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
  // Presentation attributes only: the panel's policy refuses style attributes.
  const svg = (tag, attrs) => { const el = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v)); return el; };
  const chevron = () => { const s = svg('svg', { class: 'chev', viewBox: '0 0 12 12', 'aria-hidden': 'true' }); s.append(svg('path', { d: 'M4.5 2.5 8 6l-3.5 3.5' })); return s; };
  const paint = (el, hex) => { if (hex) el.style.setProperty('--c', hex); else el.style.removeProperty('--c'); };

  const panel = document.getElementById('panel');
  const layer = h('div', { class: 'sheet-layer appearance-layer', id: 'appearance-layer', hidden: true },
    h('div', { class: 'scrim', 'aria-hidden': 'true', onclick: () => close({ instant: false }) }));
  const sheet = h('div', { class: 'sheet appearance-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'appearance-title', 'aria-describedby': 'appearance-lede' });
  layer.append(sheet);
  panel.append(layer);

  // ---- State ------------------------------------------------------------------------------
  let host = null;
  let state = null; // { loaded, saved, pending, open, said: { role: {kind, …} }, el: {…} }
  let opener = null;

  const clone = (t) => ({ name: t.name, appearance: t.appearance, colors: { ...(t.colors || {}) } });
  function same(a, b) {
    if (a.name !== b.name || a.appearance !== b.appearance) return false;
    const ka = Object.keys(a.colors); const kb = Object.keys(b.colors);
    return ka.length === kb.length && ka.every((k) => a.colors[k] === b.colors[k]);
  }
  const scheme = () => {
    const a = state.pending.appearance;
    if (a === 'light' || a === 'dark') return a;
    return matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  };
  const resolved = (name) => T.resolve({ name: name || state.pending.name, appearance: state.pending.appearance, colors: state.pending.colors });

  // ---- The theme pictures: night on the left, day on the right, as they will really be drawn --
  // A ring in Claude's colour, a T3 bar and an accent pill beside it, and two rows: a Codex dot
  // with a title bar, a Gemini dot with a shorter secondary bar.
  const W = 106; const H = 66; const HALF = W / 2;
  const RING_R = 10; const RING_C = 2 * Math.PI * RING_R;
  function picture(name) {
    const r = resolved(name);
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid slice', 'aria-hidden': 'true', focusable: 'false' });
    [['dark', 0], ['light', HALF]].forEach(([mode, x]) => {
      const p = r[mode];
      // Each half overdraws outward so a slightly wider frame never shows a seam of the sheet.
      s.append(svg('rect', { x: mode === 'dark' ? x - 40 : x, y: -20, width: HALF + 40, height: H + 40, fill: p.bg }));
      const cx = x + 16; const cy = 20;
      s.append(svg('circle', { cx, cy, r: RING_R, fill: 'none', stroke: p.track, 'stroke-width': 3.5 }));
      s.append(svg('circle', { cx, cy, r: RING_R, fill: 'none', stroke: p['pv-claude-node'], 'stroke-width': 3.5, 'stroke-linecap': 'round',
        'stroke-dasharray': (RING_C * 0.7).toFixed(2) + ' ' + RING_C.toFixed(2), transform: `rotate(-90 ${cx} ${cy})` }));
      s.append(svg('rect', { x: x + 31, y: 13, width: 16, height: 4, rx: 2, fill: p['hx-t3'] }));
      s.append(svg('rect', { x: x + 31, y: 21, width: 12, height: 7, rx: 3.5, fill: p.accent }));
      s.append(svg('circle', { cx: x + 8.5, cy: 43, r: 2.5, fill: p['pv-codex-node'] }));
      s.append(svg('rect', { x: x + 14, y: 41.5, width: 32, height: 3, rx: 1.5, fill: p.title }));
      s.append(svg('circle', { cx: x + 8.5, cy: 53, r: 2.5, fill: p['pv-gemini-node'] }));
      s.append(svg('rect', { x: x + 14, y: 51.5, width: 22, height: 3, rx: 1.5, fill: p.secondary }));
    });
    return s;
  }

  // ---- Radio groups: arrow keys move the choice, as native radios do ----------------------------
  function radioKeys(event) {
    const keys = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1, Home: 'first', End: 'last' };
    if (!(event.key in keys)) return;
    const group = event.currentTarget;
    const items = [...group.querySelectorAll('[role="radio"]')];
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    event.preventDefault();
    const step = keys[event.key];
    const next = step === 'first' ? 0 : step === 'last' ? items.length - 1 : (i + step + items.length) % items.length;
    items[next].click();
    items[next].focus({ preventScroll: true });
  }
  // One tab stop per group: the chosen item, or the first when nothing is chosen.
  function rove(items, chosen) {
    items.forEach((el, i) => {
      const on = i === chosen;
      el.setAttribute('aria-checked', String(on));
      el.tabIndex = on || (chosen < 0 && i === 0) ? 0 : -1;
    });
  }

  // ---- Building the sheet once per open; every change updates it in place ----------------------
  function build() {
    const el = { themes: [], pics: [], segs: [], rows: {} };
    const themes = h('div', { class: 'ap-themes', role: 'radiogroup', 'aria-label': 'Theme', onkeydown: radioKeys },
      Object.keys(T.THEMES).map((name) => {
        const pic = h('span', { class: 'ap-pic' });
        const button = h('button', { type: 'button', role: 'radio', class: 'ap-theme', 'data-theme': name, 'aria-checked': 'false',
          onclick: () => choose({ name }) }, pic, h('span', { class: 'ap-theme-name', text: T.THEMES[name].label }));
        el.themes.push(button); el.pics.push([name, pic]);
        return button;
      }));
    const segs = h('div', { class: 'ap-seg', role: 'radiogroup', 'aria-label': 'Appearance', onkeydown: radioKeys },
      APPEARANCES.map(([value, label]) => {
        const button = h('button', { type: 'button', role: 'radio', class: 'ap-seg-btn', 'data-appearance': value, 'aria-checked': 'false',
          onclick: () => choose({ appearance: value }), text: label });
        el.segs.push(button);
        return button;
      }));
    const colours = h('div', { class: 'group ap-colours', role: 'group', 'aria-label': 'Colours' }, T.ROLES.map((role) => colourRow(role, el)));
    el.error = h('p', { class: 'sheet-error', id: 'appearance-error', role: 'alert', hidden: true });
    el.save = h('button', { type: 'button', class: 'btn default', id: 'appearance-save', disabled: true, text: 'Save', onclick: () => save() });
    sheet.replaceChildren(
      h('h2', { id: 'appearance-title', text: 'Appearance' }),
      h('p', { class: 'sheet-lede', id: 'appearance-lede', text: 'Saved on this computer only.' }),
      el.error, themes, segs, colours,
      h('div', { class: 'sheet-actions' },
        h('button', { type: 'button', class: 'btn', id: 'appearance-restore', text: 'Restore defaults', onclick: () => restore() }),
        h('span', { class: 'grow' }),
        h('button', { type: 'button', class: 'btn', id: 'appearance-cancel', text: 'Cancel', onclick: (e) => close({ instant: e.detail === 0 }) }),
        el.save));
    return el;
  }

  function colourRow(role, el) {
    const name = ROLE_NAMES[role];
    const id = 'ap-' + role;
    const dot = h('span', { class: 'ap-dot', 'aria-hidden': 'true' });
    const head = h('button', { type: 'button', class: 'ap-colour-head', id: id + '-head', 'aria-expanded': 'false', 'aria-controls': id + '-body',
      onclick: () => toggle(role) }, h('span', { class: 'ap-colour-name', text: name }), dot, chevron());
    const presets = [[null, 'Theme default'], ...presetsFor(role)].map(([seed, label]) => {
      const swatch = h('span', { class: 'ap-swatch', 'aria-hidden': 'true' });
      return h('button', { type: 'button', role: 'radio', class: 'ap-preset', 'aria-label': label, title: label, 'aria-checked': 'false', 'data-seed': seed || '',
        onclick: () => pick(role, seed) }, swatch);
    });
    const hex = h('input', { class: 'ap-hex', id: id + '-hex', type: 'text', inputmode: 'text', autocomplete: 'off', spellcheck: 'false', maxlength: '7',
      'aria-label': name + ' colour, hex', 'aria-describedby': id + '-note',
      oninput: (e) => typed(role, e.target.value, false), onblur: (e) => typed(role, e.target.value, true),
      onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); typed(role, e.target.value, true); } } });
    const note = h('p', { class: 'ap-note', id: id + '-note', role: 'status' });
    const body = h('div', { class: 'ap-colour-body', id: id + '-body', hidden: true },
      h('div', { class: 'ap-pick' }, h('div', { class: 'ap-presets', role: 'radiogroup', 'aria-label': name + ' colour', onkeydown: radioKeys }, presets), hex),
      note);
    el.rows[role] = { head, dot, presets, hex, note, body };
    return h('div', { class: 'ap-colour', 'data-role': role }, head, body);
  }

  // ---- Updating ---------------------------------------------------------------------------------
  function update() {
    if (!state) return;
    const { pending, el } = state;
    const mode = scheme();
    const r = resolved();
    const names = Object.keys(T.THEMES);
    rove(el.themes, names.indexOf(pending.name));
    el.pics.forEach(([name, pic]) => pic.replaceChildren(picture(name)));
    rove(el.segs, APPEARANCES.findIndex(([v]) => v === pending.appearance));
    const defaults = T.resolve({ name: pending.name, appearance: pending.appearance, colors: {} })[mode];
    for (const role of T.ROLES) {
      const row = el.rows[role];
      const open = state.open === role;
      row.head.setAttribute('aria-expanded', String(open));
      row.body.hidden = !open;
      paint(row.dot, r[mode][TOKEN[role]]);
      const seed = pending.colors[role] || null;
      row.presets.forEach((button) => {
        const s = button.dataset.seed || null;
        paint(button.firstChild, s ? T.check(role, s, pending.name).drawn[mode] : defaults[TOKEN[role]]);
      });
      rove(row.presets, row.presets.findIndex((button) => (button.dataset.seed || null) === seed));
      // The field shows what is chosen, unless the owner is typing in it or a refused or
      // unreadable value is waiting there to be corrected.
      const said = state.said[role];
      if (document.activeElement !== row.hex && !(said && (said.kind === 'refused' || said.kind === 'invalid'))) row.hex.value = seed || '';
      row.hex.placeholder = defaults[TOKEN[role]];
      const words = noteFor(role, r);
      row.note.textContent = words ? words.text : '';
      row.note.hidden = !words;
      row.note.classList.toggle('strong', !!(words && words.strong));
    }
    el.save.disabled = !!state.saving || same(pending, state.saved);
  }

  const REFUSED = {
    amber: 'Too close to the yellow that means running low. Pick another.',
    rose: 'Too close to the rose that means it needs you. Pick another.',
    // No signal in the way, but no shade of it reads on this theme.
    none: "Can't be made readable on this theme. Pick another.",
  };
  function noteFor(role, r) {
    const said = state.said[role];
    if (said && said.kind === 'invalid') return { text: 'Use six hex digits, like #7c5cff.', strong: true };
    if (said && said.kind === 'refused') return { text: REFUSED[said.reason] || REFUSED.none, strong: true };
    const c = r.colors && r.colors[role];
    if (!c || !state.pending.colors[role]) return null;
    // A saved colour this theme can't draw (a hand-edited file) is refused here too.
    if (c.status === 'refused') return { text: REFUSED[c.reason] || REFUSED.none, strong: true };
    if (c.status !== 'adjusted') return null;
    const notes = T.check(role, state.pending.colors[role], state.pending.name).notes || {};
    if (notes.dark && notes.light) return { text: 'Adjusted to stay readable at night and by day.' };
    if (notes.dark) return { text: (notes.dark === 'darker' ? 'Darkened' : 'Lightened') + ' to stay readable at night.' };
    if (notes.light) return { text: (notes.light === 'lighter' ? 'Lightened' : 'Darkened') + ' to stay readable by day.' };
    return null;
  }

  // ---- Choices ------------------------------------------------------------------------------------
  function preview() {
    T.apply(state.pending, { persist: false });
    update();
  }
  function choose(change) {
    if (!state) return;
    if (change.name && change.name !== state.pending.name) state.said = {};
    Object.assign(state.pending, change);
    preview();
  }
  function toggle(role) {
    state.open = state.open === role ? null : role;
    update();
  }
  function pick(role, seed) {
    if (!state) return;
    if (seed) {
      const result = T.check(role, seed, state.pending.name);
      if (result.status === 'refused') { state.said[role] = { kind: 'refused', reason: result.reason }; update(); return; }
      state.pending.colors[role] = seed.toLowerCase();
    } else delete state.pending.colors[role];
    delete state.said[role];
    // A preset replaces whatever was typed.
    state.el.rows[role].hex.value = state.pending.colors[role] || '';
    preview();
  }
  // Typing applies as soon as six digits make a colour; an unreadable value says so on leaving.
  function typed(role, raw, leaving) {
    if (!state) return;
    const text = raw.trim();
    const m = HEX.exec(text);
    if (!m) {
      if (leaving && text) state.said[role] = { kind: 'invalid' };
      else if (leaving) { delete state.said[role]; state.el.rows[role].hex.value = state.pending.colors[role] || ''; }
      else delete state.said[role]; // a new value is being typed: what was said no longer applies
      update();
      return;
    }
    const seed = '#' + m[1].toLowerCase();
    if (leaving && text !== seed) state.el.rows[role].hex.value = seed;
    const result = T.check(role, seed, state.pending.name);
    if (result.status === 'invalid') { state.said[role] = { kind: 'invalid' }; update(); return; }
    if (result.status === 'refused') { state.said[role] = { kind: 'refused', reason: result.reason }; update(); return; }
    delete state.said[role];
    if (state.pending.colors[role] === seed) { update(); return; }
    state.pending.colors[role] = seed;
    preview();
  }
  function restore() {
    if (!state) return;
    state.pending = DEFAULT_SETTING();
    state.said = {};
    T.ROLES.forEach((role) => { state.el.rows[role].hex.value = ''; });
    preview();
  }

  // ---- Saving: the settings loaded at open, plus the theme; the reader's answer is the truth ------
  async function save() {
    if (!state || state.saving || same(state.pending, state.saved)) return;
    state.saving = true; state.el.error.hidden = true; update();
    const body = { ...state.loaded, theme: clone(state.pending) };
    let saved = null;
    try {
      const response = await fetch('/api/settings', { method: 'POST', cache: 'no-store', headers: POST_HEADERS, body: JSON.stringify(body) });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      saved = (await response.json()).settings;
      if (!saved || typeof saved !== 'object') throw new Error('answer');
    } catch {
      if (!state) return;
      state.saving = false;
      state.el.error.textContent = "Couldn't save. Your appearance is unchanged.";
      state.el.error.hidden = false;
      update(); // the preview stays, so nothing chosen is lost
      return;
    }
    if (!state) return;
    host.saved(saved);
    state.saved = clone(T.normalize(saved.theme || state.pending));
    T.apply(state.saved);
    finish({ instant: true });
  }

  // ---- Open and close ---------------------------------------------------------------------------
  function show(options) {
    opener = document.activeElement;
    layer.classList.toggle('instant', !options || options.instant !== false);
    layer.hidden = false;
    void layer.offsetHeight; // start the transition from the closed state
    layer.dataset.open = 'true';
    panel.querySelectorAll('.pinned, .scroll, .rail').forEach((el) => { el.inert = true; });
  }

  // Cancel, Esc and the scrim: the saved theme comes back.
  function close(options) {
    if (!state) return;
    T.apply(state.saved);
    finish(options);
  }
  function finish(options) {
    if (layer.hidden) return;
    const instant = !options || options.instant !== false;
    layer.classList.toggle('instant', instant);
    layer.dataset.open = 'false';
    panel.querySelectorAll('.pinned, .scroll, .rail').forEach((el) => { el.inert = false; });
    const done = () => { if (layer.dataset.open !== 'true') { layer.hidden = true; sheet.replaceChildren(); } };
    if (instant || matchMedia('(prefers-reduced-motion: reduce)').matches) done(); else setTimeout(done, 200);
    state = null;
    const back = opener && opener.isConnected && !layer.contains(opener) ? opener : host && host.opener();
    if (back) back.focus({ preventScroll: true });
    if (host) host.refresh();
  }

  async function open(nextHost, options) {
    if (state) return;
    host = nextHost;
    const settings = host.settings() || {};
    const theme = clone(T.normalize(settings.theme || T.current()));
    const loaded = { ...settings }; delete loaded.theme;
    state = { loaded, saved: theme, pending: clone(theme), open: null, said: {}, saving: false, el: null };
    state.el = build();
    show(options);
    update();
    state.el.themes[Object.keys(T.THEMES).indexOf(theme.name)].focus({ preventScroll: true });
    // The freshest saved settings, so Save never posts a stale value; the theme only if
    // nothing has been chosen yet.
    try {
      const response = await fetch('/api/settings', { cache: 'no-store' });
      if (!response.ok) return;
      const value = await response.json();
      if (!state || !value || !value.settings) return;
      const fresh = { ...value.settings }; delete fresh.theme;
      state.loaded = fresh;
      if (value.settings.theme && same(state.pending, state.saved)) {
        state.saved = clone(T.normalize(value.settings.theme));
        state.pending = clone(state.saved);
        preview();
      }
    } catch {}
  }

  // System follows the desktop: the drawn dots follow it too while the sheet is open.
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (state) update(); });

  // Esc cancels (instantly), wherever focus happens to be, before the panel's own Esc sees it.
  document.addEventListener('keydown', (event) => {
    if (!state || event.key !== 'Escape') return;
    event.preventDefault(); event.stopPropagation();
    close({ instant: true });
  }, true);
  // Tab stays inside the sheet, one stop per radio group.
  layer.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    const items = [...sheet.querySelectorAll('button:not(:disabled), input:not(:disabled)')].filter((el) => el.tabIndex >= 0 && el.offsetParent !== null);
    const i = items.indexOf(document.activeElement);
    if (event.shiftKey && i <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
    else if (!event.shiftKey && i === items.length - 1) { event.preventDefault(); items[0].focus(); }
  });

  window.NagiAppearance = Object.freeze({ open, isOpen: () => !!state });
})();
