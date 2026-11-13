// Copies the real glance panel from web/ into site/panel/ so the site's hero runs the
// shipped renderer, not a redraw. Only mechanical changes are made:
//   - absolute asset URLs become relative, so the site works under any base path;
//   - the page loads demo.js (a fictional fixture and a fetch shim) instead of nagi-auth.js.
// Run from the repository root:  node site/scripts/sync-panel.mjs [--check]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const web = path.join(root, 'web');
const out = path.join(root, 'site', 'panel');
const check = process.argv.includes('--check');

const relative = (text) => text
  .replaceAll('url("/fonts/', 'url("fonts/')
  .replace(/(href|src)="\/(?!\/)/g, '$1="');

const FILES = [
  ['glance-v2.css', 'nagi-glance.css', relative],
  ['glance-sheet.css', 'nagi-sheet.css', relative],
  ['glance-model.js', 'nagi-model.js'],
  ['glance-motion.js', 'nagi-motion.js'],
  ['project-icons.js', 'nagi-icons.js'],
  ['glance-v2.js', 'nagi-glance.js'],
  ['fonts/inter-opsz.woff2', 'fonts/inter-opsz.woff2'],
  ['fonts/inter-opsz-LICENSE.txt', 'fonts/inter-opsz-LICENSE.txt'],
  ['fonts/nagi-glyph-serif.woff2', 'fonts/nagi-glyph-serif.woff2'],
  ['fonts/nagi-glyph-OFL.txt', 'fonts/nagi-glyph-OFL.txt'],
  ['glance-v2.html', 'index.html', (html) => relative(html)
    .replace('<title>Nagi · Agents and limits</title>', '<title>Nagi panel · demo data</title>\n<meta name="robots" content="noindex">')
    .replace('<link rel="icon" href="favicon.svg">', '<link rel="icon" href="../favicon.svg">')
    .replace('<script src="nagi-auth.js" defer></script>', '<script src="demo.js"></script>')],
];

let stale = [];
for (const [from, to, transform] of FILES) {
  const src = path.join(web, from);
  const dest = path.join(out, to);
  let body = fs.readFileSync(src);
  if (transform) body = Buffer.from(transform(body.toString('utf8')), 'utf8');
  if (check) {
    if (!fs.existsSync(dest) || !fs.readFileSync(dest).equals(body)) stale.push(to);
    continue;
  }
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, body);
}
if (check && stale.length) {
  console.error('site/panel is out of date with web/: ' + stale.join(', ') + '\nRun: node site/scripts/sync-panel.mjs');
  process.exit(1);
}
if (!check) console.log('site/panel synced from web/ (' + FILES.length + ' files)');
