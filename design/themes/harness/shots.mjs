// Captures the themes, a custom palette and the Appearance sheet at panel size, night and day.
//   node design/v3/harness/serve.mjs 47991 &
//   node design/themes/harness/shots.mjs http://127.0.0.1:47991 design/themes/shots [name,name…]
// A forced appearance is shot with the browser set to the OPPOSITE scheme, to prove it holds:
// `graphite-night.png` is appearance=dark in a light browser. `system` shots follow the browser.
// Needs Playwright with its WebKit build (the same engine family as WebKitGTK and WKWebView):
//   PLAYWRIGHT_MODULES=<dir containing playwright>  WEBKIT_BIN=<pw_run.sh>
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const modules = process.env.PLAYWRIGHT_MODULES || path.join(os.homedir(), '.local/state/tool-maintenance/staging/playwright_cli/0.1.24/runtime/node_modules');
const { webkit } = createRequire(modules + '/')('playwright');
const executablePath = process.env.WEBKIT_BIN || path.join(os.homedir(), '.cache/ms-playwright/webkit-2370/pw_run.sh');
const [,, origin, outDir = 'design/themes/shots', only] = process.argv;

const click = (selector) => async (page) => { await page.click(selector); };
const steps = (...fns) => async (page) => { for (const fn of fns) { await fn(page); await page.waitForTimeout(250); } };
// Typing a hex value previews it at once, as the owner would see it while typing.
const typeHex = (role, value) => async (page) => { await page.fill('#ap-' + role + '-hex', value); };
const openAppearance = steps(click('#gear'), click('#change-appearance'));

// name → { scene, theme, colors, ci, load, appearance: 'forced' (default) | 'system', action, fixed, same }
//   theme, colors, ci and load go to the fixture's query string; fixed is a window height, or the
//   panel's own height when absent; `same` names a shot this one must equal pixel for pixel.
const SHOTS = {
  // The three themes on the busiest glance.
  violet: { scene: 'both', theme: 'violet' },
  graphite: { scene: 'both', theme: 'graphite' },
  tide: { scene: 'both', theme: 'tide' },
  // One custom palette: an orange accent, Claude violet, Codex teal, T3 blue; Gemini as the theme draws it.
  custom: { scene: 'both', theme: 'graphite', colors: 'accent:ff8800,claude:9a7bf0,codex:2bb3c0,t3:409cff' },
  // System follows the browser.
  'system-follow': { scene: 'both', theme: 'tide', appearance: 'system' },
  // Settings, with its Appearance row.
  settings: { scene: 'calm', theme: 'violet', action: click('#gear'), fixed: 690 },
  // The Appearance sheet on each theme.
  'appearance-violet': { scene: 'calm', theme: 'violet', action: openAppearance, fixed: 690 },
  'appearance-graphite': { scene: 'calm', theme: 'graphite', action: openAppearance, fixed: 690 },
  'appearance-tide': { scene: 'calm', theme: 'tide', action: openAppearance, fixed: 690 },
  // Claude's row open: a dark brown is lightened for the night; a yellow is refused.
  'appearance-adjusted': { scene: 'calm', theme: 'violet', action: steps(openAppearance, click('#ap-claude-head'), typeHex('claude', '#7a2e1a')), fixed: 690 },
  'appearance-refused': { scene: 'calm', theme: 'violet', action: steps(openAppearance, click('#ap-claude-head'), typeHex('claude', '#e8c547')), fixed: 690 },
  // Checks, deployments, pull requests, ended results and load (Part 2).
  'ci-mixed': { scene: 'both', ci: 'mixed', load: 'gpu' },
  'ci-mixed-graphite': { scene: 'both', theme: 'graphite', ci: 'mixed', load: 'gpu' },
  'ci-mixed-tide': { scene: 'both', theme: 'tide', ci: 'mixed', load: 'gpu' },
  'ci-green': { scene: 'calm', ci: 'green', load: 'calm' },
  'ci-down': { scene: 'both', ci: 'down', load: 'calm' },
  'ci-dated': { scene: 'both', ci: 'dated', load: 'calm' },
  'ci-signedout': { scene: 'both', ci: 'signedout' },
  'ci-rowdown': { scene: 'both', ci: 'rowdown', load: 'calm' },
  'ci-partial': { scene: 'both', ci: 'partial', load: 'calm' },
  'ci-ended-open': { scene: 'calm', ci: 'mixed', load: 'gpu', action: click('.ended-btn'), fixed: 690 },
  'load-detail': { scene: 'calm', ci: 'mixed', load: 'hot', action: click('[data-key="gauge:load"]') },
  'load-partial': { scene: 'calm', load: 'partial', action: click('[data-key="gauge:load"]') },
  'load-down': { scene: 'calm', load: 'down', action: click('[data-key="gauge:load"]') },
  // GitHub off draws nothing: the same pixels as the plain Violet shot of the same scene.
  'ci-off': { scene: 'both', ci: 'off', same: 'violet' },
  // The fullest header: 2 PRs, asks you, a failed ring, a deployment in flight and a hot machine.
  'ci-busy-header': { scene: 'both', ci: 'mixed', load: 'hot' },
  // Seven PRs waiting (four shown and `+ 3 more`) and fifteen results.
  'ci-many': { scene: 'calm', ci: 'many', load: 'calm' },
  // Settings → Sources: the GitHub switch, off, on and with gh signed out.
  'sources-github-off': { scene: 'multi', theme: 'violet', ci: 'off', action: steps(click('#gear'), click('#manage-sources')), fixed: 690 },
  'sources-github-on': { scene: 'multi', theme: 'violet', ci: 'mixed', action: steps(click('#gear'), click('#manage-sources')), fixed: 690 },
  'sources-github-signedout': { scene: 'multi', theme: 'violet', ci: 'signedout', action: steps(click('#gear'), click('#manage-sources')), fixed: 690 },
};

