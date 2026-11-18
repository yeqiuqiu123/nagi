// Measures the v3 readability floors in the running panel (design/v3/project-bar.md):
// every text element's size, weight and contrast against the surface actually behind it,
// and every meaningful stroke's width and contrast, in each state, night and day.
//   node design/v3/harness/serve.mjs 47990 &
//   node design/v3/harness/measure.mjs http://127.0.0.1:47990 > design/v3/measurements.md
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';

const modules = process.env.PLAYWRIGHT_MODULES || path.join(os.homedir(), '.local/state/tool-maintenance/staging/playwright_cli/0.1.24/runtime/node_modules');
const { webkit } = createRequire(modules + '/')('playwright');
const executablePath = process.env.WEBKIT_BIN || path.join(os.homedir(), '.cache/ms-playwright/webkit-2370/pw_run.sh');
const origin = process.argv[2];

// scene, then clicks that open the state to measure
const STATES = [['calm'], ['both'], ['low'], ['limitsfail'], ['datedlimits'], ['unreachable'], ['never'], ['notsetup'], ['quiet'], ['nothing'], ['partial'],
  ['overflow'], ['multi'], ['friend'], ['low', '#dials .acct:nth-child(2)'], ['calm', '.ended-btn'], ['multi', 'button.src.waiting'], ['calm', '#gear'],
  ['first'], ['multi', '#gear', '#manage-sources']];

// Roles: [name, selector, min px, min weight, min contrast]
const ROLES = [
  ['Mark', '.kanji', 20, 400, 12],
  // A headline that recedes on purpose: nothing running, not set up, or a dated count.
  ['Quiet headline', '.headline.calm, .headline.dim, .headline.dim .num', 15, 500, 7],
  ['Title', '.title, .headline, .dd-name, .choice-name, .field label, .field-label, .sheet h2, .flag.alert', 15, 500, 12],
  ['Dial numeral', '.val b', 15, 650, 7],
  ['State word', '.flag.asks, .flag.stuck, .note.asks, .note.stuck, .model', 13, 420, 7],
  ['Tertiary', '.prefix, .sep, .btn.default:disabled', 12, 400, 4.5],
  ['Chip', '.chip, .app-tile', 12, 700, 4.5],
  ['Percent sign', '.val small', 12, 500, 7],
  ['Secondary', '*', 13, 420, 7],
];

function inPage(roles) {
  const lum = ([r, g, b]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const x = lum(a); const y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const probe = document.createElement('canvas'); probe.width = probe.height = 1; const ctx = probe.getContext('2d', { willReadFrequently: true });
  const rgb = (css) => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = css; ctx.fillRect(0, 0, 1, 1); const d = ctx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  // The surface behind an element: the nearest ancestor that paints an opaque background.
  const surface = (el) => { for (let n = el; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c[3] > 0.99) return c; } return rgb(getComputedStyle(document.body).backgroundColor); };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && !el.closest('[hidden], [inert], .sr'); };
  const out = { text: [], strokes: [] };
  const seen = new Set();
  for (const el of document.querySelectorAll('#panel *')) {
    if (!visible(el) || el.closest('svg')) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const s = getComputedStyle(el);
    const role = roles.find(([, sel]) => el.matches(sel));
    const fg = rgb(s.color);
    const key = [role[0], s.fontSize, s.fontWeight, s.color, surface(el).join()].join('|');
    if (seen.has(key)) continue; seen.add(key);
    out.text.push({ role: role[0], size: parseFloat(s.fontSize), weight: Number(s.fontWeight), contrast: ratio(fg, surface(el)), sample: el.textContent.trim().slice(0, 24),
      ok: parseFloat(s.fontSize) >= role[2] - 0.01 && Number(s.fontWeight) >= role[3] && ratio(fg, surface(el)) >= role[4] });
  }
  // Meaningful strokes: arcs, ticks, dashed and empty rings, branches, nodes. The plain track is scaffold.
  for (const el of document.querySelectorAll('#panel .dial .arc, #panel .dial .tick, #panel .cell.failed .track, #panel .cell.empty .track, #panel .cell.absent .track, #panel .geo .branch, #panel .geo circle, #panel .geo .n-wedge, #panel .obar i')) {
    if (!visible(el.closest('svg') || el)) continue;
    const s = getComputedStyle(el);
    const isFill = (s.stroke === 'none' || !s.stroke) || el.matches('.obar i');
    const paint = el.matches('.obar i') ? (rgb(s.backgroundColor)[3] > 0.5 ? s.backgroundColor : s.borderTopColor) : isFill ? s.fill : s.stroke;
    const host = el.closest('.acct, .row, .problem, .ended-btn') || el.closest('#pinned, #scroll') || document.body;
    // A node or branch is drawn above its row: the row's own surface is what it sits on.
    let behind = surface(host);
    if (el.closest('.geo')) { const r = el.getBoundingClientRect(); const under = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2).find((n) => !n.closest('svg')); if (under) behind = surface(under); }
    const width = el.matches('.obar i') ? parseFloat(s.height) : isFill ? (el.getBBox ? Math.min(el.getBBox().width, el.getBBox().height) : 0) : parseFloat(s.strokeWidth);
    const name = (el.getAttribute('class') || el.tagName).split(' ').slice(0, 2).join('.');
    const key = [name, paint, behind.join(), width].join('|');
    if (seen.has(key)) continue; seen.add(key);
    out.strokes.push({ name, width, contrast: ratio(rgb(paint), behind), ok: width >= 2 - 0.01 && ratio(rgb(paint), behind) >= 3 });
  }
  return out;
}

