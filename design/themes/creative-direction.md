# Themes, palette and CI: direction

Fable 5.2, frontend lead, 19 Nov 2026. Builds on `design/v3/creative-direction.md` ("Read the instruments, not the log") and changes nothing in it except where this file says so. The bar is in `design/themes/project-bar.md`.

The owner asked for two things and then three more: themes with an adjustable palette, CI and deployments in the panel, and then pull requests waiting on them, what each finished agent produced, and one small ring for machine load.

## Thesis

**The paint may change. The signals may not.**

A theme repaints the bridge: the sheet, the ink, the controls, whose colour a provider wears. It never repaints a signal. Rose still means it needs you, yellow still means running low, and the new CI marks say passed, failed and running in the same green, red and blue in every theme and every custom palette. The owner can make Nagi theirs without ever being able to make a warning look calm.

And the new instruments follow the old rule. A CI run, a deployment, a pull request and the machine's load are each one small drawn mark with a link behind it, never a sentence.

## Part 1: three themes

Each has a night and a day and follows System, Light or Dark.

| Theme | What it is | Night | Day | Accent |
|---|---|---|---|---|
| **Violet** | Today's T3-derived panel, untouched on the glance. The default. | violet ink `#18131d` | lavender paper `#f2f0f6` | lavender `#b59cf7` / `#6a45d1` |
| **Graphite** | The neutral greys of macOS itself: System Settings at night, a Finder window by day. For the owner who wants Nagi to look like it came with the Mac. | `#1c1c1e` | `#ececee` | system blue `#409cff` / `#0066d6` |
| **Tide** | Deep water. 凪 is the calm at sea; this is the sea. Blue-green night, sea-mist day. Rose and yellow stand out most here. | `#0f1a1f` | `#eaf2f2` | seafoam `#62d3d8` / `#0a737a` |

**Why not a high-contrast theme.** It was floated. Every built-in theme already holds the v3 floors (titles 12:1, secondary 7:1, marks 3:1), so a fourth "more contrast" skin would be an accessibility setting wearing a theme's name. If it is wanted it belongs to the system's Increase Contrast switch, as a follow-up. **Why not a warm paper theme.** On cream, the yellow wash of a stuck row all but disappears. A theme that hides a warning breaks the thesis.

### Accent: controls, never content

Nagi had no accent; switches and the default button were ink-coloured. It gets one now, used exactly where macOS uses its own: the switch that is on, the default button, the focus ring, the selected theme, text selection. It never colours a title, a dial, a node or a count. The glance's colour grammar is unchanged.

### The custom palette

Five colours can be changed: **Accent**, **Claude**, **Codex**, **Gemini**, **T3**. The owner picks a colour; Nagi keeps its hue and moves its lightness until the mark and the word are readable in both the night and the day of the chosen theme. So a pick is one colour, and what is saved is one colour, but four values are drawn from it (mark and word, night and day), the same way the built-in pairs were tuned by hand.

- **Nudge, not refuse, for contrast.** A pick too dark for night is lightened until its arc clears 3:1 and its word 7:1. The swatch shows the colour Nagi will really draw. One line says it was adjusted, but only when the change is plain to see: a brand orange drawn a shade darker by day says nothing.
- **Refuse, for a signal.** Claude, Codex and Gemini paint arcs and nodes, the same marks that turn yellow when a limit runs low and rose when an agent asks. A pick that lands on yellow or rose is refused with one line saying why: within 0.09 in OKLab of the theme's rose or yellow, or, for yellow, any saturated colour within 20 degrees of its hue, because a yellow stays a yellow however far it is darkened. Accent and T3 never paint those marks and are only held to contrast. Providers are not kept away from the green, red and blue of checks: Codex is green and Gemini is blue by their own brands, and a check is told from a node by its shape and its place on the row.
- **Locked.** Rose, yellow, green, red, blue and the greys are not in the picker and cannot be set through the API.

### Where it lives

Settings gets one more grouped row, **Appearance**, with the current choice as its value and a **Change…** button, the same idiom as Sources → Manage…. It opens the Appearance sheet:

1. **Three theme pictures**, side by side, in the manner of System Settings → Appearance. Each is a small drawing of the panel in that theme, split down the middle, night on the left and day on the right, with a dial arc and two rows drawn in the palette as it will really be. So the pictures are also the proof: every custom colour is seen on every theme in both appearances before it is saved.
2. **System · Light · Dark**, a segmented control.
3. **Colours**, a group of five rows. Each shows its colour as a dot and opens a row of presets and a hex field beneath it, one at a time. No native colour dialog: it would take focus from a tray panel and close it.
4. **Restore defaults**, **Cancel**, **Save**. Choices preview on the live panel behind the sheet and revert on Cancel.

It is saved by the reader in the same private settings file as the other preferences (`theme` in `/api/settings`), so it survives restarts and is the same in the Linux tray panel and the Mac app. A cached copy in the page's own storage paints the right theme on the first frame.

## Part 2: CI, deployments, pull requests, results, load

### The new marks

Circles are checks. Triangles are deployments. Both sit at the trailing edge of a row, where iOS puts an accessory, each one a link to its run on GitHub.

