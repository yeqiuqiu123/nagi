# Nagi v3 project bar

Fable 5.2, 18 Nov 2026. Supersedes `design/project-bar.md` for v3. Concept: Soundings (`design/v3/selection.md`). Devices: the Linux tray panel (WebKitGTK, 400 CSS px wide, 320 to 690 high) and the Mac menu-bar panel (the same page at pageZoom 0.85).

**What the owner lifted on 18 Nov:** the bans on rings, gauges, charts and bars for limits. **What they kept:** the truth rules, the readability floors, Apple-grade craft.

## Grammar

One meaning per mark. Nothing else is drawn or coloured.

| Mark | Means |
|---|---|
| Arc on a ring | Percent left in one limit window |
| Tick on a ring | How much of that window's time is left. Arc past the tick: it lasts. |
| Dashed ring with `?` | Nagi couldn't check. Never an arc, never a number. |
| Ring with no arc and the word `empty` | Fresh evidence the window is at zero |
| Grey arc | A value from an earlier check, dated in its second line |
| Solid dot on a row | A running agent, in its provider's colour |
| Hollow ring on a row | Not running: a completed parent, a queued agent, an ended thread |
| Drawn branch | Parent to child |
| A running node that drains | Silence: a full disc has just spoken, a thin wedge is nearly stuck, an empty yellow ring is stuck |
| A washed row | It needs you: rose for `asks you`, yellow for stuck |
| Chip under a dial, on a project, in the rail | Which app read it: `T3`, `CC`, `CX`, `CU`; `T3·2` for a second computer |
| Yellow | Running low: a window at or under the alert level, silence past halfway |
| Rose | It needs you now: `asks you` |
| Provider hue | Whose quota or model: Claude terracotta, Codex green, Gemini blue; others neutral |

## Bar per surface

| Surface | At the bar means | Unacceptable |
|---|---|---|
| **Dials** | Every window is one ring, lowest account first, however many sources read it; percent in the ring; window name and absolute reset time under it; source chips under the group when there are several sources; exact date, check time and sources one click away | A card or border around a dial; an arc for a failed read; the same window drawn twice; two windows in one ring; a tick on a window whose length Nagi doesn't know |
| **Header** | One line: the count and, only when true, `1 asks you` and `1 stuck`. Failures say what and when on a second line | A hero number larger than the dials; a sentence when all is well |
| **Watch list** | Titles in full at 15 px; model and run time in a right-hand column; the row that asks you first, washed in rose, then stuck rows, washed in yellow; children on drawn branches; a completed parent in one line; no source or computer headings | Truncated titles; `just now`; a status word on a healthy row; an indent standing in for a branch |
| **Empty list** | A glyph and two to four words; the sentence is the tooltip and opens beneath on a click or Enter | A paragraph where the list would be |
| **Ended** | One line: count, outcome bar, failed and stopped counts. Expands to projects and the failed or stopped threads only | A history view |
| **Sources rail** | One chip per connected source when there are several: monogram, running count, and words only when it can't be read or has seen nothing yet | A heading and a paragraph per source |
| **Settings and setup** | macOS sheet; one decision per row; coming-soon apps in one line; a pasted link never shown | A wall of disabled rows |
| **Tray** | Unchanged: `凪 3`, `3 · ?`, `3 · ●`, `3 · empty`, `–`, `·` (shared with the Mac through `tests/tray-label-cases.json`) | A glyph that needs the panel to explain it |

## Must beat

1. **The shipped panel on limits and height:** the friend's evening (three sources, the same Codex account read twice, one agent) took the full 690 px and scrolled; in v3 it is 351 px with no scroll, and the account appears once.
2. **Mizu on truth:** every running agent is named; a failed read is never a ring at zero.
3. **The friend's sketch on pace:** the tick shows time left in the window, and the text under the ring is the absolute reset time, so relative and exact are both on the glance.

## Readability floors (measured in the WebKit capture, both themes)

Raised where marked; none lowered.

- **Titles** (agent titles, account names in detail, sheet labels): 15 px, weight 500 or more, line-height 1.3 or more.
- **A headline that recedes on purpose** (`Nothing running`, `T3 Code not set up`, a dated count): 17 px, weight 560 or more, 7:1.
- **Dial numeral:** 15 px, weight 650. The `%` sign 12 px.
- **Secondary** (model, run time, window name, reset time, account captions, state words): 13 px, weight 420 or more.
- **Smallest text anywhere:** 12 px (the `%` sign and the source chips, which are weight 700). No tracked capitals, no mono, no italics.
- **Contrast on `--bg`, on row hover and on the rose wash:** titles 12:1, secondary 7:1, tertiary 4.5:1, state words (rose, yellow, provider) 7:1.
- **Meaningful strokes** (arc, tick, dashed and empty rings, branches, nodes, the outcome bar): 2 px or more (raised from 1.5) at 3:1. The ring's track is scaffold, not meaning: every state it could carry is also a numeral or a word.
- **No weights under 400.** Dim with a tested colour, never opacity.
- **Readable in 2 seconds at arm's length:** the count; any `asks you` or stuck row; the lowest window, its percent and its reset time.
- **Fits without scrolling:** 3 running, 2 completed parents, 5 windows, the ended line and a 3-source rail (609 px measured).
- **Measured, not asserted:** `design/v3/measurements.md` is generated from the running panel by `design/v3/harness/measure.mjs`; it lists nothing below a floor.
- **Pointer targets:** 28 px or more; every interactive thing reachable by Tab in reading order, with a visible focus ring.

## Truth add-ons

- **One ring per window.** Two sources that read the same window (same provider, window name and reset instant, the reader's own alert key) share one ring and both chips; the fresher reading shows, and a dated reading never replaces a fresh one. Never averaged. A different reset instant is a different ring. See `design/v3/backend-requests.md` for the identity the API should carry.
- **`empty` needs fresh evidence.** A retained 0 is a grey `0%` with `as of {HH:mm}`.
- **A failed read prints `couldn't check` and `tried {HH:mm}`** under a dashed ring. Reasons the owner can act on (`sign in again`) print in place of `couldn't check`, with the full sentence in the detail.
- **The reset time is always absolute** on the glance (`20:56`, `Fri 12:56`, `1 Dec`) and complete in the detail (`resets Fri 20 Nov 12:56`).
- **A tick is drawn only for windows of known length** (5 hours, 7 days, a calendar month).
- **A completed parent** stays out of the count and draws a hollow ring.
- **A dated list** (the source can't be reached) draws hollow nodes, no silence strokes, no rose, and says `last seen {HH:mm}`.
- **Totals sum fresh sources only,** and the rail names the ones that couldn't be read.
- **Read-only:** no control on the glance changes anything in an agent app.

## Motion

- **One orchestrated moment:** on an open where a window's percent changed since the last open, its arc sweeps from the old value to the new one (450 ms, critically damped). Gated: not on the first open, not under reduced motion, not when nothing changed.
- **Kept from v2:** new branches draw in spawn order on an open at least 30 minutes after the last.
- **Everything else is instant:** hover, focus, expanding a dial or the ended line, keyboard paths. A pointer open of a sheet keeps its 240 / 190 ms.

## Tells and don'ts

- **Widget drift:** a fill, border or shadow behind a dial; equal rounded cards; glass.
- **Dashboard creep:** sparklines, history, totals across accounts, a second row of statistics.
- **Colour creep:** green for "fine", red for "bad", a hue on a title.
- **Text creeping back:** a label above the dials, `left` after a percent, a sentence under a healthy source.
- **Bigger type bought by truncation.**
