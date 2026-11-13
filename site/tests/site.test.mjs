// node --test site/tests/  — static checks for the website.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(site, '..');

test('site/panel is the shipped panel, synced from web/', () => {
  execFileSync(process.execPath, [path.join(site, 'scripts', 'sync-panel.mjs'), '--check'], { cwd: root, stdio: 'pipe' });
});

test('the panel page loads the demo shim and no auth or live API', () => {
  const html = fs.readFileSync(path.join(site, 'panel', 'index.html'), 'utf8');
  assert.match(html, /<script src="demo.js"><\/script>/);
  assert.doesNotMatch(html, /nagi-auth/);
  assert.doesNotMatch(html, /(href|src)="\//, 'no root-absolute URLs (the site may live under a sub-path)');
});

test('the demo fixture stays fictional', () => {
  const demo = fs.readFileSync(path.join(site, 'panel', 'demo.js'), 'utf8');
  // Only the invented projects and accounts appear, and no address or host name of any kind.
  const projects = new Set([...demo.matchAll(/title: '([^']+)'/g)].map((m) => m[1]));
  assert.deepEqual([...projects].sort(), ['Kestrel API', 'Lantern Docs', 'Tidepool']);
  const accounts = [...demo.matchAll(/account\('\w+', '([^']+)'/g)].map((m) => m[1]);
  assert.ok(accounts.length >= 3);
  for (const a of accounts) assert.match(a, /^(Codex|Claude) \d$/, a);
  for (const m of demo.matchAll(/label: '([^']+)'/g)) assert.equal(m[1], 'This computer');
  assert.doesNotMatch(demo, /\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/, 'no IP addresses');
  assert.doesNotMatch(demo, /ts\.net|\.local\b|@[a-z0-9-]+\.[a-z]/i, 'no host names or emails');
});

test('the page loads nothing from another site and stores nothing', () => {
  const html = fs.readFileSync(path.join(site, 'index.html'), 'utf8');
  // Only links (<a href>) may point elsewhere; every loaded resource is local.
  for (const m of html.matchAll(/<(script|link|img|source|iframe)\b[^>]*?\b(src|href|srcset|data-src)="([^"]+)"/g)) {
    assert.doesNotMatch(m[3], /^(https?:)?\/\//, `${m[1]} loads ${m[3]}`);
  }
  assert.doesNotMatch(html, /url\((["']?)(https?:)?\/\//, 'no remote CSS urls');
  for (const file of ['js/site.js', 'js/panel-embed.js']) {
    const js = fs.readFileSync(path.join(site, file), 'utf8');
    assert.doesNotMatch(js, /localStorage|sessionStorage|indexedDB|document\.cookie/, file);
  }
});

test('sources match the catalog on main: available ones named, the rest coming soon', () => {
  const html = fs.readFileSync(path.join(site, 'index.html'), 'utf8');
  const root = path.join(site, '..');
  const catalog = fs.readFileSync(path.join(root, 'sources_service.py'), 'utf8');
  const names = [...catalog.slice(catalog.indexOf('CATALOG = ('), catalog.indexOf('HARNESS_IDS')).matchAll(/\('(\w+)', '([^']+)', '\w+'\)/g)].map((m) => [m[1], m[2]]);
  const adapters = fs.readFileSync(path.join(root, 'source_adapters.py'), 'utf8');
  const available = new Set(['t3', ...[...adapters.matchAll(/ADAPTERS\['(\w+)'\]/g)].map((m) => m[1])]);
  assert.ok(names.length >= 10 && available.size >= 4);
  const soon = html.match(/Coming soon: ([^.]+)\./)[1];
  for (const [id, name] of names) {
    if (available.has(id)) { assert.ok(html.includes(name), name + ' is named'); assert.ok(!soon.includes(name), name + ' is not coming soon'); }
    else assert.ok(soon.includes(name), name + ' is coming soon');
  }
  assert.match(html, /<b>Cursor<\/b> <span>in beta<\/span>/);
  assert.match(html, /MIT licence/);
  assert.ok(fs.existsSync(path.join(root, 'LICENSE')), 'the repo carries the licence the page names');
});
