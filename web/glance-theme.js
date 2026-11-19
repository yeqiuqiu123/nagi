'use strict';
// Nagi themes: three built-in palettes (design/themes/palettes.mjs, measured by the lead) and
// the guard that turns one picked colour per role into marks and words that stay readable in
// the night and the day of the chosen theme (design/themes/creative-direction.md, Part 1).
// Pure functions run in node with no DOM; apply() paints document.documentElement through the
// CSSOM only (the page's CSP forbids inline style attributes and injected <style>).
// Loaded by a plain, non-deferred <script> in the head, so the cached theme is on the first frame.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.NagiTheme = api;
})(typeof self !== 'undefined' ? self : this, function () {
  // Copied exactly from design/themes/palettes.mjs; tests/glance-theme.test.cjs proves the floors.
  const THEMES = {
    violet: { label: 'Violet',
      dark: {
        bg: '#18131d', sheet: '#241d2b', scrim: '#0d0a10', title: '#f5f1f8', 'title-context': '#e2dbe9', secondary: '#cdc4d6',
        tertiary: '#a397b0', stroke: '#9486a3', hair: '#3a3142', track: '#463c50', rose: '#ff7aa5', 'rose-text': '#ff9dbb',
        wash: '#2a1b28', amber: '#e6c84a', 'amber-text': '#ecd27a', 'wash-amber': '#272118', 'pv-claude': '#e2977f', 'pv-claude-node': '#d97757',
        'pv-codex': '#13c197', 'pv-codex-node': '#10a37f', 'pv-gemini': '#7caaf7', 'pv-gemini-node': '#4285f4', 'hx-t3': '#f58ac0', 'hx-codex': '#13c197',
        'hx-claude': '#e2977f', focus: '#cdc4d6', hover: '#211a27', control: '#2c2433', 'control-border': '#8b7f99', 'control-text': '#f5f1f8',
        green: '#3fc98a', 'green-text': '#6fdcaa', red: '#ff4d42', 'red-text': '#ff958c', blue: '#5b9dff', 'blue-text': '#8dbbff',
        accent: '#b59cf7', 'accent-ink': '#18131d',
      },
      light: {
        bg: '#f2f0f6', sheet: '#fbfafd', scrim: '#c9c4d3', title: '#17121c', 'title-context': '#2b2432', secondary: '#403849',
        tertiary: '#645b70', stroke: '#6b6280', hair: '#dcd7e4', track: '#d2cbdc', rose: '#c8235f', 'rose-text': '#8f103c',
        wash: '#efe0ea', amber: '#7d6800', 'amber-text': '#594a00', 'wash-amber': '#f0ead2', 'pv-claude': '#7b331c', 'pv-claude-node': '#d15a34',
        'pv-codex': '#085240', 'pv-codex-node': '#0e9071', 'pv-gemini': '#0943a3', 'pv-gemini-node': '#317af3', 'hx-t3': '#8f1245', 'hx-codex': '#085240',
        'hx-claude': '#7b331c', focus: '#403849', hover: '#e8e5ee', control: '#ffffff', 'control-border': '#847a97', 'control-text': '#17121c',
        green: '#16804f', 'green-text': '#0b5231', red: '#d92d20', 'red-text': '#8e1a13', blue: '#2f6fe0', 'blue-text': '#123f96',
        accent: '#6a45d1', 'accent-ink': '#ffffff',
      },
    },
    graphite: { label: 'Graphite',
      dark: {
        bg: '#1c1c1e', sheet: '#272729', scrim: '#0b0b0c', title: '#f5f5f7', 'title-context': '#e3e3e8', secondary: '#c9c9cf',
        tertiary: '#a1a1a8', stroke: '#8e8e93', hair: '#38383a', track: '#48484a', rose: '#ff6f91', 'rose-text': '#ff9bb1',
        wash: '#2f1e24', amber: '#f2cc3d', 'amber-text': '#f5d76e', 'wash-amber': '#2b2618', 'pv-claude': '#eaa48e', 'pv-claude-node': '#d97757',
        'pv-codex': '#3fd0a9', 'pv-codex-node': '#10a37f', 'pv-gemini': '#8fb6f9', 'pv-gemini-node': '#4285f4', 'hx-t3': '#f794c6', 'hx-codex': '#3fd0a9',
        'hx-claude': '#eaa48e', focus: '#409cff', hover: '#242426', control: '#303032', 'control-border': '#8e8e93', 'control-text': '#f5f5f7',
        green: '#32d074', 'green-text': '#6fe09b', red: '#ff4d42', 'red-text': '#ff9d95', blue: '#409cff', 'blue-text': '#85bcff',
        accent: '#409cff', 'accent-ink': '#0b0b0c',
      },
      light: {
        bg: '#ececee', sheet: '#f6f6f8', scrim: '#bcbcc2', title: '#1d1d1f', 'title-context': '#2c2c2e', secondary: '#3a3a3c',
        tertiary: '#5e5e63', stroke: '#6e6e73', hair: '#d6d6db', track: '#cdcdd2', rose: '#d30f45', 'rose-text': '#8f002a',
        wash: '#f3dfe4', amber: '#806600', 'amber-text': '#584600', 'wash-amber': '#efe8cf', 'pv-claude': '#78311a', 'pv-claude-node': '#cf5630',
        'pv-codex': '#075240', 'pv-codex-node': '#0d8a6c', 'pv-gemini': '#08409e', 'pv-gemini-node': '#2f74ea', 'hx-t3': '#8f1245', 'hx-codex': '#075240',
        'hx-claude': '#78311a', focus: '#0066d6', hover: '#e3e3e6', control: '#ffffff', 'control-border': '#7c7c82', 'control-text': '#1d1d1f',
        green: '#1b8048', 'green-text': '#0c5230', red: '#d92d20', 'red-text': '#8e1a13', blue: '#0066d6', 'blue-text': '#0a3f8f',
        accent: '#0066d6', 'accent-ink': '#ffffff',
      },
    },
    tide: { label: 'Tide',
      dark: {
        bg: '#0f1a1f', sheet: '#19272e', scrim: '#070d10', title: '#eef6f7', 'title-context': '#d8e5e8', secondary: '#bdd0d5',
        tertiary: '#8fa7ae', stroke: '#7f989f', hair: '#263840', track: '#30454e', rose: '#ff7aa5', 'rose-text': '#ff9dbb',
        wash: '#2a1c2a', amber: '#e9c84a', 'amber-text': '#efd57c', 'wash-amber': '#252416', 'pv-claude': '#e89d86', 'pv-claude-node': '#dd7a5a',
        'pv-codex': '#2ccb9f', 'pv-codex-node': '#12a983', 'pv-gemini': '#84b0f8', 'pv-gemini-node': '#4a8af5', 'hx-t3': '#f58ac0', 'hx-codex': '#2ccb9f',
        'hx-claude': '#e89d86', focus: '#62d3d8', hover: '#16242b', control: '#213138', 'control-border': '#7f989f', 'control-text': '#eef6f7',
        green: '#3fc98a', 'green-text': '#6fdcaa', red: '#ff4d42', 'red-text': '#ff958c', blue: '#5b9dff', 'blue-text': '#8dbbff',
        accent: '#62d3d8', 'accent-ink': '#070d10',
      },
      light: {
        bg: '#eaf2f2', sheet: '#f6fbfb', scrim: '#b9c9cb', title: '#0d1b1f', 'title-context': '#1d2e33', secondary: '#2f4248',
        tertiary: '#52666c', stroke: '#5c7279', hair: '#cfdcde', track: '#c4d4d7', rose: '#c8235f', 'rose-text': '#8f103c',
        wash: '#f0dfe8', amber: '#7a6500', 'amber-text': '#564700', 'wash-amber': '#ece9cb', 'pv-claude': '#7b331c', 'pv-claude-node': '#cc5530',
        'pv-codex': '#075240', 'pv-codex-node': '#0c876a', 'pv-gemini': '#0943a3', 'pv-gemini-node': '#2f74ea', 'hx-t3': '#8f1245', 'hx-codex': '#075240',
        'hx-claude': '#7b331c', focus: '#0a737a', hover: '#dde9ea', control: '#ffffff', 'control-border': '#6c838a', 'control-text': '#0d1b1f',
        green: '#157a4c', 'green-text': '#0a4f2f', red: '#d92d20', 'red-text': '#8e1a13', blue: '#2a6bdc', 'blue-text': '#123f96',
        accent: '#0a737a', 'accent-ink': '#ffffff',
      },
    },
  };
  const ROLES = ['accent', 'claude', 'codex', 'gemini', 't3'];
  const APPEARANCES = ['system', 'light', 'dark'];
  const SCHEMES = ['dark', 'light'];
  const DEFAULT = Object.freeze({ name: 'violet', appearance: 'system', colors: Object.freeze({}) });
  const HEX = /^#[0-9a-f]{6}$/i;
  const CACHE_KEY = 'nagi-theme';
  // A provider mark this close to rose or yellow (OKLab distance) would read as a signal.
  const SIGNAL_DISTANCE = 0.09;
  // Yellow is also refused by hue: a saturated mark within this many degrees of the theme's
  // yellow reads as "running low" however light or dark it was nudged.
  const YELLOW_HUE = 20; const YELLOW_CHROMA = 0.06;
  // A mark that moved further than this in OKLab lightness was visibly adjusted.
  const VISIBLE_SHIFT = 0.1;
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

  // ---- Colour arithmetic (WCAG 2 contrast, sRGB mixing, OKLab/OKLCH) ---------------------
  const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const rgbToHex = (rgb) => '#' + rgb.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
  const toLinear = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const toGamma = (c) => 255 * (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
  function luminance(hex) { const [r, g, b] = hexToRgb(hex).map(toLinear); return 0.2126 * r + 0.7152 * g + 0.0722 * b; }
  function contrast(a, b) { const x = luminance(a); const y = luminance(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  // color-mix(in srgb, a p, b): the tint a chip or tile sits on.
  function mix(a, b, p) { const x = hexToRgb(a); const y = hexToRgb(b); return rgbToHex(x.map((v, i) => v * p + y[i] * (1 - p))); }

  function linearToOklab([r, g, b]) {
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
      1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
      0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  }
  function oklabToLinear([L, a, b]) {
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
  }
  const oklab = (hex) => linearToOklab(hexToRgb(hex).map(toLinear));
  function oklch(hex) { const [L, a, b] = oklab(hex); return [L, Math.hypot(a, b), Math.atan2(b, a)]; }
  function distance(x, y) { const p = oklab(x); const q = oklab(y); return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); }
  const inGamut = (rgb) => rgb.every((v) => v >= -1e-6 && v <= 1 + 1e-6);
  // The seed's hue and chroma at lightness L, chroma reduced only as far as sRGB needs.
  function atLightness(L, C, h) {
    const lab = (c) => oklabToLinear([L, c * Math.cos(h), c * Math.sin(h)]);
    let rgb = lab(C);
    if (!inGamut(rgb)) {
      let low = 0; let high = C;
      for (let i = 0; i < 24; i++) { const mid = (low + high) / 2; if (inGamut(lab(mid))) low = mid; else high = mid; }
      rgb = lab(low);
    }
    return rgbToHex(rgb.map((v) => toGamma(Math.max(0, Math.min(1, v)))));
  }
  // The nearest lightness (from the seed's own) at which `pass` holds; ties go the way that
  // gains contrast on this appearance's sheet. The seed itself is kept when it already passes.
  function nearest(seed, pass, scheme) {
    if (pass(seed)) return seed;
    const [L0, C, h] = oklch(seed);
    const first = scheme === 'dark' ? 1 : -1;
    for (let step = 1; step <= 1000; step++) {
      for (const sign of [first, -first]) {
        const L = L0 + sign * step / 1000;
        if (L < 0 || L > 1) continue;
        const hex = atLightness(L, C, h);
        if (pass(hex)) return hex;
      }
    }
    return null;
  }

  // ---- Settings -----------------------------------------------------------------------
  function normalize(setting) {
    const value = setting && typeof setting === 'object' && !Array.isArray(setting) ? setting : {};
    const name = typeof value.name === 'string' && own(THEMES, value.name) ? value.name : DEFAULT.name;
    const appearance = APPEARANCES.includes(value.appearance) ? value.appearance : DEFAULT.appearance;
    const colors = {};
    const given = value.colors && typeof value.colors === 'object' && !Array.isArray(value.colors) ? value.colors : {};
    for (const role of ROLES) {
      if (own(given, role) && typeof given[role] === 'string' && HEX.test(given[role])) colors[role] = given[role].toLowerCase();
    }
    return { name, appearance, colors };
  }

  // Which token is the drawn mark for each role, and what each derived token must clear.
  const MARK = { accent: 'accent', claude: 'pv-claude-node', codex: 'pv-codex-node', gemini: 'pv-gemini-node', t3: 'hx-t3' };
  const PROVIDERS = ['claude', 'codex', 'gemini'];
  const clears = (hex, palette, surfaces, min) => surfaces.every((s) => contrast(hex, palette[s]) >= min);
  // A chip's text on its own tint, on the sheet and on a settings tile.
  const chipClears = (hex, palette) => contrast(hex, mix(hex, palette.bg, 0.16)) >= 4.5 && contrast(hex, mix(hex, palette.control, 0.16)) >= 4.5;

  // One role, one appearance: the tokens drawn from the seed, or null when nothing can work.
  function deriveScheme(role, seed, palette, scheme) {
    if (role === 'accent') {
      const accent = nearest(seed, (hex) => clears(hex, palette, ['bg', 'hover', 'sheet', 'control'], 3), scheme);
      if (!accent) return null;
      // The ink on the accent: the end with the most contrast.
      const ink = [palette.bg, palette.title, '#ffffff', '#000000'].reduce((best, hex) => (contrast(hex, accent) > contrast(best, accent) ? hex : best));
      return { mark: accent, tokens: { accent, 'accent-ink': ink, focus: accent, 'default-btn': accent, 'default-btn-text': ink } };
    }
    if (role === 't3') {
      const chip = nearest(seed, (hex) => chipClears(hex, palette), scheme);
      return chip && { mark: chip, tokens: { 'hx-t3': chip } };
    }
    const mark = nearest(seed, (hex) => clears(hex, palette, ['bg', 'hover'], 3), scheme);
    const chip = role !== 'gemini';
    const word = nearest(seed, (hex) => clears(hex, palette, ['bg', 'hover'], 7) && (!chip || chipClears(hex, palette)), scheme);
    if (!mark || !word) return null;
    const tokens = { ['pv-' + role + '-node']: mark, ['pv-' + role]: word };
    if (chip) tokens['hx-' + role] = word;
    return { mark, tokens };
  }

  function derive(role, seed, name) {
    const theme = THEMES[name];
    const out = { status: 'ok', reason: null, drawn: {}, notes: {}, tokens: {}, distance: {} };
    const L0 = oklch(seed)[0];
    for (const scheme of SCHEMES) {
      const palette = theme[scheme];
      const got = deriveScheme(role, seed, palette, scheme);
      if (!got) { out.status = 'refused'; out.reason = null; break; }
      out.drawn[scheme] = got.mark; out.tokens[scheme] = got.tokens;
      const shift = oklch(got.mark)[0] - L0;
      out.notes[scheme] = Math.abs(shift) > VISIBLE_SHIFT ? (shift > 0 ? 'lighter' : 'darker') : null;
      if (PROVIDERS.includes(role)) {
        const rose = distance(got.mark, palette.rose); const amber = distance(got.mark, palette.amber);
        out.distance[scheme] = { rose, amber };
        if (out.status !== 'refused' && Math.min(rose, amber) < SIGNAL_DISTANCE) { out.status = 'refused'; out.reason = rose <= amber ? 'rose' : 'amber'; }
        const [, chroma, hue] = oklch(got.mark);
        const apart = Math.abs(((hue - oklch(palette.amber)[2]) * 180 / Math.PI + 540) % 360 - 180);
        if (out.status !== 'refused' && chroma >= YELLOW_CHROMA && apart < YELLOW_HUE) { out.status = 'refused'; out.reason = 'amber'; }
      }
    }
    if (out.status === 'ok' && SCHEMES.some((s) => out.notes[s])) out.status = 'adjusted';
    return out;
  }

  const fallback = (role, name) => ({ dark: THEMES[name].dark[MARK[role]], light: THEMES[name].light[MARK[role]] });

  // For the picker: what this seed becomes for this role on this theme.
  function check(role, seedHex, themeName) {
    const name = typeof themeName === 'string' && own(THEMES, themeName) ? themeName : DEFAULT.name;
    if (!ROLES.includes(role)) return { status: 'invalid', reason: null, drawn: { dark: null, light: null }, notes: { dark: null, light: null } };
    if (typeof seedHex !== 'string' || !HEX.test(seedHex)) return { status: 'invalid', reason: null, drawn: fallback(role, name), notes: { dark: null, light: null } };
    const got = derive(role, seedHex.toLowerCase(), name);
    if (got.status === 'refused') return { status: 'refused', reason: got.reason, drawn: fallback(role, name), notes: { dark: null, light: null } };
    return { status: got.status, reason: null, drawn: { dark: got.drawn.dark, light: got.drawn.light }, notes: { dark: got.notes.dark, light: got.notes.light } };
  }

  // Every token for both appearances, with each custom colour's outcome.
  function resolve(setting) {
    const value = normalize(setting);
    const theme = THEMES[value.name];
    const out = { name: value.name, appearance: value.appearance, dark: {}, light: {}, colors: {} };
    for (const scheme of SCHEMES) {
      const palette = theme[scheme];
      out[scheme] = { ...palette, 'default-btn': palette.accent, 'default-btn-text': palette['accent-ink'] };
    }
    for (const role of ROLES) {
      const seed = own(value.colors, role) ? value.colors[role] : null;
      if (!seed) { out.colors[role] = { seed: null, status: 'default', reason: null, drawn: fallback(role, value.name) }; continue; }
      const got = derive(role, seed, value.name);
      if (got.status === 'refused') { out.colors[role] = { seed, status: 'refused', reason: got.reason, drawn: fallback(role, value.name) }; continue; }
      for (const scheme of SCHEMES) Object.assign(out[scheme], got.tokens[scheme]);
      out.colors[role] = { seed, status: got.status, reason: null, drawn: { dark: got.drawn.dark, light: got.drawn.light } };
    }
    return out;
  }

  // ---- Painting (browser only) --------------------------------------------------------
  let applied = normalize(DEFAULT);
  let listening = false;
  const lightQuery = () => (typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: light)') : null);
  function scheme() {
    if (applied.appearance !== 'system') return applied.appearance;
    const query = lightQuery();
    return query && query.matches ? 'light' : 'dark';
  }
  function current() { return { name: applied.name, appearance: applied.appearance, colors: { ...applied.colors } }; }
  // Storage is looked up on every call: a host page (the website demo) may swap it after load.
  function store() { try { return typeof localStorage !== 'undefined' ? localStorage : null; } catch (e) { return null; } }
  function paint() {
    if (typeof document === 'undefined' || !document.documentElement) return;
    const html = document.documentElement;
    const resolved = resolve(applied);
    const now = scheme();
    html.setAttribute('data-theme', resolved.name);
    html.setAttribute('data-scheme', now);
    html.style.colorScheme = now;
    for (const [token, hex] of Object.entries(resolved[now])) html.style.setProperty('--' + token, hex);
    try { if (typeof CustomEvent === 'function') window.dispatchEvent(new CustomEvent('nagi-theme', { detail: { name: resolved.name, scheme: now } })); } catch (e) { /* painting never fails on a listener */ }
  }
  function apply(setting, opts) {
    applied = normalize(setting);
    if (!listening) {
      const query = lightQuery();
      if (query) {
        const follow = () => { if (applied.appearance === 'system') paint(); };
        if (typeof query.addEventListener === 'function') query.addEventListener('change', follow);
        else if (typeof query.addListener === 'function') query.addListener(follow);
        listening = true;
      }
    }
    paint();
    if (!opts || opts.persist !== false) {
      const storage = store();
      try { if (storage) storage.setItem(CACHE_KEY, JSON.stringify(applied)); } catch (e) { /* a private window keeps the theme for this view only */ }
    }
    return current();
  }

  // First frame: the cached setting, or the default.
  if (typeof document !== 'undefined' && document.documentElement) {
    let cached = null;
    const storage = store();
    try { cached = storage ? JSON.parse(storage.getItem(CACHE_KEY)) : null; } catch (e) { cached = null; }
    apply(cached, { persist: false });
  }

  // For tests and the lead's measurements: the raw derivation, with each mark's distance to rose and yellow.
  const inspect = (role, seed, name) => derive(role, String(seed).toLowerCase(), own(THEMES, name) ? name : DEFAULT.name);

  return { THEMES, ROLES, DEFAULT, normalize, check, resolve, apply, current, scheme, contrast, distance, mix, inspect, SIGNAL_DISTANCE };
});
