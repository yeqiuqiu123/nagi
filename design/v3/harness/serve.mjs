// Design harness for the v3 panel: serves web/ exactly as the reader routes it, but answers
// the panel's API from fixtures.js (fictional data, no reader, no T3, no network).
//   node design/v3/harness/serve.mjs [port]      then open http://127.0.0.1:<port>/glance?scene=calm
// Scenes are listed at the top of fixtures.js. Nothing here ships.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, '..', '..', '..', 'web');
const FILES = { '/glance': 'glance-v2.html', '/nagi-glance.js': 'glance-v2.js', '/nagi-model.js': 'glance-model.js', '/nagi-motion.js': 'glance-motion.js',
  '/nagi-icons.js': 'project-icons.js', '/nagi-setup.js': 'glance-setup.js', '/nagi-sheet.css': 'glance-sheet.css', '/nagi-glance.css': 'glance-v2.css',
  '/favicon.svg': 'favicon.svg', '/fonts/inter-opsz.woff2': 'fonts/inter-opsz.woff2', '/fonts/nagi-glyph-serif.woff2': 'fonts/nagi-glyph-serif.woff2' };
const TYPES = { '.woff2': 'font/woff2', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8', '.svg': 'image/svg+xml' };
// The reader's own policy: no inline script or style may run in the panel.
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";

const port = Number(process.argv[2]) || 47990;
http.createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  const send = (status, body, type) => { response.writeHead(status, { 'Content-Type': type, 'Content-Security-Policy': CSP, 'Cache-Control': 'no-store' }); response.end(body); };
  if (url.pathname === '/nagi-auth.js') return send(200, fs.readFileSync(path.join(here, 'fixtures.js')), TYPES['.js']);
  const file = FILES[url.pathname];
  if (!file) return send(404, 'not found', 'text/plain');
  send(200, fs.readFileSync(path.join(web, file)), TYPES[path.extname(file)]);
}).listen(port, '127.0.0.1', () => console.log('http://127.0.0.1:' + port + '/glance?scene=calm'));
