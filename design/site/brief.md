# Nagi website: brief (13 Nov 2026)

The panel's own records (`design/product.md`, `project-bar.md`, `art-direction-spec.md`) stay authoritative for the panel. This folder is the **public website** for the open-source release. Static, in `site/`, branch `nagi/site`; GitHub Pages or Vercel, no server.

## The owner's request, condensed
- **Nagi (凪, "calm sea") is a tiny menu-bar / tray glance for people running AI coding agents.** It answers two questions only: *What are my agents doing right now?* and *Am I about to hit my limits?*
- **Feeling:** Apple-grade craft, calm and precise. Think Linear or iStat Menus, not a SaaS template.
- **Hates:** a gradients-and-glow hero, a bento of fake stats, dashboard creep, anything that looks like Windows (tiles, bordered cards, acrylic).
- **The hero shows the real panel, alive:** an agent appears and branches from its parent, one goes quiet, a limit line ticks down. Built from the real `web/glance-v2` code fed with fictional data, not a redrawn mock-up.
- **Carry the panel's identity over; don't reinvent it.** Now Line + Lineage + Lull. Grammar: vertical is time and parentage, horizontal is silence, rose is now or "asks you", yellow is silence past halfway. Provider colours: Claude terracotta, Codex green, Gemini blue. Inter, and the 凪 glyph as the mark.
- **Sections to consider (direction decides the shape):** hero with Install and GitHub; the two questions and how the panel answers each in two seconds; local-first and private; sources (T3 Code today, others coming soon, room for "write an adapter"); install; open source.
- **Gates:** Lighthouse 95+ in every category, AA contrast in light and dark, reduced motion honoured, works at 375 px. Copy plain, confident, short, no hype words.

## What is true on main (8d33569); every claim must trace here
| Claim | Evidence |
|---|---|
| Two questions, nothing else; read-only, no stop/send/approve | `design/product.md`, `README.md` |
| Loopback reader bound to 127.0.0.1, owner proof or session on every API, exact Host/Origin checks, Linux socket UID check, no cookies | `server.py:195`, `README.md` "Local owner boundary" |
| Read-only T3 access with a token scoped `orchestration:read`; no T3 database or provider credential store is read | `README.md`, `t3_reader.py` |
| Another computer is reached only over your own Tailscale (pairing link or `--t3-origin http://100.x…:3773`); computers never read each other's feeds otherwise | `README.md`, `sources_service.py` placement `local`/`tailscale` |
| No cloud, no account, no telemetry: the reader only talks to T3 origins you configure | grep of network calls; only `t3_reader.py`/`sources_transport.py` on the glance path |
| Linux: GTK 3 + WebKitGTK tray (Ayatana AppIndicator), systemd user service | `install.sh`, `linux/` |
| macOS: native menu-bar app (SwiftUI shell with WKWebView), LaunchAgent | `mac/`, `install.sh` |
| Install: `./install.sh` on Linux or macOS, Python 3.11+; never overwrites data, owner key or connections; sudo only for missing Linux desktop libraries, and it asks | `install.sh` |
| In-app setup: four steps (which apps, where, connect, done) | `web/glance-setup.js`, spec "Sources, phase 1" |
| Sources catalog: **T3 Code available**; OpenBot, Pi, oh-my-pi, Codex, Claude Code, Hermes, OpenClaw, OpenCode **coming soon** | `sources_service.py:40` `CATALOG` |
| Limits: one line per account, lowest window first, % left and reset date; never averaged; "empty" only on fresh evidence; "couldn't check · tried HH:mm" only on a failed read | `web/glance-model.js` `limitLines` |
| Limits come from Codex and Claude windows (Gemini has a model colour but no limits source) | `glance-model.js` `PROVIDERS` |
| Notification once when a thread fails or goes stuck (15 min default, 5–120) | `README.md`, `linux/notifications.py`, `mac/Sources/Nagi/Notifications.swift` |
| Ended group: last 24 h by default (1–168), collapsed | `README.md` |
| Licence | **None yet.** No root `LICENSE`; the site must not name one until the owner picks |

## Real-content seeds
- **The panel, running the real code on a fictional fixture:** `site/panel/` (synced from `web/` by `site/scripts/sync-panel.mjs`; `site/panel/demo.js` is the fixture, fetch shim and virtual clock). Scenes: `?scene=story` (animated), `still`, `asks`, `stuck`, `offline`, `limits`, `quiet`.
- **Captures:** `design/site/seeds/panel-*-{dark,light}-*.png` (400×720 CSS px at 2×).
- **Fictional projects:** Tidepool (a field-notes app), Kestrel API, Lantern Docs. Accounts Codex 1 (empty), Codex 2, Claude 1. Never the owner's titles, projects, hosts or accounts.
- **Story the hero tells (real motion engine):** open → the rose now line sweeps up across two agents that started since the last look and their branches draw from the parent → a minute a beat: the Gemini agent goes quiet (grey stroke, yellow past half, `silent 15 m`, hero `1 stuck`), the Opus agent speaks again and its stroke clears, Claude's Session window ticks down → "half an hour later" the panel opens again and a new Sol agent branches from the same parent.
- **Install commands:** `git clone https://github.com/yeqiuqiu123/nagi && cd nagi && ./install.sh` (Linux and macOS).

## Reference ladder (fixed captures in `design/references/<slug>/`, gitignored; 1440 and 390, first screen and full page)
| Slug | URL | Role | Why |
|---|---|---|---|
| `mizu` | usemizu.com | Competitor (closest) | Menu-bar panel for agents and usage rings. Hero = MacBook mock-up with the panel; we beat it with the real panel and named agents |
| `conductor` | conductor.build | Competitor | Parallel coding agents on a Mac; dev-tool marketing voice |
| `superset` | superset.sh | Competitor | Agent workspace; fleet-of-agents language |
| `istat-menus` | bjango.com/mac/istatmenus | Best in sector (menu-bar utility) | Dense real readouts as the hero; we refuse its gauges and gradients |
| `linear` | linear.app | Best in sector (craft) | Product UI as the hero, calm dark type, precise rhythm |
| `ghostty` | ghostty.org | Best in sector (open-source dev tool) | One object, one sentence, two buttons; restraint |
| `tailscale` | tailscale.com | Best in sector (privacy explanation) | How "your own network" is explained plainly |
| `creative-reference-library` | crl-2026.webflow.io | Awwwards SOTD 10 Nov 2026 | Index/catalogue typography, kinetic wordmark |
| `a24-klaassens` | a24.raviklaassens.com | Awwwards SOTD 26 Oct 2026 | Editorial restraint; a single object and a counting numeral |
| `grail` | grail-app.com | Awwwards SOTD 4 Nov 2026 | Confident display type, flat colour |

Award records were verified on 12 Nov for the panel project (`design/brief.md`); captures were not re-browsed.