const browser = await webkit.launch({ executablePath });
const worst = new Map(); const fails = [];
for (const scheme of ['dark', 'light']) {
  for (const [scene, ...clicks] of STATES) {
    const context = await browser.newContext({ viewport: { width: 400, height: 690 }, colorScheme: scheme, reducedMotion: 'reduce' });
    const page = await context.newPage();
    await page.goto(origin + '/glance?scene=' + scene, { waitUntil: 'load' });
    await page.waitForFunction(() => document.getElementById('panel').dataset.state !== 'loading');
    await page.waitForTimeout(300);
    for (const selector of clicks) { await page.click(selector); await page.waitForTimeout(300); }
    const result = await page.evaluate(inPage, ROLES);
    const state = scene + (clicks.length ? ' + ' + clicks.join(' ') : '');
    for (const t of result.text) {
      const k = (scheme === 'dark' ? 'Night' : 'Day') + '|' + t.role;
      const w = worst.get(k) || { size: 99, weight: 999, contrast: 99 };
      worst.set(k, { size: Math.min(w.size, t.size), weight: Math.min(w.weight, t.weight), contrast: Math.min(w.contrast, t.contrast) });
      if (!t.ok) fails.push(`${scheme} · ${state} · ${t.role} "${t.sample}": ${t.size}px / ${t.weight} / ${t.contrast.toFixed(2)}:1`);
    }
    for (const s of result.strokes) {
      const k = (scheme === 'dark' ? 'Night' : 'Day') + '|Stroke';
      const w = worst.get(k) || { size: 99, weight: 0, contrast: 99 };
      worst.set(k, { size: Math.min(w.size, s.width), weight: 0, contrast: Math.min(w.contrast, s.contrast) });
      if (!s.ok) fails.push(`${scheme} · ${state} · stroke ${s.name}: ${s.width}px / ${s.contrast.toFixed(2)}:1`);
    }
    await context.close();
  }
}
await browser.close();

const floor = Object.fromEntries(ROLES.map(([name, , px, weight, contrast]) => [name, { px, weight, contrast }]));
floor.Stroke = { px: 2, weight: 0, contrast: 3 };
console.log('# Nagi v3 measured floors\n');
console.log('Generated by `design/v3/harness/measure.mjs` in Playwright WebKit from ' + STATES.length + ' states, night and day. Each cell is the worst value found for that role; the floor is in brackets. Contrast is against the surface actually behind the element (panel, row hover is not included, rose and yellow washes, the detail well, sheets).\n');
console.log('| Theme | Role | Smallest size | Lightest weight | Lowest contrast |');
console.log('|---|---|---|---|---|');
for (const [k, w] of [...worst.entries()].sort()) {
  const [theme, role] = k.split('|'); const f = floor[role];
  console.log(`| ${theme} | ${role} | ${w.size} px (${f.px}) | ${role === 'Stroke' ? 'n/a' : w.weight + ' (' + f.weight + ')'} | ${w.contrast.toFixed(2)}:1 (${f.contrast}:1) |`);
}
console.log('\n## Below a floor\n');
console.log(fails.length ? fails.map((f) => '- ' + f).join('\n') : 'None.');
process.exitCode = fails.length ? 1 : 0;
