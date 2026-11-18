// Keyboard, focus and motion checks for the v3 panel, in Playwright WebKit.
//   node design/v3/harness/serve.mjs 47990 &
//   node design/v3/harness/check.mjs http://127.0.0.1:47990
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';

const modules = process.env.PLAYWRIGHT_MODULES || path.join(os.homedir(), '.local/state/tool-maintenance/staging/playwright_cli/0.1.24/runtime/node_modules');
const { webkit } = createRequire(modules + '/')('playwright');
const executablePath = process.env.WEBKIT_BIN || path.join(os.homedir(), '.cache/ms-playwright/webkit-2370/pw_run.sh');
const origin = process.argv[2];
const browser = await webkit.launch({ executablePath });

async function open(scene, options) {
  const context = await browser.newContext({ viewport: { width: 400, height: 690 }, colorScheme: 'dark', reducedMotion: 'no-preference', ...(options || {}) });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(origin + '/glance?scene=' + scene, { waitUntil: 'load' });
  await page.waitForFunction(() => document.getElementById('panel').dataset.state !== 'loading');
  await page.waitForTimeout(250);
  return { page, context, errors };
}
const focused = (page) => page.evaluate(() => { const el = document.activeElement; return el && el !== document.body ? (el.dataset.key || el.id || el.tagName) : null; });
const results = [];
const check = async (name, fn) => { try { await fn(); results.push('ok    ' + name); } catch (error) { results.push('FAIL  ' + name + ': ' + error.message.split('\n')[0]); process.exitCode = 1; } };

await check('Tab reaches every control in reading order, each with a visible focus ring', async () => {
  const { page, context, errors } = await open('multi');
  const order = [];
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press('Tab');
    const key = await focused(page);
    if (!key || order.includes(key)) break;
    order.push(key);
    const ring = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2; });
    assert.ok(ring, 'no focus ring on ' + key);
  }
  const kind = (k) => k.split(':')[0];
  const kinds = order.map(kind).filter((k, i, all) => k !== all[i - 1]);
  assert.deepEqual(kinds, ['word', 'gear', 'dial', 'row', 'ended', 'src'], order.join(' '));
  assert.deepEqual(errors, []);
  await context.close();
});

await check('Enter opens a dial\'s exact lines; Escape closes them, then the panel', async () => {
  const { page, context } = await open('low');
  await page.focus('#dials .acct');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.getElementById('dial-detail').hidden), false);
  assert.match(await page.evaluate(() => document.getElementById('dial-detail').textContent), /empty.*until/);
  assert.equal(await page.evaluate(() => document.activeElement.getAttribute('aria-expanded')), 'true');
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(() => document.getElementById('dial-detail').hidden), true);
  assert.equal(await page.evaluate(() => window.__nagi.closed), false);
  assert.match(await focused(page), /^dial:/); // focus stays where it was
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(() => window.__nagi.closed), true);
  await context.close();
});

await check('The header\'s "asks you" brings its row into view and focuses it', async () => {
  const { page, context } = await open('asks');
  await page.click('.flag.asks');
  assert.equal(await page.evaluate(() => document.activeElement.classList.contains('is-asks')), true);
  await context.close();
});

await check('Ended expands in place with the keyboard and lists only failed and stopped threads', async () => {
  const { page, context } = await open('calm');
  await page.focus('.ended-btn');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.querySelector('.ended-btn').getAttribute('aria-expanded')), 'true');
  const problems = await page.evaluate(() => [...document.querySelectorAll('.problem .aside')].map((el) => el.textContent.split(' ')[0]));
  assert.ok(problems.length > 0 && problems.every((word) => word === 'failed' || word === 'stopped'), problems.join());
  await context.close();
});

await check('Settings opens from the keyboard, traps Tab, and Escape returns focus to the gear', async () => {
  const { page, context } = await open('calm');
  await page.focus('#gear');
  await page.keyboard.press('Enter');
  assert.equal(await focused(page), 'stuck-minutes');
  for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); assert.ok(await page.evaluate(() => !!document.activeElement.closest('#sheet')), 'focus left the sheet'); }
  await page.keyboard.press('Escape');
  assert.equal(await focused(page), 'gear');
  await context.close();
});

await check('No control on the glance can change an agent app: links open, buttons only reveal', async () => {
  const { page, context } = await open('multi');
  const found = await page.evaluate(() => [...document.querySelectorAll('#pinned button, #scroll button, #rail button, #scroll a')].map((el) => el.dataset.key ? el.dataset.key.split(':')[0] : el.id));
  assert.deepEqual([...new Set(found)].sort(), ['dial', 'ended', 'gear', 'problem', 'row', 'src', 'word']);
  await context.close();
});

await check('An open after a limit moved sweeps its arc; reduced motion draws it at once', async () => {
  const moving = await open('calm&since=45');
  assert.ok(await moving.page.evaluate(() => document.getAnimations().length) > 0, 'no sweep');
  await moving.context.close();
  const still = await open('calm&since=45', { reducedMotion: 'reduce' });
  assert.equal(await still.page.evaluate(() => document.getAnimations().length), 0);
  await still.context.close();
  const first = await open('calm');
  assert.equal(await first.page.evaluate(() => document.getAnimations().length), 0, 'a first open must not animate');
  await first.context.close();
});

await check('The Mac density (0.85) keeps every dial on one row and nothing clipped', async () => {
  const { page, context } = await open('both&mac=1');
  const rows = await page.evaluate(() => new Set([...document.querySelectorAll('#dials .acct')].map((el) => Math.round(el.getBoundingClientRect().top))).size);
  assert.equal(rows, 1);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true);
  await context.close();
});

await browser.close();
console.log(results.join('\n'));
