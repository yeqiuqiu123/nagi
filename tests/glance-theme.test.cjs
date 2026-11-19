'use strict';
// Theme tests: every built-in theme clears the floors in design/themes/project-bar.md in both
// appearances, the stylesheet's fallback is Violet, and any custom pick is either drawn
// readable or refused (design/themes/creative-direction.md, "The custom palette").
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const T = require('../web/glance-theme.js');

// ---- The lead's pairs, ported from design/themes/palettes.mjs (checks) --------------------
const hex2rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const lin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = (h) => { const [r, g, b] = hex2rgb(h).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const cr = (a, b) => { const x = lum(a); const y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
const mix = (a, b, p) => { const x = hex2rgb(a); const y = hex2rgb(b); return '#' + x.map((v, i) => Math.round(v * p + y[i] * (1 - p)).toString(16).padStart(2, '0')).join(''); };
function checks(p) {
  const out = [];
  const need = (fg, bgs, min, what) => bgs.forEach((b) => { const r = cr(p[fg], p[b]); out.push({ fg, on: b, r, min, ok: r >= min, what }); });
  const surf = ['bg', 'hover', 'wash', 'wash-amber', 'sheet', 'control'];
  need('title', surf, 12, 'title');
  need('title-context', ['bg', 'hover'], 10, 'context title');
  need('secondary', surf, 7, 'secondary');
  need('tertiary', ['bg', 'hover', 'sheet', 'control'], 4.5, 'tertiary');
  need('stroke', ['bg', 'hover', 'wash', 'wash-amber', 'sheet'], 3, 'stroke');
  need('rose-text', ['bg', 'hover', 'wash'], 7, 'rose word'); need('amber-text', ['bg', 'hover', 'wash-amber'], 7, 'amber word');
  need('rose', ['bg', 'hover', 'wash'], 3, 'rose mark'); need('amber', ['bg', 'hover', 'wash-amber'], 3, 'amber mark');
  for (const k of ['claude', 'codex', 'gemini']) { need('pv-' + k, ['bg', 'hover'], 7, 'provider word'); need('pv-' + k + '-node', ['bg', 'hover'], 3, 'provider mark'); }
  for (const k of ['t3', 'codex', 'claude']) {
    const chip = cr(p['hx-' + k], mix(p['hx-' + k], p.bg, 0.16)); out.push({ fg: 'hx-' + k, on: 'chip tint', r: chip, min: 4.5, ok: chip >= 4.5 });
    const tile = cr(p['hx-' + k], mix(p['hx-' + k], p.control, 0.16)); out.push({ fg: 'hx-' + k, on: 'tile tint', r: tile, min: 4.5, ok: tile >= 4.5 });
  }
  for (const k of ['green', 'red', 'blue']) { need(k, surf, 3, 'status mark'); need(k + '-text', ['bg', 'hover'], 7, 'status word'); need(k + '-text', ['wash', 'wash-amber', 'sheet', 'control'], 4.5, 'status word'); }
  need('control-border', ['control', 'sheet'], 3, 'control border'); need('focus', ['bg', 'hover', 'sheet', 'control'], 3, 'focus');
  need('accent', ['bg', 'hover', 'sheet', 'control'], 3, 'accent');
  const ink = cr(p['accent-ink'], p.accent); out.push({ fg: 'accent-ink', on: 'accent', r: ink, min: 4.5, ok: ink >= 4.5 });
  // The default button is the accent and its ink.
  const btn = cr(p['default-btn-text'] || p['accent-ink'], p['default-btn'] || p.accent); out.push({ fg: 'default-btn-text', on: 'default-btn', r: btn, min: 4.5, ok: btn >= 4.5 });
  return out;
}
const failures = (p) => checks(p).filter((x) => !x.ok).map((x) => `${x.fg} on ${x.on} ${x.r.toFixed(2)} < ${x.min}`);

const NAMES = Object.keys(T.THEMES);
const REFUSED = ['#e6c84a', '#f0b030', '#ffff00', '#ffd60a', '#ff7aa5', '#f25fa5'];
const ACCEPTED = ['#d97757', '#10a37f', '#4285f4', '#9a7bf0', '#2bb3c0', '#c95bd0', '#8e8e93', '#86b83a'];
const SPREAD = ['#000000', '#ffffff', '#808080', '#ffff00', '#ff0000', '#00ff00', '#0000ff', ...REFUSED, ...ACCEPTED];
const MARK = { accent: 'accent', claude: 'pv-claude-node', codex: 'pv-codex-node', gemini: 'pv-gemini-node', t3: 'hx-t3' };
const ROLE_TOKENS = { accent: ['accent', 'accent-ink', 'focus', 'default-btn', 'default-btn-text'], claude: ['pv-claude', 'pv-claude-node', 'hx-claude'],
  codex: ['pv-codex', 'pv-codex-node', 'hx-codex'], gemini: ['pv-gemini', 'pv-gemini-node'], t3: ['hx-t3'] };

test('three themes, each with a night and a day, in the shape the panel paints', () => {
  assert.deepEqual(NAMES, ['violet', 'graphite', 'tide']);
  assert.deepEqual(NAMES.map((n) => T.THEMES[n].label), ['Violet', 'Graphite', 'Tide']);
  assert.deepEqual(T.ROLES, ['accent', 'claude', 'codex', 'gemini', 't3']);
  assert.deepEqual(T.DEFAULT, { name: 'violet', appearance: 'system', colors: {} });
  const keys = Object.keys(T.THEMES.violet.dark).sort();
  for (const name of NAMES) for (const scheme of ['dark', 'light']) {
    assert.deepEqual(Object.keys(T.THEMES[name][scheme]).sort(), keys, `${name} ${scheme}`);
    for (const value of Object.values(T.THEMES[name][scheme])) assert.match(value, /^#[0-9a-f]{6}$/);
  }
});

test('every built-in theme clears every floor, night and day', () => {
  for (const name of NAMES) {
    const resolved = T.resolve({ name, appearance: 'system', colors: {} });
    for (const scheme of ['dark', 'light']) {
      assert.deepEqual(failures(T.THEMES[name][scheme]), [], `${name} ${scheme} palette`);
      assert.deepEqual(failures(resolved[scheme]), [], `${name} ${scheme} resolved`);
      assert.equal(resolved[scheme]['default-btn'], T.THEMES[name][scheme].accent);
      assert.equal(resolved[scheme]['default-btn-text'], T.THEMES[name][scheme]['accent-ink']);
    }
  }
});

test("the stylesheet's fallback blocks are Violet, token for token", () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'web', 'glance-v2.css'), 'utf8');
  const night = css.match(/^:root \{([\s\S]*?)^\}/m)[1];
  const day = css.match(/@media \(prefers-color-scheme: light\) \{\s*:root \{([\s\S]*?)\n  \}/)[1];
  const tokens = (block) => Object.fromEntries([...block.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
  for (const [scheme, block] of [['dark', night], ['light', day]]) {
    const found = tokens(block);
    for (const [token, hex] of Object.entries(T.THEMES.violet[scheme])) assert.equal(found[token], hex, `--${token} (${scheme})`);
    assert.equal(found['default-btn'], 'var(--accent)');
    assert.equal(found['default-btn-text'], 'var(--accent-ink)');
  }
  // Project icons follow the resolved appearance, never the system's alone.
  assert.doesNotMatch(css, /prefers-color-scheme: light\)\s*\{\s*\.pi-/);
  assert.match(css, /:root\[data-scheme="light"\] \.pi-gray/);
});

test('any pick on any theme is drawn readable in both appearances, or refused to the default', () => {
  for (const name of NAMES) for (const role of T.ROLES) for (const seed of SPREAD) {
    const resolved = T.resolve({ name, appearance: 'dark', colors: { [role]: seed } });
    const outcome = resolved.colors[role];
    assert.ok(['ok', 'adjusted', 'refused'].includes(outcome.status), `${name} ${role} ${seed}`);
    for (const scheme of ['dark', 'light']) {
      assert.deepEqual(failures(resolved[scheme]), [], `${name} ${role} ${seed} ${scheme} (${outcome.status})`);
      assert.equal(outcome.drawn[scheme], resolved[scheme][MARK[role]], `${name} ${role} ${seed} drawn ${scheme}`);
      if (outcome.status === 'refused') {
        for (const token of ROLE_TOKENS[role]) {
          const builtin = token === 'default-btn' ? 'accent' : token === 'default-btn-text' ? 'accent-ink' : token;
          assert.equal(resolved[scheme][token], T.THEMES[name][scheme][builtin], `${name} ${role} ${seed} ${token} falls back`);
        }
      }
    }
    // Only the role picked changes; every other token is the theme's own.
    for (const scheme of ['dark', 'light']) for (const [token, hex] of Object.entries(T.THEMES[name][scheme])) {
      if (!ROLE_TOKENS[role].includes(token)) assert.equal(resolved[scheme][token], hex, `${name} ${role} ${seed} leaves --${token}`);
    }
    const checked = T.check(role, seed, name);
    assert.equal(checked.status, outcome.status);
    assert.deepEqual(checked.drawn, outcome.drawn);
  }
});

test('a provider pick on yellow or rose is refused on every theme; brand and preset picks pass', () => {
  for (const name of NAMES) for (const role of ['claude', 'codex', 'gemini']) {
    for (const seed of REFUSED) {
      const got = T.check(role, seed, name);
      assert.equal(got.status, 'refused', `${name} ${role} ${seed}`);
      assert.ok(['rose', 'amber'].includes(got.reason));
      assert.deepEqual(got.drawn, { dark: T.THEMES[name].dark[MARK[role]], light: T.THEMES[name].light[MARK[role]] });
    }
    for (const seed of ACCEPTED) assert.notEqual(T.check(role, seed, name).status, 'refused', `${name} ${role} ${seed}`);
  }
  assert.equal(T.check('claude', '#e6c84a', 'violet').reason, 'amber');
  assert.equal(T.check('codex', '#ff7aa5', 'tide').reason, 'rose');
  // Accent and T3 never paint a signal mark, so they are only made readable.
  for (const name of NAMES) for (const seed of REFUSED) {
    assert.notEqual(T.check('accent', seed, name).status, 'refused');
    assert.notEqual(T.check('t3', seed, name).status, 'refused');
  }
});

test('a pick that already passes is drawn as picked; a nudge says which way', () => {
  // Claude's own orange is its night mark on Violet as picked. By day it is drawn a shade
  // darker, too little to see, so nothing is said about it.
  const claude = T.check('claude', '#D97757', 'violet');
  assert.equal(claude.drawn.dark, '#d97757');
  assert.notEqual(claude.drawn.light, '#d97757');
  assert.equal(claude.status, 'ok');
  // A pick that has to move a long way says so, and which way.
  const pale = T.check('claude', '#ffe0e0', 'violet');
  assert.equal(pale.status, 'adjusted');
  assert.equal(pale.notes.dark, null);
  assert.equal(pale.notes.light, 'darker');
  const black = T.check('gemini', '#000000', 'graphite');
  assert.equal(black.status, 'adjusted');
  assert.equal(black.notes.dark, 'lighter');
  // Achromatic picks derive a readable grey.
  for (const seed of ['#000000', '#808080', '#ffffff']) for (const scheme of ['dark', 'light']) {
    const [r, g, b] = hex2rgb(T.check('codex', seed, 'tide').drawn[scheme]);
    assert.ok(Math.max(r, g, b) - Math.min(r, g, b) <= 2, `${seed} stays grey`);
  }
  // A custom accent becomes the focus ring and the default button too.
  const accent = T.resolve({ name: 'graphite', colors: { accent: '#ff8800' } });
  for (const scheme of ['dark', 'light']) {
    assert.equal(accent.dark.focus, accent.dark.accent);
    assert.equal(accent[scheme]['default-btn'], accent[scheme].accent);
    assert.ok(cr(accent[scheme]['accent-ink'], accent[scheme].accent) >= 4.5);
  }
  assert.equal(T.check('nope', '#ff8800', 'violet').status, 'invalid');
  assert.equal(T.check('accent', 'ff8800', 'violet').status, 'invalid');
  assert.equal(T.check('accent', '#ff8800', 'unknown').drawn.dark, T.check('accent', '#ff8800', 'violet').drawn.dark);
});

test('the refuse threshold sits between the two lists with room on both sides', () => {
  const nearest = (seed) => {
    let min = Infinity;
    for (const name of NAMES) for (const role of ['claude', 'codex', 'gemini']) {
      const got = T.inspect(role, seed, name);
      for (const scheme of ['dark', 'light']) if (got.distance[scheme]) min = Math.min(min, got.distance[scheme].rose, got.distance[scheme].amber);
    }
    return min;
  };
  // Saturated yellows are caught by hue as well, so they may sit just outside the distance.
  const BY_HUE = ['#ffff00', '#ffd60a'];
  const refused = Math.max(...REFUSED.filter((seed) => !BY_HUE.includes(seed)).map(nearest)); const accepted = Math.min(...ACCEPTED.map(nearest));
  assert.ok(refused < T.SIGNAL_DISTANCE && T.SIGNAL_DISTANCE <= accepted, `${refused} < ${T.SIGNAL_DISTANCE} <= ${accepted}`);
  assert.ok(T.SIGNAL_DISTANCE >= 0.08 && T.SIGNAL_DISTANCE <= 0.1);
});

test('normalize drops what it cannot use and resolve never throws', () => {
  assert.deepEqual(T.normalize(null), { name: 'violet', appearance: 'system', colors: {} });
  assert.deepEqual(T.normalize({ name: 'tide', appearance: 'dark', colors: { accent: '#FF8800', claude: '#9a7bf0' } }),
    { name: 'tide', appearance: 'dark', colors: { accent: '#ff8800', claude: '#9a7bf0' } });
  assert.deepEqual(T.normalize({ name: 'solarized', appearance: 'dim', colors: { rose: '#ff0000', amber: '#00ff00', codex: '#12345', gemini: 'blue', t3: 7, accent: '#gggggg' } }),
    { name: 'violet', appearance: 'system', colors: {} });
  assert.deepEqual(T.normalize({ name: 'graphite', colors: ['#ff0000'] }), { name: 'graphite', appearance: 'system', colors: {} });
  assert.deepEqual(T.normalize({ name: 'toString', appearance: 'light', colors: Object.create({ accent: '#ff0000' }) }), { name: 'violet', appearance: 'light', colors: {} });
  for (const bad of [undefined, null, 7, 'tide', [], { name: {} }, { colors: null }, { colors: 'x' }, { colors: { claude: null } },
    { name: '__proto__', colors: { __proto__: { claude: '#ff0000' } } }, JSON.parse('{"colors":{"__proto__":{"t3":"#ffffff"}}}')]) {
    const resolved = T.resolve(bad);
    assert.equal(resolved.name, 'violet');
    assert.deepEqual(failures(resolved.dark), []);
    assert.deepEqual(failures(resolved.light), []);
    for (const role of T.ROLES) assert.equal(resolved.colors[role].status, 'default');
  }
  // Painting is browser-only; in node it records the choice and touches nothing.
  assert.deepEqual(T.apply({ name: 'tide', appearance: 'light' }, { persist: false }), { name: 'tide', appearance: 'light', colors: {} });
  assert.equal(T.scheme(), 'light');
  assert.deepEqual(T.current(), { name: 'tide', appearance: 'light', colors: {} });
  T.apply(T.DEFAULT, { persist: false });
  assert.equal(T.scheme(), 'dark');
  assert.ok(Math.abs(T.contrast('#000000', '#ffffff') - 21) < 1e-9);
});
