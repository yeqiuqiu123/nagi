# Nagi art-direction and motion spec: the fused Now Line

Opus 5.5 (art director, fresh reader), 13 Nov 2026. Sources: the creative direction, the owner's pick, the binding `project-bar.md`, the explorer's prototypes and `api-contract.md`. Every value below was tried in a prototype unless it is marked **untested**. Agent titles never appear in this file.

**Decision.** **Layout A, Inter with Inter Display for the numeral, motion variant a for travel and branches, tray V1 `凪 3`.** I agree with the explorer on all four.
- **From B, I take the latest-start project order.**
- **I overrule the borrow of B's left time gutter.** A 56 px gutter takes 34 px from every title line. In B it wrapped two more titles and left 4 px of slack tonight. A wraps one title and keeps 13 px. The owner asked for readability, so the width goes to titles.
- **The rose now time stays at the right end of the hero,** where A has it (`shots/layout-a-dark.png`).
- **Each project heading carries its start time instead** (**untested**), so the reordering still reads as time.

## 1. The idea
**One vertical axis, with the rose line at now.** What will stop the work (limit reset dates) sits above the line, the count sits on it, and the agents and their lineage hang below it.

It should feel like looking through a quiet window at people working, and the glance never draws what it doesn't know.
- **Signature moment 1:** a `silent 17 m` row's stroke turns amber and runs full width before any notification fires.
- **Signature moment 2:** the now line sweeps up from the last open and crosses the rows that started since then.
- **Dials:** density high, motion low, colour very low (rose plus amber only), type-led, with no imagery.

| Message | Carrier |
|---|---|
| Running count | The 56 px numeral on the line |
| Which agents | Verbatim titles at 15 px |
| Lineage | The drawn trunk, branches and nodes |
| Silence | One 2 px stroke per running row |
| Limits | The table above the line, with dates |

## 2. References that matter
- **`mizu`:** the glance to beat. We name agents where it prints "Agents 2". We take its single-panel density and refuse its tiles, rings, toggles and sparklines.
- **`istat-menus`:** the bar readout must read at 1× with no legend. We take dense right-aligned numerals and refuse its colour-coded gauges.
- **`linear`:** rows where the title leads and one quieter metadata line follows. Children hang from a drawn branch, never from an indent alone.
- **`a24-klaassens`:** a single large numeral as the hero, with everything else held back.

## 3. Identity
**Wordmark.** The header reads `凪 nagi`.
- **凪:** a one-glyph subset of Noto Serif CJK JP (`nagi-glyph-notoserifcjk.woff2`), 22 px, line-height 1.
- **nagi:** Inter 15/620, tracking 0.01em.
- **Right side:** `Linux` at 13/420 `--secondary`, then the settings gear (32×32 button, 18 px icon, 1.6 px stroke).
- **Tray:** 凪 drawn from the Noto Sans CJK JP glyph (`nagi-glyph-notosanscjk.woff2`).

**Colour.** The explorer's tokens (now in `web/glance-v2.css`) are used verbatim. The theme follows the system dark or light setting, with no in-app theme switch (**untested** switching). Ratios were measured in WebKit in `contrast.html`; the floors come from the bar.

