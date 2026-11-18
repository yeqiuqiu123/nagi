# Nagi v3 creative direction

Fable 5.2, creative director and builder, 18 Nov 2026. The owner asked for a full rethink, taken end to end without checkpoints. Mid-run they added a designer friend's critique of the shipped panel ("too many text", "this shouldn't be text", "urs has no design at all", a sketch of ring gauges) and lifted the old bans on rings, gauges, charts and bars. This file supersedes the direction in `design/art-direction-spec.md` for v3.

## Thesis

**Read the instruments, not the log.**

凪 means the calm at sea. The shipped panel is a ship's log: every fact written out as a sentence, one under another. v3 is the bridge of the same ship: a row of dials for what's left, a watch list for who is working, and words only where a name or an exception needs them.

Three rules follow from it.

1. **A quantity is drawn.** Percent left, time left in the window, silence against the stuck threshold: each is an arc or a stroke first and a number second.
2. **A name is written.** Agent titles, project names and account names stay text, at full size, never truncated. They are the content.
3. **An exception speaks.** `asks you`, `silent 17m`, `couldn't check`, `empty` are the only status words on the glance. Everything that is fine is silent.

## The 2-second answer

Open the panel and, without reading a sentence:

- **Am I about to hit a limit?** The dials are sorted lowest first. A short arc, a yellow arc or the word `empty` is in the top-left corner of the panel or it is nowhere.
- **Will it last until it resets?** Each dial carries a tick for how much of the window's time is left. Arc past the tick: it will last. Arc short of the tick: it is being used faster than the window.
- **Who is working, and does anyone need me?** The header says `3 running` and, only if true, `1 asks you` in rose or `1 stuck` in yellow. The row that needs you is the first row of the list, washed in rose.

## Audit of the shipped panel (fixtures, 400 px, both themes)

Captured with `tests/glance_preview.py` and Playwright WebKit before any change.

| What I saw | Why it fails the glance |
|---|---|
| Two connected sources print **nine limit lines plus two source headings**: about 310 px, 45% of the panel, before the count. | The owner's friend is right: a table of `name / % left / date` is the slowest way to show five percentages. |
| The same facts repeat as words on every line: `left`, `Weekly`, `today`, full dates with year-less month names. | Every line costs a read. Nothing can be compared at a glance. |
| Three levels of headings below the line (`T3 Code`, `Computer 2`, project) and a status sentence per unread or idle source (`Nothing seen from Codex yet. Nagi sees a session once it does something after you connected.`). | A source that has nothing to say takes three lines to say so. |
| Each agent takes two lines even when its title is short; the second line reads `Opus · 6 m · just now`. | `just now` is the normal state, printed on every row. The width to the right of short titles is empty. |
| A completed parent takes two lines (`Opus · completed`). | Context costs as much as content. |
| The 56 px `3` repeats the number the owner just clicked in the tray. | The largest thing in the panel is the one fact they already have. |
| The setup sheet lists ten apps, six of them `Coming soon`, each with a sentence; capabilities read as one wrapped sentence. | The first screen a new user sees is a wall of text. |
| What works and stays: the lineage branches, the silence stroke, provider colour on the model, `empty` instead of `0%`, the calm violet-ink palette, Inter with tabular figures, the sheet idiom. | The owner picked these; they are not the problem. |

## What v3 refuses

- **A tile board.** Dials sit on the panel's own surface, in one band. No cards, no borders around a gauge, no glass, no shadows inside the panel. Mizu already ships the tile board; the owner rejected that look once.
- **Colour as decoration.** Provider hue marks whose quota or model it is. Yellow means running low (quota or patience). Rose means it needs you. Nothing else is coloured.
- **A drawn guess.** A failed read is a dashed ring with `?` and the time it tried. It never draws an arc. An empty window draws no arc and says `empty`. A window Nagi can't time (kind `other`) draws no tick.
- **Averaging.** One dial per account window. Two sources that both report `Codex 1` stay two dials with two source chips: the API has no proof they are the same account (`design/sources-api.md`, "T3 overlap and alerts").
- **Sentences for normal.** No `just now`, no `all active`, no `left`, no `running` on a row, no per-source "nothing seen" paragraph.
- **Motion for its own sake.** One orchestrated moment: on an open where something changed since the last look, each arc sweeps from where it was to where it is. Everything else changes on the next frame.
- **Truncation.** Titles wrap. Type never drops below the floors in `design/v3/project-bar.md`.

## Reference ladder

Craft anchors, looked at for how they solve the same job, not copied.

| Reference | What I take | What I refuse |
|---|---|---|
| Apple Batteries widget | A row of rings, one per device, lowest state obvious, percent beside the ring's meaning. | Device icons inside the ring: the number goes there. |
| Apple Weather, hourly strip | Small repeated columns: a glyph, a value, a time under it. Absolute times. | Horizontal scrolling for essential facts. |
| Apple Reminders and Mail lists | Title left and wrapping, one quiet right-aligned column of metadata. | Swipe actions: Nagi is read-only. |
| iStat Menus (`references/istat-menus`) | Tabular numerals, right-aligned; density without boxes. | Rainbow gauges. |
| Mizu (`references/mizu`) | It proves rings read fast in a menu-bar panel. | Its tile grid, sparklines, toggles and counts in place of names. |
| Linear (`references/linear`) | Children hang from a drawn branch. | Nothing. |
| 21st.dev "Rate Limit Meter", Arc "Gauge" (collectui) | Pairing what's left with the reset and the burn rate in one mark. | React and shadcn: the panel stays dependency-free. |

Mobbin was wanted for menu-bar and widget flows; its MCP needs sign-in and was unavailable in this run.

## Identity kept

- **Palette:** the violet-ink night and lavender-paper day already measured in `web/glance-v2.css`, with rose and yellow. The website is built on the same tokens. New tokens only for the dial track and the row washes.
- **Type:** Inter (variable, optical size) for everything, tabular figures in every number, the Noto Serif 凪 as the one mark. No second face: the instruments carry the personality. I looked at a display numeral (Fontshare, Typewolf lists); at 15 px inside a 52 px ring a second face is noise, and GNOME's own UI face is Inter-based.
- **Voice:** dates are absolute (`Fri 12:56`), durations are compact (`3h 29m`), exceptions are plain (`couldn't check`, `asks you`, `empty`).

## Seeds for the five concepts

1. **Soundings.** A band of dials, then a watch list with a status column.
2. **Tide Table.** One horizontal time axis with now in the middle: how long each agent has run to the left, how long until each limit resets to the right.
3. **Orbit.** One large radial figure: every window a concentric ring around the count.
4. **Still Water.** Only what needs you, large; everything else one line each behind a disclosure.
5. **Ledger.** One list, one row anatomy for limits and agents alike: name, meter, value.

The board is `design/v3/concepts/index.html`; the ranking and pick are in `design/v3/selection.md`.
