// Captures every panel state from the design harness at panel size, night and day.
//   node design/v3/harness/serve.mjs 47990 &
//   node design/v3/harness/shots.mjs http://127.0.0.1:47990 design/v3/shots [name,name…]
// Needs Playwright with its WebKit build (the same engine family as WebKitGTK and WKWebView):
//   PLAYWRIGHT_MODULES=<dir containing playwright>  WEBKIT_BIN=<pw_run.sh>
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const modules = process.env.PLAYWRIGHT_MODULES || path.join(os.homedir(), '.local/state/tool-maintenance/staging/playwright_cli/0.1.24/runtime/node_modules');
const { webkit } = createRequire(modules + '/')('playwright');
const executablePath = process.env.WEBKIT_BIN || path.join(os.homedir(), '.cache/ms-playwright/webkit-2370/pw_run.sh');
const [,, origin, outDir, only] = process.argv;

const click = (selector) => async (page) => { await page.click(selector); };
const steps = (...fns) => async (page) => { for (const fn of fns) { await fn(page); await page.waitForTimeout(250); } };
const key = (name) => async (page) => { await page.keyboard.press(name); };
const button = (text) => async (page) => { await page.locator('.setup-sheet button', { hasText: new RegExp('^' + text + '$') }).first().click(); };
const closeSetup = key('Escape');

// name → [scene, action after the first draw, fixed height or null to follow the panel]
const SHOTS = {
  'calm': ['calm'], 'asks-you': ['asks'], 'stuck': ['stuck'], 'asks-and-stuck-low-limits': ['both'], 'limits-low-and-empty': ['low'],
  'limits-could-not-check': ['limitsfail'], 'limits-dated': ['datedlimits'], 'cannot-reach-source': ['unreachable'], 'never-read': ['never'],
  'not-set-up': ['notsetup'], 'checking': ['checking'], 'nothing-running': ['quiet'], 'nothing-ran': ['nothing'],
  'first-run-empty': ['first', closeSetup], 'overflow': ['overflow'], 'several-sources': ['multi'], 'six-dials': ['sixdials'], 'many-windows': ['manywindows'], 'friends-evening': ['friend'],
  'dial-detail': ['low', click('#dials .acct:nth-child(2)')], 'dial-detail-failed': ['limitsfail', click('#dials .acct:nth-child(2)')],
  'ended-open': ['calm', click('.ended-btn')], 'source-detail': ['multi', click('button.src.waiting')], 'no-sessions-yet': ['partial'],
  'settings': ['calm', click('#gear'), 690],
  'setup-1-apps': ['first', null, 690],
  'setup-2-where': ['first', steps(button('Continue')), 690],
  'setup-3-connect': ['first', steps(click('#app-claude'), click('#app-codex'), click('#app-cursor'), button('Continue'), click('#where-peerpeer1'), button('Continue')), 690],
  'setup-3-consent': ['first', steps(click('#app-t3'), click('#app-codex'), click('#app-cursor'), button('Continue'), button('Continue')), 690],
  'setup-4-done': ['first', steps(click('#app-claude'), click('#app-codex'), click('#app-cursor'), button('Continue'), click('#where-local'), button('Continue'), button('Connect'), button('Continue')), 690],
  'sources': ['multi', steps(click('#gear'), click('#manage-sources')), 690],
  'sources-disconnect': ['multi', steps(click('#gear'), click('#manage-sources'), async (page) => { await page.locator('.setup-sheet button', { hasText: 'Disconnect' }).first().click(); }), 690],
  'keyboard-focus': ['asks', steps(key('Tab'), key('Tab'), key('Tab'))],
  'mac-density': ['both&mac=1'],
};

const names = only ? only.split(',') : Object.keys(SHOTS);
fs.mkdirSync(outDir, { recursive: true });
const browser = await webkit.launch({ executablePath });
for (const scheme of ['dark', 'light']) {
  for (const name of names) {
    const [scene, action, fixed] = SHOTS[name];
    const context = await browser.newContext({ viewport: { width: 400, height: 690 }, deviceScaleFactor: 2, colorScheme: scheme, reducedMotion: 'reduce' });
    const page = await context.newPage();
    // Playwright's own screenshot helper adds a style element, which the panel's policy refuses.
    page.on('console', (m) => { if (m.type() === 'error' && !/Refused to apply a stylesheet/.test(m.text())) console.log('  console:', name, m.text()); });
    page.on('pageerror', (e) => console.log('  error:', name, e.message));
    await page.goto(origin + '/glance?scene=' + scene, { waitUntil: 'load' });
    await page.waitForFunction(() => document.getElementById('panel').dataset.state !== 'loading', null, { timeout: 8000 }).catch(() => console.log('  never drew:', name));
    await page.waitForTimeout(350);
    if (action) { await action(page); await page.waitForTimeout(350); }
    // The Mac shell shows the same page at 0.85 (pageZoom). Here that is a CSS zoom, so the
    // window is sized from what the zoomed content measures.
    const mac = scene.includes('mac=1');
    const height = fixed || await page.evaluate((zoomed) => (zoomed
      ? Math.ceil(['pinned', 'scroll-inner', 'rail'].reduce((n, id) => n + document.getElementById(id).getBoundingClientRect().height, 0)) + 2
      : window.__nagi.heights[window.__nagi.heights.length - 1] || 690), mac);
    // Under a CSS zoom the page's 100vh is zoomed too, so the window is made taller by the
    // same factor and the capture is clipped back to the panel.
    await page.setViewportSize({ width: mac ? 340 : 400, height: mac ? Math.ceil(height / 0.85) : height });
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(outDir, name + '-' + (scheme === 'dark' ? 'night' : 'day') + '.png'), ...(mac ? { clip: { x: 0, y: 0, width: 340, height } } : {}) });
    console.log(name, scheme, height);
    await context.close();
  }
}
await browser.close();