| Token | Role | Night hex / OKLCH | Day hex / OKLCH | Night / day ratio on `--bg` (floor) |
|---|---|---|---|---|
| `--bg` | panel background | `#18131d` 19.8% .021 307 | `#f2f0f6` 95.8% .008 301 | — |
| `--sheet` | settings sheet | `#241d2b` 24.5% .028 307 | `#fbfafd` 98.7% .004 301 | — |
| `--title` | titles, numeral, account names | `#f5f1f8` 96.3% .010 311 | `#17121c` 19.3% .021 307 | 16.37 / 16.29 (12) |
| `--secondary` | model, run time, dates, % left, completed-parent ring | `#cdc4d6` 83.3% .027 308 | `#403849` 35.6% .031 306 | 10.84 / 9.88 (7) |
| `--tertiary` | dimmed project prefix, separators | `#a397b0` 69.5% .038 307 | `#645b70` 48.7% .035 305 | 6.62 / 5.68 (4.5) |
| `--stroke` | trunk, branches, silence stroke under ½ | `#9486a3` | `#6b6280` | 5.39 / 5.04 (3); on hover 4.99 / 4.58 |
| `--hair` | non-meaning rules (sheet only) | `#3a3142` | `#dcd7e4` | — |
| `--rose` | now line, now dot, asks-you node | `#ff7aa5` 74.5% .167 2 | `#c8235f` 54.9% .200 6 | 7.46 / 4.81 (3) |
| `--rose-text` | now time, `asks you` | `#ff9dbb` 80.4% .121 0 | `#8f103c` 42.3% .159 9 | 9.39 / 8.05 (7) |
| `--amber` | silence stroke at ½ or more (now a yellow) | `#e6c84a` | `#7d6800` | 11.07 / 4.82 (3); on hover 10.25 / 4.38 |
| `--amber-text` | `silent 17 m`, `1 stuck` (now a yellow) | `#ecd27a` | `#594a00` | 12.23 / 7.72 (7); on hover 11.33 / 7.02 |
| `--pv-claude` / `-node` | Claude model word / node | `#e2977f` / `#d97757` | `#7b331c` / `#d15a34` | word 7.80 / 7.96 (7), node 5.85 / 3.56 (3) |
| `--pv-codex` / `-node` | Codex model word / node | `#13c197` / `#10a37f` | `#085240` / `#0e9071` | word 7.92 / 8.10, node 5.71 / 3.54 |
| `--pv-gemini` / `-node` | Gemini model word / node | `#7caaf7` / `#4285f4` | `#0943a3` / `#317af3` | word 7.78 / 7.92, node 5.13 / 3.57 |
| `--focus` | keyboard focus only (neutral, = `--secondary`) | `#cdc4d6` | `#403849` | 10.84 / 9.88 (3) |
| `--hover` | row hover fill | `#211a27` | `#e8e5ee` | titles 15.16 / 14.80 |
| `--control` and `--control-border` | fields and buttons | `#2c2433`, `#8b7f99` | `#ffffff`, `#847a97` | border 3.97 / 4.03 (3) |
| `--scrim` | behind the sheet, at 0.62 opacity, never carrying text | `#0d0a10` | `#c9c4d3` | — |

**Balance.** About 60% `--bg`, 30% `--title` and `--secondary` text, and 10% strokes. Rose appears as one line, one dot and at most two words. Amber marks only silence past halfway.

**What never appears together:**
- Rose and amber never share a row; asks-you suppresses the silence stroke.
- Rose never appears on limits.
- Focus is a neutral ring in the panel's own palette (see Changes).
- Text is never dimmed with opacity.
- Failed and stopped rows get no status colour.

**Type.** Inter, as `inter-latin-opsz-normal.woff2` (73 KB, OFL 1.1, free, licence in `explore/fonts/inter-LICENSE.txt`). Inter Display is the same file at `font-variation-settings: "opsz" 32`.
- **Rejected:** Newsreader over Geist (a serif numeral; costs 301 KB) and Atkinson Hyperlegible Next (the most legible, but the least Apple).
- **Why Inter:** GNOME's Adwaita Sans is built on Inter.
- **Every number** uses `tabular-nums`.