| Mark | Means |
|---|---|
| Green ring with a check | Checks passed |
| Solid green disc with a check | Passed and merged: it landed |
| Solid red disc with a cross | Checks failed |
| Blue arc on a ring | Checks running; the arc is how many have finished |
| Ring with a blue dot | Checks running, and the feed gives no count: no arc is guessed |
| Grey ring with a dash | Cancelled |
| Dashed grey ring with `?` | Couldn't check. Its tooltip gives the time it tried |
| Any of these in grey | A reading from an earlier check |
| Solid green triangle | Deployed |
| Solid red triangle with a bar | Deployment failed |
| Blue outline triangle | Deploying |
| Yellow outline triangle with a dot | Deployment waiting for approval |
| Grey outline triangle | Inactive; dashed when its state is unknown |

No checks draws no mark. A check that passed is the quietest mark and a failure the loudest, so the eye lands on red first.

### On an agent row

Up to two marks at the trailing edge of the row's first line: checks, then deployment. Model and run time move left to make room, as detail text does beside an iOS accessory. The row itself still opens the thread; each mark opens its run or deployment. Nothing is written on the row: the PR number, the count of checks and the environment name are in the mark's tooltip and its spoken label.

### In the header

When the header is full, the words that need you (`2 PRs`, `1 asks you`, `1 stuck`) take their own line under it, right-aligned, and the instruments keep the top line.

One instrument, left of the gear: **a small ring cut into segments**, one per watched branch, red for failed, blue for running, green for passed. A red number beside it when anything failed. All green is one quiet full ring. A deployment appears beside it only when it is in flight, failed or waiting. Pressing either brings the first such row into view.

### Pull requests waiting on you

They join the queue of things blocked on the owner. In the header, `2 PRs` in rose beside `1 asks you`. In the list, one group headed by a pull-request glyph, placed straight after the projects that need you and before the ones that are fine. Each row is the PR's title, with why it waits as one rose word (`review`, `changes`, `merge`), its repository and number beneath, and its checks mark. The row is a link to the PR. There is no merge or approve button and there never will be.

### What finished agents produced

The Ended line keeps its count and outcome bar. Beneath it, a **results strip**: `6 PRs` and then one checks mark per pull request, each a link, the ones that need you first, then failed, running, passed. Solid green is merged. Opened, each project's ended agents that produced a PR are listed with the PR number, one state word (`merged`, `open`, `draft`, `closed`) and the mark. "15 ended" becomes six results you can see the colour of.

### Machine load

One 20 px mark in the header beside the checks ring: **concentric arcs, CPU outside, memory inside it, GPU innermost when there is one**. Ink-coloured, yellow at 90% or more. A machine without a GPU draws two arcs, never a third at zero; a reading that failed is a dashed ring. Pressing it opens the three exact numbers. It has no history, no graph and no per-process list: it is a gauge, not a monitor.

### Honest states

| State | What shows |
|---|---|
| GitHub is switched off (the default) | Nothing on the glance. Settings → Sources has the switch. |
| Switched on but `gh` is missing or signed out | A `GH` chip in the rail with `not set up`; its detail says what to do |
| GitHub couldn't be reached | The header ring is dashed with `?`; the rail says `couldn't check · tried 14:02`; and where the pull requests would be, one line says they couldn't be checked, because a queue that is yours must never read as empty when it is unknown. No row draws a mark that pretends, and the results strip stays out rather than say it a third time |
| The very first read fails | The same: a failure with no earlier reading is kept as a failure, with the time. Only a feed last known to be off or absent stays silent |
| The GitHub switch couldn't be confirmed | The switch rests in the middle, neither on nor off, with `Couldn't check whether this is on · tried 14:02` |
| Only the pull-request or results feed failed | That one place says `couldn't check` with the time |
| One branch couldn't be read | That row's mark alone is the dashed `?` |
| A reading kept from earlier | The same marks in grey, dated in the rail |
| A partial list | Counts carry `+`: `2+ PRs` |
| This reader has no CI or machine routes yet | The marks are absent. Nothing is labelled as zero |

## What this adds to the v3 grammar, and what it refuses

- **Green, red and blue enter the panel** for checks and deployments only. v3 refused "green for fine, red for bad" on agents and limits, and still does: no title, dial, node or count takes these hues, and the Ended outcome bar stays three shapes with no hue. Checks are different in kind: pass and fail are the content, not a decoration on it.
- **Every mark differs by shape as well as hue**, so none rests on colour alone: check, cross, arc, dash, `?`; solid, outline, dashed.
- **No controls.** No rerun, cancel, merge, approve or deploy. Marks are links out.
- **No tile board.** Marks sit on the panel's own surface. The theme pictures are the one place a framed miniature appears, inside a sheet, because that is how macOS shows an appearance.
- **No acrylic, no blur, no gradients** in any theme. Graphite is flat greys, not glass.
- **No system monitor.** One ring.
- **No text creeping back.** A row gains marks, not words.

## Motion

None added. Theme changes are instant. The Appearance sheet opens with the existing sheet transition. Running checks draw a still arc: the panel repaints on its 20-second poll, and a spinner would move for its own sake.
