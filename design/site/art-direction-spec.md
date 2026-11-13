# Nagi website: art-direction and motion spec

Written by the builder (Opus 5.5) on 13 Nov 2026. It records the values built and verified for the slice, and Fable's direction and bar decide anything not settled here.
- **Sources:** `creative-direction.md`, `concept-selection.md` (with the sign-off), `project-bar.md` and `copy/deck.md`.
- **The embedded panel stays under `design/art-direction-spec.md` and `design/project-bar.md`.** The site never restyles, scales or patches it.

## 1. The idea
**The page is the panel's drawing at page scale.** The panel's rose now line continues across the page at the same height. Its rail becomes the page's trunk, and each section hangs from it on a branch. The limits question sits above the line and the agents question below it.

## 2. Identity
- **Wordmark:** `凪 nagi`. The glyph is the panel's one-glyph Noto Serif subset at 28 px; `nagi` is Inter 620 at 18 px, tracked 0.01em.
- **Colour:** the panel's tokens verbatim, following the system theme with no toggle.
  - **Rose** (`--rose` and `--rose-text`) appears only on the now line, the Install nodes and `Copy`.
  - **Yellow** never appears outside the panel.
- **Type:** Inter, self-hosted and shared with the panel's own font file.

| Role | Size and weight |
|---|---|
| Display: the questions, section heads | Inter at opsz 32, weight 560, tracking −0.03em, line-height 1.08. Questions 46 px (34 px at ≤960, 30 px at ≤360); section heads 34 px (28 px at ≤960) |
| Lede (h1) | 21/1.4, weight 500, `--secondary` |
| Body | 17/1.5 |
| Answer lines | 18 |
| Fine print, actions | 15 |
| Demo caption | 13 |
| Mono (install command) | System UI mono at 15 px; 14 px at ≤560 |

- **Rules:** none. The page draws no divider. Lists are spaced 14–20 px apart.

## 3. Layout
**At 1440:**
- The page is up to 1280 px wide with a 48 px gutter.
- The panel column is 400 px wide, with an 88 px gap to the copy column (copy max 600 px).
- The grid's first row is `--demo-top` (40) plus `--line-y` (the panel's line, measured: 219 at 400 px).

**Desktop v2 (961 and wider), 13 Nov 2026:** superseded by `desktop-v2-direction.md` (Fable call 6): one five-column grid, the tray legend as a five-up band, then two staggered pairs (Privacy with Honesty, Sources with Install), panel nodes per section, and Sources as a sub-tree. 1,998 px at 1440, down from 3,078. From 961 to 1199 the lede is 19 px and the first question 40 px, so they keep a gap of 20 px or more.

**Below 960:** one column with a 16 px gutter. The lede and the two questions come first, then the panel.
- **At ≤560:** the opening's command is hidden; the command lives at the Install node and steps back to the gutter.

**Sections:**
- Each section hangs at `--rail` (22, the panel's `--trunk-x`) plus `--hang`: 36 px on desktop, 32 px on mobile.
- Sections are spaced 128 px apart (88 px on mobile). The first sits 72 px below the opening (56 px on mobile).

**Panel slot:** it reserves the panel's tallest story height, so the page never shifts as the panel grows.

| Width | Slot | Initial frame |
|---|---|---|
| Desktop | 644 | 589 |
| ≤480 | 682 | 627 (line at 237) |
| ≤360 | 694 | — |

## 4. Strokes and nodes (the panel's own)
- **Trunk and branches:** `--stroke`, 2 px, round caps, with 10 px elbows.
- **Section nodes:** hollow rings, r 4.
- **Install node:** a rose dot, r 5.
- The trunk starts 5 px below the centre of the panel's last ring and is drawn over the panel's lower edge.

## 5. Motion

| Moment | Trigger | What moves | Timing |
|---|---|---|---|
| Panel open (the product's own) | The panel's now line, at rest, comes on screen, or the panel's slot is in the top 85% of the screen | The panel's line travels up across the rows that started since the last look, and their branches draw in. The page line follows the same transform and opacity in the same frame | The panel's 700 ms `--ease-out`; branches 260 ms each, 90 ms apart |
| Story beats (demo) | After the open | A virtual minute per beat: silence strokes grow, one clears and limits tick down. Then "half an hour later" the panel reopens and a new branch draws | Beats 0.9 s apart, then 2.6 s |
| Section branch draw | The section enters the viewport (bottom inset 20%) | The branch's stroke-dashoffset runs from its length to 0; the node appears with it | 260 ms, `cubic-bezier(0.77, 0, 0.175, 1)`, once |
| Copy feedback | Click | The label reads `Copied` and a hidden status speaks it | Instant, resets after 2.4 s |

**Reduced motion:** the story is paused on its still frame (stuck visible), with Play available. There's no travel, and every branch is already drawn.

**No JavaScript:** a still capture of the real panel, with alt text that says what it shows.

```motion-surfaces
[
  {"surface": "Panel open: now-line travel and new-branch draw (the shipped panel's own motion)", "usage": "rare", "frequency": "rare", "file": "site/panel/nagi-motion.js", "reason": "The product's signature moment, once per page view and again at the story's reopen; explains what is new since the last look."},
  {"surface": "Demo story beats: silence growth and clearing, limits ticking, the reopen", "usage": "rare", "frequency": "rare", "file": "site/panel/demo.js", "reason": "Plays once per page view with Pause and Replay; explains what the panel shows over time."},
  {"surface": "Settings sheet open and close (the shipped panel's)", "usage": "occasional", "frequency": "occasional", "file": "site/panel/nagi-sheet.css"},
  {"surface": "Copy the install command (label change only, no motion)", "usage": "occasional", "frequency": "occasional", "file": "site/js/site.js", "lines": [19, 32]},
  {"surface": "Page line following the panel's travel", "usage": "rare", "frequency": "rare", "file": "site/js/site.js", "lines": [33, 72], "reason": "The same line as the panel's, moved in the same frame."},
  {"surface": "Section branch draw, once per section per page view", "usage": "rare", "frequency": "rare", "file": "site/js/site.js", "lines": [73, 161], "reason": "Each section hangs from the trunk as the panel's branches do: 260 ms short, 420 ms long, then the Sources rail and its children 90 ms apart; fires once."},
  {"surface": "Links, demo controls and hover (no motion)", "usage": "occasional", "frequency": "occasional", "file": "site/index.html"}
]
```

## 6. Truth rules
- **Quoted panel strings are computed, never typed.** The tray legend rows and the three "says" rows come from the panel's own `NagiModel` (`traySources`, `buildSources`) on the demo fixture at the panel's clock, and refresh on every beat.
- **The demo fixture is invented** and stays so (`site/tests/site.test.mjs`).
- **No storage, no cookies, no third-party requests.** Fonts are self-hosted.

## 7. Performance and quality, measured on the slice
| Check | Result |
|---|---|
| Lighthouse mobile | Performance 97–99; accessibility, best practices and SEO 100; CLS 0 |
| Lighthouse desktop | 100 in every category |
| axe | Clean in both themes at 1440 and 375, for the page and the embedded panel |
| Page line against the panel's line | Within 0.16 px from 375 to 1920 |

## Open items
- **Done:** the limit dates that wrapped at narrow widths are fixed in the panel source (a ≤380 px column rule; the shipped 400 px panel is unchanged). The Ended button's name now matches its visible text (WCAG 2.5.3), also in the panel source.
- **Follow-up (taste, the fresh judge):** section nodes are identical hollow rings; give each one meaning from the panel's node vocabulary.
