# Nagi website

A static page with no build step and no server. `index.html` is the page; `panel/` is the real glance panel, copied from `web/`, running on invented demo data.

## Work on it

```sh
python3 -m http.server 8765 --directory site   # then open http://127.0.0.1:8765/
node --test site/tests/                         # checks the panel copy and the demo data
```

## The panel is the real one

`site/panel/` is generated. Don't edit it by hand. When the panel changes in `web/`, run:

```sh
node site/scripts/sync-panel.mjs
```

The sync copies the panel's HTML, CSS, JavaScript and fonts. It changes only two things: absolute URLs become relative, so the site works under any path, and `demo.js` replaces the login script. `site/tests/site.test.mjs` fails if the copy drifts from `web/`.

`panel/demo.js` is the only hand-written file in `panel/`. Its job:
- **Answers the panel's API** with a made-up fixture: the projects Tidepool, Kestrel API and Lantern Docs, and the accounts Codex 1, Codex 2 and Claude 1.
- **Runs a virtual clock,** so a few minutes of agent work fit in a few seconds.
- **Keeps the panel's one remembered value in memory,** so the site stores nothing in the browser.

The page's tray legend and its "It only says what it knows" lines are computed at runtime by the panel's own model from that same fixture. Never type them by hand.

**Never put real agent titles, project names, hostnames, addresses or account names in the fixture.**

## Publish (ask the owner first)

Nothing here deploys by itself. Either host works with no configuration beyond pointing it at `site/`:

- **GitHub Pages:**
  1. In Settings → Pages, choose "GitHub Actions".
  2. Add a workflow that uploads `site/` with `actions/upload-pages-artifact` and publishes it with `actions/deploy-pages`.

  The page uses only relative URLs, so `https://<user>.github.io/nagi/` works as is.
- **Vercel (in use):** the project is `nagi` and the domain is `usenagi.xyz`.
  - Deploy from `site/` with `vercel deploy --prod`. There's no build step.
  - `vercel.json` sets the security headers: a strict CSP (self only), no referrer, nosniff.
  - `.vercelignore` keeps the tests, scripts and any `.env*` files out of the upload.

The site makes no third-party requests and sets no cookies. Keep it that way: no analytics, no font CDNs, no embeds.