There is a single size class, because the panel is 400 px wide (the 1440 and 390 sizes don't apply).

| Role | Size / weight / line-height |
|---|---|
| Count numeral | 56 / 560 / 1.0, opsz 32, tracking −0.03em |
| `running` | 20 / 560 |
| Running title | 15 / 560 / 1.34, wraps, never ellipsised, `overflow-wrap: anywhere` |
| Completed-parent title, Ended line | 15 / 500 |
| Account name | 15 / 560 |
| % figure | 15 / 640, with `left` at 13 / 420 |
| Sub-window row | 13 / 420 name, 13 / 600 % |
| Meta, dates, help | 13 / 420 / 1.38 |
| Project heading | 13 / 680, tracking 0.01em, `--title` |
| Hero right | now time 15 / 640 rose; alert 15 / 650; sub-lines 13 / 420 |
| Sheet | title 15 / 650, labels 15 / 520, buttons 13 / 560, fields 15 tabular |

Measure: titles run at most 322 px (depth 1) and 300 px (depth 2), about 40–45 characters a line. There are no tracked capitals, no mono and no italics. The lowest weight is 420, apart from the glyph.

**Voice.** Dates first, plain, exact.

| We say | We don't say |
|---|---|
| `Codex 1 · 0% left · Mon 16 Nov 21:58` | `Resets in 3d` |
| `silent 17 m` | `Stalled!` |
| `couldn't check · tried 06:03` | `0%` or `Error` |

The copy deck is `explore/copy.md`, approved with three amendments:
- **(a)** The tray menu is `Open Nagi`, `Settings…`, `Quit Nagi`.
- **(b)** The limits as-of suffix is `· as of {HH:mm}`, per account.
- **(c)** The Ended expansion lists failed and stopped threads by title (see Q2).

## 4. Layout and composition (400 px wide, height hugs content up to 690 px)
**Geometry,** from `panel.css` layout A:
- **Trunk** at x 22 px; **content** at x 40.
- **Depth 1:** node at 46, text at 62. **Depth 2:** node at 68, text at 84.
- **Depth 3 and deeper:** +22 px per level, capped at depth 3 with the branch still drawn from the true parent (**untested**).
- **Right padding** 16 px.

**Vertical spacing:**
- Header 46 px tall.
- Limit rows 22 px minimum, sub-rows 19.
- Now block margin-top 10; the count's baseline sits 6 px above the line.
- Rows have 4 / 8 px padding and project groups a 6 px gap.
- The past region starts 10 px below the line, the Ended block has an 8 px top margin, and the panel has 14 px of bottom padding.

**Strokes and nodes:**
- **Trunk and branches:** 1.75 px `--stroke`, round caps, 10 px elbows.
- **Now line:** 2 px `--rose`, full width, with a now dot of r 5 and a 3 px `--bg` halo.
- **Running node:** a filled 10 px `--title` dot.
- **Completed-parent node:** a 1.75 px `--secondary` ring.
- **Asks-you node:** a `--rose` dot.
- **Limit node:** a hollow `--stroke` ring, filled `--title` when the window is at 0%.
- **Ended node:** a hollow ring of r 4.
- **Silence stroke:** 2 px, radius 1, from the row's text x to 16 px from the right edge, 2 px above the row bottom. It is hidden under ⅓ of the stuck threshold, `--stroke` from ⅓ to ½, `--amber` at ½ or more, and full width at the threshold.

**Radii and shadows:**
- Radii: row hover 8, gear 8, sheet 12, field 6, button 7.
- The only shadow is the sheet's: `0 0 0 .5px var(--stroke), 0 18px 48px rgb(0 0 0/.38)`.
- No cards, no borders on rows.

**Order:**
- **Limits:** accounts lowest window first, then the `not set up` and `unsupported` providers.
- **Projects:** by the latest start of any active descendant, newest nearest the line, so down means older.
- **Siblings:** newest first (**untested**).
- **Project heading:** the title left, with its earliest active start `{HH:mm}` right-aligned at 13 / 420 `--secondary` (**untested**).

**Height** (**untested**): the panel opens at the content height, with a minimum of 320 px and a maximum of 690. It resizes only on open, so the quiet state isn't 400 px of dead space.

### (1) Overflow rule: 4 or more running rows. Nothing ever truncates a title.
1. **Pinned, never scrolling:** the header, the limits table, the hero and the now line. This is every 2-second fact except the rows themselves: the count, the lowest window and its date, and the `k asks you · j stuck` words.
2. **Step one:** if the content is taller than 690, each completed parent folds to one line, `{title} · completed`. The title stays 15 / 500 `--title` and may wrap, with `· completed` at 13 / 420 `--secondary` inline. This saves about 19 px per parent (**untested**).
3. **Step two:** if it is still taller, the region below the now line becomes a native overflow scroll (WebKitGTK overlay scrollbar).
   - **Rows slide under the rose line,** which is the clip edge; no fade or gradient mask.
   - **The trunk and branches** live inside the scrolled content.
   - **The Ended line** is the last item of the scroll, not pinned.
   - **Scroll resets to the top** on every open.
4. **The hero's state words become buttons** when a stuck or asks-you row is out of view. `1 asks you` and `1 stuck` scroll that row into view, instantly and with no animation (**untested**). Rows are never reordered to the top, because the axis is time.

Tonight's real content (3 running, 2 parents, 3 accounts and 5 windows, Ended collapsed) measures 677 / 690 in WebKit and needs neither step. That leaves 13 px, one wrapped title.

## 5. Imagery and media
**None.** This is a type-led instrument. There are no logos, model icons or illustrations. Models are words.

## 6. Motion system
**Principle.** Motion explains only two things:
- **What is new since you last looked** (the line travel and new branches).
- **That silence ended** (the stroke clears).

The panel open, hover, Ended, scroll, the tray and every keyboard path change on the next frame.

**Tokens:**
- `--ease-out: cubic-bezier(.22,1,.36,1)`.
- `--ease-draw: cubic-bezier(.33,0,.2,1)`.
- The node pop is a 320 ms spring sampled to CSS `linear()` (ζ .55, ω 20).

**Tried and rejected:**
- **Travel:** b, a 900 ms spring that overshoots above now, so for a frame the line claims the future; c, 420 ms ease-in-out, where crossings don't register.
- **Branches:** b, 420 ms each, 160 ms apart, which leaves the tree half-drawn for 1.5 s; c, 160 ms each, 50 ms apart, where the order is invisible.
- **Silence spring-back:** a, a 420 ms spring at ζ .62, ω 18, which is busy beside the travel; b, a 720 ms soft spring, which wobbles.

| Moment | Trigger | What moves | Timing | Interrupt | Frames |
|---|---|---|---|---|---|
| Now-line travel | Panel opens and ≥1 row started since the last open, and the last open was ≥30 min ago (**untested** gate) | The line and its dot translateY from just below the lowest new row to now; each crossed row's title flashes `--rose-text`→`--title` over 900 ms ease-out, and its node pops ×1.6 | 700 ms `--ease-out`, transform only | Any click or key snaps to the end state | `shots/motion-a.png`, `motion-open-a.png` |
| Branch draw | Same gate; only branches new since the last open | stroke-dashoffset from length to 0, in spawn order; nodes pop as their branch arrives | 260 ms each, 90 ms apart, 260 ms delay, `--ease-draw`; at most 6 staggered, the rest appear at once (**untested** cap) | As above | `motion-a.png` |
| Silence growth | Each 20 s poll | scaleX of the stroke, origin left | Steps with data, no easing | — | `motion-a.png` |
| Silence clears | A running row's activity resumes while the panel is open | scaleX → 0, then hidden | 240 ms `--ease-out`, no overshoot (variant c) | Restarts on the next poll | `motion-c.png` |
| Settings sheet | Gear or tray `Settings…` | The sheet does translateY −12 px → 0 with opacity 0 → 1; the scrim fades 0 → .62 | In 240 ms, out 190 ms, `--ease-out` (**untested**) | Esc mid-flight reverses | — |

The 700 ms travel exceeds the 300 ms product band for a mechanical reason: each crossed row needs several frames under the line to register as crossed, and at 420 ms the frame strips show none. The gate keeps it to the occasional tier.

**Scroll.** Native only; nothing is driven by scroll.

**Reduced motion** (`shots/motion-reduced.png`):
- No travel and no draw.
- The silence stroke steps once per minute and clears with no animation.
- The sheet appears instantly.

```motion-surfaces
[
  {"surface": "Panel open and close from the tray indicator", "usage": "high-frequency", "frequency": "tens a day", "file": "linux/notifications.py"},
  {"surface": "Agent row hover, focus and open-in-T3", "usage": "high-frequency", "frequency": "100+ a day", "file": "web/glance-v2.css"},
  {"surface": "Ended line expand and collapse", "usage": "high-frequency", "frequency": "tens a day", "file": "web/glance-v2.js"},
  {"surface": "Hero state words scroll a row into view", "usage": "keyboard-driven", "frequency": "keyboard-initiated", "file": "web/glance-v2.js"},
  {"surface": "Now-line travel and new-branch draw, gated to opens after 30 min with new rows", "usage": "occasional", "frequency": "occasional", "file": "web/glance-motion.js", "reason": "Gated to state change since the last look; crossings need about 700 ms to register (variant c at 420 ms showed none)."},
  {"surface": "Silence stroke clears when an agent speaks", "usage": "occasional", "frequency": "occasional", "file": "web/glance-motion.js", "reason": "Data-driven, only after 5 or more minutes of silence while the panel is open."},
  {"surface": "Settings sheet open and close", "usage": "occasional", "frequency": "occasional", "file": "web/glance-sheet.css"},
  {"surface": "Settings steppers, fields and buttons", "usage": "high-frequency", "frequency": "many per session", "file": "web/glance-v2.css"}
]
```
`linux/notifications.py` holds the tray and panel window. The occasional motion lives in its own files (`web/glance-motion.js`, `web/glance-sheet.css`) so the high-frequency files stay motion-free.

## 7. Interaction details and state treatments
**General interaction:**
- **Hover:** the row fill is `--hover`, with no transition.
- **Focus:** a 2 px `--focus` outline, offset 2 (−2 inside rows).
- **Pressed:** nothing; a row opens the thread through `links.desktop`, falling back to `links.web`, and the panel hides.
- **Cursor:** default arrow everywhere, as in Apple's menu-bar panels. There is no sound.
- **Esc:** closes the sheet, then the panel.

### (3) State treatments
| State | Hero (left · right) | Rows / limits | Tray |
|---|---|---|---|
| Calm | `3 running` · `06:05` (rose) / `all spoke in the last 9 s` | As captured | `凪 3` |
| Asks you | right: `06:05` / `1 asks you` (15 / 650 `--rose-text`) | The node turns a `--rose` dot; the meta leads with `asks you · 4 m` (640, rose-text) then `· Opus · 6 m`; no silence stroke (`layout-a-waiting.png`) | `凪 3 ?` |
| Stuck (`stuck === true` only) | right: `06:05` / `1 stuck` (`--amber-text`) | The meta leads with `silent 17 m` (640, amber-text) then `· Sol · 3 h 29 m`; the silence stroke is full width `--amber`; the node stays a `--title` dot (`layout-a-light-stuck.png`) | `凪 3 ●` |
| Both | right: `1 asks you · 1 stuck` | As each | `?` outranks `●` |
| Liveness `unknown` or `child_wait`, or `stuck` null | — | No silence stroke and no amber; the meta keeps `{d} ago` (**untested**); never an alarm | — |
| Can't reach T3 (last-known) | The numeral and `running` turn `--secondary` (**untested**); right: `Can't reach T3 Code` (15 / 650) / `tried 06:08 · list from 06:05` / `limits from 06:03`, with no rose time | Rows say `last seen 06:05`; no strokes, no rose, no amber; the limits keep their values (`layout-a-unreachable.png`) | `凪 –` |
| Never reached / not paired | `—` · `Can't reach T3 Code · tried {HH:mm}` + `Nagi hasn't read T3 Code on this computer yet.` / `T3 Code isn't connected on this computer.` | No rows | `凪 –` |
| First check | `—` · `Checking T3 Code…` | Limits read `checking…` | `凪` |
| Quiet (nothing running) | `0 running` · `06:05` / `nothing running since {HH:mm}` | No project rows; the trunk runs from the now dot to the Ended node; with nothing ended either, `Nothing ran in the last 24 h.` (15 / 500 `--secondary`) replaces Ended (**untested** capture) | `凪` alone |
| Limits: couldn't check | — | `Codex 1` · `—` · `couldn't check · tried 06:03`; never 0, a ring or a bar | — |
| Limits: last known | When T3 is down, only the hero's `limits from 06:03`; otherwise the date cell adds `· as of 06:03` and may wrap | — | — |
| Limits: not set up / unsupported | — | `Claude` · `—` · `not set up on this computer` / `no limits for this account type`, listed last | — |
| Limits: empty (0%) | — | `0%` at 15 / 640 `--title` with the filled node; no colour | `凪 3 0%` |

### (2) The Ended line
**Collapsed** (`layout-a-dark.png`):
- **Line 1:** `135 ended since Thu 06:05 ›`. The number is 15 / 640 `--title`; the words are 15 / 500 `--secondary`; the chevron is a 12 px, 1.6 px stroke.
- **Line 2:** `6 threads and 129 sub-agents · {projects}` at 13 / 420 `--secondary`, which wraps.
- **What the count holds:** every ended id at any depth, excluding context-only rows (verified 6 + 129 = `counts.ended`).
- **Target:** the whole two-line block is one button, with `aria-expanded` and the deck's label.
- **It opens collapsed every time.**

**Expanded** (built with `?ended=open`, not captured, so **untested**). Inline, inside the scroll region, which scrolls so the Ended line sits under the now line:
- **Project order:** latest end first.
- **Per project, two lines:** `{Project}` at 15 / 500 `--title`, over `77 completed, 2 stopped · 06:13–23:03` at 13 / 420 `--secondary`. Zero counts are omitted. A range that crosses days takes day prefixes: `Wed 23:34–Thu 16:04`.
- **Beneath each project,** only its failed and stopped threads, as link rows: title 15 / 500, meta `Sol · failed 09:57`.
- **Identical siblings** (same title and state) fold to `6 × {title} · failed 09:57–09:58`.
- **Completed threads are counted, never listed.** This is not a history view.
- **No branches** inside Ended.

**Empty:** the line is absent.

### (4) Tray on GNOME (Shell 46, ubuntu-appindicators, `linux/notifications.py`)
**Item.** One StatusNotifierItem:
- **Icon:** a symbolic SVG, `nagi-symbolic`, 16 px, outlined from the Noto Sans CJK 凪 glyph (OFL), so the shell recolours it.
- **Label:** `XAyatanaLabel` text in the shell's own bold.
- **Label values:** `3`, `3 ●`, `3 ?`, `3 0%`, `–`, or empty when nothing is running (and `0%` alone if a window is empty).
- **Precedence:** unreachable `–` replaces the count, then `?` outranks `●`, which outranks `0%`. One mark at a time.
- **Tooltip:** follows the deck, but the label must stand alone, because tooltip support in the extension is **untested**.
- **The `0%` mark stays on** while Codex 1 is empty. The bar requires it, and it is true.
- **Re-capture on the real bar.** The label renders in this machine's shell font, not the Inter stand-in in `tray.png`.

**Click target.** The whole indicator pill (icon and label, the shell's roughly 26 px hit area).
- **Left click** toggles the panel. That needs an SNI with `ItemIsMenu=false`, because Ayatana forces a menu (**untested** on Shell 46).
- **Middle click** also toggles; this is today's secondary-activate path.
- **Right click** opens `Open Nagi`, `Settings…`, a separator, then `Quit Nagi`.
- **If left click still opens the menu,** `Open Nagi` is the first item, and the gap is recorded.

**Panel placement.** It appears with no animation 4 px under the bar, its right edge aligned to the indicator, at least 8 px from the screen edge. It hides on focus loss, Esc, a second click or opening a thread.

### (5) Settings sheet
**Idiom: a macOS sheet,** attached under the header (`settings.png`, `settings-dark.png`).
- **Frame:** inset 12 px, top 8 px, radius 12, padding 18 / 20 / 16, on `--sheet`.
- **Title and lede:** `Settings` / `Saved on this computer only.`
- **Field rows:** label left, then a 52×26 right-aligned tabular field, an 18×12 ×2 stepper and the unit at 13 / 420 `--secondary`. Help text sits below at 13 / 1.4, with 1 px `--hair` rules between rows.

**Values:**
- **Stuck after:** `15` minutes by default, range **5–120**, step 1.
- **Clear ended after:** `24` hours by default, range **1–168**, step 1.
- **Keys:** ↑/↓ step 1 and Shift+↑/↓ step 10 (**untested**).
- **Out-of-range values** clamp on blur, with `Set to {v}, the nearest allowed value.` beneath the field. The server's clamped values are what the sheet shows after Save.

**Buttons** (26 px, radius 7, 13 / 560):
- **`Restore defaults`** becomes a bordered push button on the left, not the underlined link that was tried (**untested**), because macOS has no links in sheets.
- **`Cancel`** is bordered.
- **`Save`** is the default button (`--default-btn`).
- **Return** saves; **Esc** cancels.
- **Save** is disabled until a value changes (**untested**).

**Errors:**
- **A failed save** keeps the sheet open with `Couldn't save. Your settings are unchanged.`
- **`settings_invalid`** shows its sentence under the lede.

## 8. Don'ts
**Bar tells:**
- A second axis, a bracket, or a silence strip on limits.
- 1 px branches.
- Tracked capitals, mono or italics.
- Grey-on-grey meta.
- Tiles, rings, progress bars, pills or toggles.
- Acrylic or blur.
- Sparklines, totals or a second hero number.
- Ellipsis truncation.
- Status colour beyond rose and amber.

**This project's risks:**
- Animating every open.
- Raising stuck rows out of time order.
- Drawing a silence stroke when liveness is unknown.
- Merging Codex 1 and Codex 2.
- Counting completed parents.
- Printing `0` for a failed check.
- Any agent control.

**On purpose:** one Japanese glyph, and a sheet borrowed from macOS on Linux.

## 9. Performance budget (local panel; Lighthouse doesn't apply)
| Measure | Budget |
|---|---|
| Click to first paint, from the cached glance | ≤100 ms (**untested**) |
| Panel JS, uncompressed | ≤60 KB (**untested**) |
| Fonts | 73 KB Inter + 2 × ~1 KB glyphs |
| Geometry redraw per 20 s poll | ≤8 ms at 50 rows (**untested**) |
| Line travel and branch draw | No task over 50 ms, no layout shift (transform and dashoffset only) |
| `/api/glance` p95, local cache | ≤50 ms (**untested**) |

## Changes
Builder, 13 Nov 2026 (glance slice). Each is a value tuned for the browser or the platform, not a change of direction.
- **Limit table columns 104 / 72 px → 100 / 66 px.** A two-digit day plus the window label (`Sun 15 Nov 00:10 · Weekly`, 170–177 px) wrapped in the 168 px date column; 178 px holds it. `Weekly · Fable` and `100% left` still fit their columns.
- **Easing tokens.** `--ease-out` is now the motion rules' `cubic-bezier(0.23, 1, 0.32, 1)` (visually the same as `.22, 1, .36, 1`), and the branch draw uses the rules' `--ease-in-out` instead of the hand-rolled `--ease-draw`; the rules forbid hand-rolled curves.
- **The panel is 400 × 690 CSS px, not window px.** WebKitGTK renders CSS px at the desktop's text scale (Xft.dpi ÷ 96); this machine runs GNOME at 1.3, so the window is 520 × up to 897 px and the composition is unchanged.
- **Tray click.** Measured on this machine (GNOME Shell 46, ubuntu-appindicators 58): left and right click both open the menu, whatever `ItemIsMenu` says; middle click toggles the panel. The spec's fallback applies: `Open Nagi` is the first item.
- **Never reached / not paired / unsupported:** the hero keeps `Can't reach T3 Code · tried {HH:mm}`; the explanatory sentence sits below the line where rows would be, at 15 / 500 `--secondary`, because at 13 px it wrapped to three lines in the hero's right column. Unsupported reads `Can't read T3 Code` / `This version of T3 Code isn't supported yet.`
- **`asks you · {d}`** counts from the row's last activity: the contract carries no request time, and a new request moves `updatedAt`.
- **A provider that couldn't be checked** prints the provider (`Codex`), not `Codex 1`: an unavailable outcome carries no account labels.
- **Omitted rows and skipped limit windows** print one plain line each (`2 threads couldn't be read.`, `Some limit windows couldn't be read.`), because the contract requires them to be visible.

Fable's sign-off fixes, 13 Nov 2026 (yes-with-fixes):
- **Tray label** marks follow a middle dot (`2 · 0%`, `2 · ?`, `2 · ●`); `2 0%` read as 20% on the real bar.
- **Hyphens.** Inter's `tnum` also swaps the hyphen-minus for a figure-width hyphen (6.9 → 9.7 px at 15 px), so `tabular-nums` on `body` opened gaps in `In-Hand` and `sub-agents`. Tabular figures now apply only to numeric cells (numeral, %, dates, meta, Ended count, fields).
- **Queued, preparing and starting rows** draw a 3.5 px `--secondary` ring, so the solid title dots equal the running count.
- **An empty window** prints `empty` (15 / 640 `--title`) and `until {date}`; no colour.
- **Strokes.** `--stroke` night `#9486a3` (5.39:1 on `--bg`, 4.99 on `--hover`), day `#6b6280` (5.04 / 4.58); trunk, branches and limit and Ended rings 2 px. The silence stroke is 3 px; still hidden under a third.
- **Cut:** the `Linux` header label, project start times, the thread/sub-agent split on the collapsed Ended line (it opens the expanded list), and seconds in the hero: under a minute it reads `all active just now`.
- **Settings sheet:** plain number fields with their units, no stepper arrows (↑/↓ and Shift still step); focus is a neutral ring, `--focus` = `--secondary`, in place of violet across the panel.
- **Expanded Ended:** project groups take the project-heading style, failed and stopped threads the row style at the depth-1 indent; expanding never scrolls the running rows away, and an open list never folds the completed parents.

Judges' round 1, 13 Nov 2026:
- **Can't reach Nagi.** If the reader stops answering after a good read, the count greys, the hero reads `Can't reach Nagi` / `tried {HH:mm} · list from {HH:mm}` / `limits from {HH:mm}`, rows read `last seen {HH:mm}`, and no live words or alarms remain. If only `/api/limits` fails, each retained limit adds `as of {HH:mm}`.
- **The sheet opens and closes instantly from the keyboard, Return, Esc and the tray**; only a pointer click on the gear, Cancel or the scrim keeps the 240 / 190 ms transition.
- **No node entrance.** New-branch nodes stay visible while their branch draws (no scale(0), no spring); the crossed row's ×1.6 settles on `--ease-out` with no overshoot.
- **`empty` everywhere:** the tray mark is `凪 3 · empty`, matching the panel.
- **Limit lines all read name, % left, date.** An account with several windows heads its own lines, and each window, lowest first, is a sub-row with `left`. Costs one 22 px line for Claude.
- **Jumps keep context.** The hero's `1 stuck` / `1 asks you` scrolls so the row's project heading sits 10 px under the rose line (the gap the list has at rest); expanding Ended does the same for its line; scrolling comes to rest on line starts (proximity snap, 10 px padding). The trunk continues through the expanded list with a small ring at each project.
- **Context parents recede:** 500 weight, `--title-context` (night `#e2dbe9` 13.52:1, day `#2b2432` 13.25:1; ≥12:1 on hover), 3 / 5 px padding.
- **The GTK window is rounded** (12 px) with a soft shadow; see the handback for how.
- **The Ended project list balances its two lines** (`text-wrap: balance`), so no word is orphaned.

Judges' round 2, 13 Nov 2026:
- **Not set up is not a failure.** The hero reads `T3 Code not set up` at 15 / 500 `--secondary`, with no attempt time, over `T3 Code isn't connected on this computer.` The tray shows `凪 ·`: no count, no dash. `Can't reach T3 Code · tried {HH:mm}` stays for never-read, and `–` for every real failure.
- **No slab.** With no count (never read, not set up, unsupported, first check) the numeral slot is a quiet `—` at 20 / 420 `--secondary`; `Checking T3 Code…` is calm too.
- **A failed limits read** prints one line under the table, `couldn't refresh · tried {HH:mm} · as of {HH:mm}`, kept on one line; a last-known source's `as of {HH:mm}` stamp never breaks mid-phrase.
- **Expanded Ended:** each failed or stopped thread hangs from its project's stem on an Ended ring, never a bare indent; the geometry sits above row hover fills so no node vanishes on hover.
- **Open motion:** crossed titles no longer flash rose (rose means `asks you`); only the node settles from ×1.6, and the travelling line fades up from 45% so it never outweighs the rows.

Code review (PR #2), 13 Nov 2026:
- **Each limits account keeps its own truth.** A failed account keeps its line, under its stable label, as `as of {HH:mm}` (its own last-known windows) or `couldn't check · tried {HH:mm}`; the provider warns `account_unavailable` (contract, additive).
- **`empty` needs fresh evidence.** A retained 0 prints `0% left` with its as-of stamp and no filled node; the tray drops the mark and its tooltip adds `limits as of {HH:mm}`.
- **Reset windows never show.** Windows are filtered against now on every render; an account with none left reads `couldn't check`.
- **Partial reads never claim `Nothing ran`:** with omitted threads the line reads `Activity in the last {h} h couldn't be fully read.`
- **Cyclic lineage** rejects the snapshot (last known, reason `cyclic_lineage`).
- **The shadow margin passes clicks through** to the desktop (GTK input shape on the visible panel; without cairo's GI bridge the whole window keeps taking clicks).


Owner requests, 13 Nov 2026:
- **T3's own project icon** sits on the trunk in place of each project's node (running headings and expanded Ended headings): 20 px, 25% radius over an opaque `--bg` base, aria-hidden, with T3's precedence (monogram, emoji or lucide override, then T3's favicon, then T3's derived monogram and colour, ported exactly). The monogram uses Inter bold, not T3's mono, because the bar forbids mono under 13 px; its letters render at about 10.3 px. Colours are T3's Tailwind `-400` at night and `-600` by day.
- **Provider brand colour** on the model word (`--pv-*`, ≥7:1 on `--bg` and `--hover`) and on the node (`--pv-*-node`, ≥3:1), keyed by the T3 driver: claudeAgent terracotta, codex green, antigravity (Gemini) blue; Grok and unknown stay neutral. Nodes keep their state shape; `asks you` keeps its rose node. Titles, trunk, branches and limits stay neutral: an account name is title-level text (12:1), and no brand hue reaches 12:1 at night without washing out.
- **Silence moves from amber to yellow** (`--amber` `#e6c84a` / `#7d6800`, `--amber-text` `#ecd27a` / `#594a00`), so a stuck Claude row's `silent 17 m` and stroke read apart from its terracotta `Opus` and node in both themes.

Mac shell, 13 Nov 2026 (owner: "it's too big relative to everything"):
- **Mac density.** The Linux floors assume GNOME's 1.3× text scale. On the Mac the same 400 × 320–690 CSS px layout is shown at **pageZoom 0.85**, by real relayout (never a transform scale), so the panel is **340 pt** wide and **272–587 pt** tall, fitted to the content. Titles, account names and percentages render at **12.75 pt** (menu text), meta, dates and limit labels at **11 pt**; strokes scale with them (2 px → 1.7 pt).
- **Hero numeral on the Mac** is 44 CSS px (**37.4 pt**) with its word at 16 CSS px (13.6 pt), through `:root[data-shell="mac"]`, which only the Mac app sets. Linux is unchanged.
- **Corner radius** 10 pt on the Mac panel. Crispness was measured, not assumed: the owner's screenshots show Nagi's glyph edges as sharp as T3 Code's text next to it (same edge-transition widths at 2×). The coarse look came from size and weight (15 px semibold in a 400 pt panel), which this density fixes.

Sources, phase 1 (13 Nov 2026):
- **One source looks exactly like before.** The glance now reads `/api/sources/v1/glance`; with one source it renders through the unchanged single-glance path (live before/after differs only in a ticking `s ago`).
- **Several sources** add a quiet harness heading (13 / 600 `--secondary`, its monogram on the trunk) and, when there is more than one connection, a computer label (13 / 500 `--secondary`, a ring on the trunk). Each source keeps its own truth line, projects and Ended line; the hero sums fresh source-local counts only and says `{k} of {n} sources can't be read right now` when some can't. Limits stay source-qualified under a `T3 Code · {label}` line (13 / 600).
- **Nothing connected yet** is calm (`Nothing connected yet`, a `Set up Nagi` button) and opens the setup by itself once.
- **Setup and Settings → Sources** are macOS sheets in the existing idiom: four steps (which apps, where, connect, done), plain-word errors with the next step, no token, address or path ever shown. Keyboard paths open, step and close on the next frame; a pointer open keeps the 240 / 190 ms sheet. Coming-soon apps read `Coming soon` as plain text, not a pill. The setup script loads on demand, so the everyday panel stays within its JS budget.