const names = only ? only.split(',') : Object.keys(SHOTS);
fs.mkdirSync(outDir, { recursive: true });
const browser = await webkit.launch({ executablePath });
for (const mode of ['dark', 'light']) {
  for (const name of names) {
    const shot = SHOTS[name];
    if (!shot) { console.log('  unknown shot:', name); continue; }
    const system = shot.appearance === 'system';
    const colorScheme = system ? mode : mode === 'dark' ? 'light' : 'dark';
    const query = new URLSearchParams({ scene: shot.scene, theme: shot.theme || 'violet', appearance: system ? 'system' : mode });
    if (shot.colors) query.set('colors', shot.colors);
    if (shot.ci) query.set('ci', shot.ci);
    if (shot.load) query.set('load', shot.load);
    const context = await browser.newContext({ viewport: { width: 400, height: 690 }, deviceScaleFactor: 2, colorScheme, reducedMotion: 'reduce' });
    const page = await context.newPage();
    // Playwright's own screenshot helper adds a style element, which the panel's policy refuses.
    page.on('console', (m) => { if (m.type() === 'error' && !/Refused to apply a stylesheet/.test(m.text())) console.log('  console:', name, m.text()); });
    page.on('pageerror', (e) => console.log('  error:', name, e.message));
    await page.goto(origin + '/glance?' + query.toString(), { waitUntil: 'load' });
    await page.waitForFunction(() => document.getElementById('panel').dataset.state !== 'loading', null, { timeout: 8000 }).catch(() => console.log('  never drew:', name));
    await page.waitForTimeout(350);
    if (shot.action) { await shot.action(page); await page.waitForTimeout(350); }
    const drawn = await page.evaluate(() => document.documentElement.dataset.scheme || null);
    if (drawn && drawn !== mode) console.log('  wrong appearance:', name, mode, 'drew', drawn);
    const height = shot.fixed || await page.evaluate(() => window.__nagi.heights[window.__nagi.heights.length - 1] || 690);
    await page.setViewportSize({ width: 400, height });
    await page.waitForTimeout(250);
    const file = path.join(outDir, name + '-' + (mode === 'dark' ? 'night' : 'day') + '.png');
    await page.screenshot({ path: file });
    console.log(name, mode, 'browser ' + colorScheme, height);
    if (shot.same) {
      const other = path.join(outDir, shot.same + '-' + (mode === 'dark' ? 'night' : 'day') + '.png');
      if (!fs.existsSync(other)) console.log('  cannot compare:', name, 'needs', other);
      else if (Buffer.compare(fs.readFileSync(file), fs.readFileSync(other)) === 0) console.log('  identical to', shot.same);
      else { console.log('  DIFFERS from', shot.same); process.exitCode = 1; }
    }
    await context.close();
  }
}
await browser.close();
