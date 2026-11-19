# Themes, palette and CI: project bar

Fable 5.2, 19 Nov 2026. Adds to `design/v3/project-bar.md`; every floor there still holds, in every theme. Direction: `design/themes/creative-direction.md`.

## Done looks like

| Surface | At the bar | Unacceptable |
|---|---|---|
| **Built-in themes** | Violet, Graphite and Tide, each with a night and a day; Violet's glance is pixel-for-pixel today's. Every theme passes the v3 contrast floors in both appearances, proven by a test over the palette data | A theme where the rose or yellow wash can't be told from the sheet; glass, blur, gradients |
| **Appearance** | System follows the desktop and changes live; Light and Dark hold | A flash of the wrong theme on open |
| **Custom palette** | Accent, Claude, Codex, Gemini and T3 can each be set; what is drawn is always readable in the night and day of the chosen theme, whatever was picked | A colour that can be saved and then can't be read; a status colour in the picker |
| **Guard** | A low-contrast pick is nudged and says so. A provider pick that lands on rose or yellow is refused and says so. A hand-edited settings file gets the same treatment when it is applied | A provider arc that looks like a low limit |
| **Settings** | One Appearance row in the grouped rows; its sheet shows three theme pictures, a segmented appearance control and five colour rows; everything reachable by keyboard | A native colour dialog; a wall of swatches; a sheet that scrolls at 690 px |
| **Persistence** | Saved by the reader in `nagi-settings.json` through a validated `theme` field; survives a restart on Linux and the Mac; an older client that posts without `theme` doesn't reset it | Theme kept only in the page's storage |
| **CI on a row** | Up to two trailing marks, each a link, each with a spoken label; titles keep their 15 px and still wrap | A word on the row; a mark inside the row's own link; a rerun or cancel control |
| **CI in the header** | One segmented ring and a red count when something failed; nothing at all when GitHub is off | A sentence; a row of counters |
| **PRs waiting** | Counted in rose in the header, listed as rows that link out, placed after the projects that need you | A merge or approve button |
| **Ended results** | A strip of marks under the Ended line, one per PR, each a link; opened, each ended agent's PR with its state | A count with no results |
| **Machine load** | One 20 px concentric ring; no GPU means no third arc; exact numbers one press away | A graph, a history, a zero for something that isn't there |
| **Unknowns** | `couldn't check` with the time it tried, as a dashed mark; `not set up` in the rail; off is silent | A green ring, a 0 or an empty list standing in for a failed read |

## Floors added

- **Status colours** (`--green`, `--red`, `--blue`, with the existing rose and yellow): marks 3:1 on the sheet, hover, both washes and the settings surfaces; their words 7:1 on the sheet and hover.
- **Accent:** 3:1 on the sheet, hover, settings sheet and control surface; the ink on it 4.5:1.
- **Custom provider colours:** mark 3:1 and word 7:1 on the sheet and hover, chip 4.5:1 on its own tint, in both appearances of the chosen theme.
- **Marks:** a checks or deployment mark is 16 px with strokes of 2 px, inside a pointer target of at least 24 by 28 px.
- **Nothing below 12 px,** as before.

## The checks that prove it

1. **`node --test tests/*.test.cjs`** includes a theme test that runs every built-in theme, night and day, through every pair in the floors above; runs a spread of awkward custom picks (black, white, mid-grey, pure yellow, pure rose, the brand colours) through the guard and asserts the drawn values clear the floors or the pick is refused; and asserts the stylesheet's fallback tokens equal Violet's.
2. **`python3 -B -m pytest tests -q`** includes the reader's `theme` validation: defaults, a round trip through a restart, every malformed shape refused with nothing written, an older client's post leaving the theme alone, and a legacy file still read.
3. **A CI model test** over fixtures for every outcome in `design/ci-contract.md`: running, passed, failed, cancelled, none, unavailable, last known, not set up, disabled, omitted, a route that answers 404, and a machine with and without a GPU.
4. **In a real browser (Playwright WebKit) at 400 px:** every built-in theme in night and day, one custom palette, the Appearance sheet, and the CI states, saved to `design/themes/shots/`. The lead looks at each one.
5. **`node site/scripts/sync-panel.mjs --check`** passes.

## Tells and don'ts

- **Fluent drift:** a tile per theme with a label inside it, acrylic behind the sheet, a "live" preview that animates.
- **Rainbow drift:** green or red on anything that isn't a check or a deployment; an accent on content.
- **Monitor drift:** a second load ring, a percentage in the header, a sparkline.
- **Log drift:** `CI passed` written on a row; a PR's whole title in the Ended line.
- **Control drift:** anything that changes GitHub.
