// Proves what this branch leaves untouched: with the Violet theme and GitHub off, the glance
// is the panel on `main`, pixel for pixel. It serves main's own web/ (read from git, never
// checked out) beside this branch's, on the same fixture and a frozen clock, and compares.
//   node design/themes/harness/parity.mjs [base ref, default main]
// Two claims, each scene, night and day:
//   1. No machine route (a reader without it), GitHub off: no pixel differs from main.
//   2. The machine route answers, GitHub off: the load ring appears, and every pixel that
//      differs is on the header's top line. Nothing below it moves.
// Needs Playwright with its WebKit build, as shots.mjs does.
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const modules = process.env.PLAYWRIGHT_MODULES || path.join(os.homedir(), '.local/state/tool-maintenance/staging/playwright_cli/0.1.24/runtime/node_modules');
const { webkit } = createRequire(modules + '/')('playwright');
const executablePath = process.env.WEBKIT_BIN || path.join(os.homedir(), '.cache/ms-playwright/webkit-2370/pw_run.sh');
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..', '..');
const base = process.argv[2] || 'main';

const TYPES = { '.woff2': 'font/woff2', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8', '.svg': 'image/svg+xml' };
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";
const ROUTES = { '/glance': 'glance-v2.html', '/nagi-glance.js': 'glance-v2.js', '/nagi-model.js': 'glance-model.js', '/nagi-motion.js': 'glance-motion.js',
  '/nagi-icons.js': 'project-icons.js', '/nagi-setup.js': 'glance-setup.js', '/nagi-sheet.css': 'glance-sheet.css', '/nagi-glance.css': 'glance-v2.css',
  '/nagi-theme.js': 'glance-theme.js', '/nagi-appearance.js': 'glance-appearance.js', '/nagi-ci.js': 'glance-ci.js',
  '/favicon.svg': 'favicon.svg', '/fonts/inter-opsz.woff2': 'fonts/inter-opsz.woff2', '/fonts/nagi-glyph-serif.woff2': 'fonts/nagi-glyph-serif.woff2' };
// Both panels answer from THIS branch's fixture: the data is the same, only the panel differs.
const fixture = fs.readFileSync(path.join(root, 'design', 'v3', 'harness', 'fixtures.js'));

function serve(read) {
  return new Promise((resolve) => {
    const server = http.createServer((request, response) => {
      const url = new URL(request.url, 'http://127.0.0.1');
      const send = (status, body, type) => { response.writeHead(status, { 'Content-Type': type, 'Content-Security-Policy': CSP, 'Cache-Control': 'no-store' }); response.end(body); };
      if (url.pathname === '/nagi-auth.js') return send(200, fixture, TYPES['.js']);
      const file = ROUTES[url.pathname];
      const body = file ? read(file) : null;
      if (!body) return send(404, 'not found', 'text/plain');
      send(200, body, TYPES[path.extname(file)]);
    }).listen(0, '127.0.0.1', () => resolve({ server, origin: 'http://127.0.0.1:' + server.address().port }));
  });
}
const fromGit = (file) => { try { return execFileSync('git', ['-C', root, 'show', base + ':web/' + file], { maxBuffer: 32 << 20, stdio: ['ignore', 'pipe', 'ignore'] }); } catch { return null; } };
const fromTree = (file) => { try { return fs.readFileSync(path.join(root, 'web', file)); } catch { return null; } };

const FROZEN = new Date('2026-11-19T08:00:00+07:00');
async function shoot(browser, origin, query, scheme) {
  const context = await browser.newContext({ viewport: { width: 400, height: 690 }, deviceScaleFactor: 2, colorScheme: scheme, reducedMotion: 'reduce', timezoneId: 'Asia/Ho_Chi_Minh' });
  const page = await context.newPage();
  await page.clock.setFixedTime(FROZEN);
  await page.goto(origin + '/glance?' + query, { waitUntil: 'load' });
  await page.waitForFunction(() => document.getElementById('panel').dataset.state !== 'loading', null, { timeout: 8000 });
  await page.waitForTimeout(900); // past the feeds' grace, so a late load ring is in the picture
  const height = await page.evaluate(() => window.__nagi.heights[window.__nagi.heights.length - 1] || 690);
  await page.setViewportSize({ width: 400, height });
  await page.waitForTimeout(250);
  // The header's top line, in device pixels: the one place the load ring may change.
  const top = await page.evaluate(() => { const r = document.querySelector('.top').getBoundingClientRect(); return { y0: Math.floor(r.top * 2), y1: Math.ceil(r.bottom * 2) }; });
  const png = await page.screenshot();
  await context.close();
  return { png, height, top };
}

// Decodes both pictures in a blank page and reports how many pixels differ and where.
async function diff(browser, a, b) {
  const page = await (await browser.newContext()).newPage();
  const result = await page.evaluate(async ([x, y]) => {
    const load = async (b64) => { const image = new Image(); image.src = 'data:image/png;base64,' + b64; await image.decode(); const c = document.createElement('canvas'); c.width = image.width; c.height = image.height; const g = c.getContext('2d'); g.drawImage(image, 0, 0); return g.getImageData(0, 0, c.width, c.height); };
    const p = await load(x); const q = await load(y);
    if (p.width !== q.width || p.height !== q.height) return { size: [p.width, p.height, q.width, q.height] };
    let n = 0; let y0 = Infinity; let y1 = -1; let x0 = Infinity; let x1 = -1;
    for (let i = 0; i < p.data.length; i += 4) {
      if (p.data[i] === q.data[i] && p.data[i + 1] === q.data[i + 1] && p.data[i + 2] === q.data[i + 2] && p.data[i + 3] === q.data[i + 3]) continue;
      n++; const px = (i / 4) % p.width; const py = Math.floor(i / 4 / p.width);
      if (py < y0) y0 = py; if (py > y1) y1 = py; if (px < x0) x0 = px; if (px > x1) x1 = px;
    }
    return { n, y0, y1, x0, x1 };
  }, [a.toString('base64'), b.toString('base64')]);
  await page.context().close();
  return result;
}

const old = await serve(fromGit);
const now = await serve(fromTree);
const browser = await webkit.launch({ executablePath });
let failed = false;
const fail = (text) => { failed = true; console.log('  FAIL', text); };
for (const scheme of ['dark', 'light']) {
  for (const scene of ['both', 'calm', 'friend', 'multi']) {
    const name = scene + ' ' + (scheme === 'dark' ? 'night' : 'day');
    const before = await shoot(browser, old.origin, 'scene=' + scene, scheme);
    // 1. A reader without the machine route, GitHub off.
    const plain = await shoot(browser, now.origin, 'scene=' + scene + '&ci=off', scheme);
    const same = await diff(browser, before.png, plain.png);
    if (same.size) fail(name + ': size differs from ' + base + ' ' + same.size.join(' '));
    else if (same.n) fail(name + ': ' + same.n + ' pixels differ from ' + base + ' (x ' + same.x0 + '-' + same.x1 + ', y ' + same.y0 + '-' + same.y1 + ')');
    else console.log(name + ': identical to ' + base + ' with GitHub off and no machine route');
    // 2. The machine route answers: the load ring, and nothing else, is new.
    const ring = await shoot(browser, now.origin, 'scene=' + scene + '&ci=off&load=calm', scheme);
    const moved = await diff(browser, before.png, ring.png);
    if (moved.size) fail(name + ': the load ring changed the panel size ' + moved.size.join(' '));
    else if (!moved.n) fail(name + ': the load ring was not drawn');
    else if (moved.y0 < ring.top.y0 || moved.y1 >= ring.top.y1) fail(name + ': with the load ring, pixels differ outside the header line (y ' + moved.y0 + '-' + moved.y1 + ', header ' + ring.top.y0 + '-' + ring.top.y1 + ')');
    else console.log(name + ': with the load ring, ' + moved.n + ' pixels differ, all on the header line (y ' + moved.y0 + '-' + moved.y1 + ')');
  }
}
await browser.close();
old.server.close(); now.server.close();
if (failed) process.exit(1);
