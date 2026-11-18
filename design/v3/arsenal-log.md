# Nagi v3 arsenal log

What was pulled from the arsenal for the redesign, what came of it, and what was left on the shelf. Everything that shipped is dependency-free JS, CSS and SVG: the panel has no React and no build step, so React components were read for their ideas and re-drawn by hand.

## Ported into the panel

| From | What I took | Where it lives |
|---|---|---|
| **Arc UI `gauge`** (collectui-arc, free) | Its rules, not its code: fill once with no overshoot, then spring to new values; name the state in words so it never rests on colour; reduced motion lands on the value at once. | `web/glance-motion.js` (`sweepDials`), `empty` / `couldn't check` / yellow-at-alert-level in `web/glance-model.js` |
| **Motion+ CSS spring generator** (collectui-motion-plus `generate-css-easing`) | A critically damped spring, 0.45 s perceptual, as a CSS `linear()` curve. Critically damped because an arc must never overshoot and claim more quota than was read. | `SPRING` in `web/glance-motion.js` |
| **beUI `background-agents-list` and `agent-team-tree`** (collectui-beui) | Each running agent wears a small ring that fills, and a run that needs a decision changes colour. Re-thought for Nagi's data: the node is a disc that **drains with silence** toward the stuck threshold. | Node drawing in `drawPast()`, `web/glance-v2.js`; `.n-rim`, `.n-wedge` in `web/glance-v2.css` |
| **affectUI `running-now`** (collectui-affectui, Pro, description only) | "One quiet pill: 3 running · 2 need you." Confirmed the header as one line of count plus only what needs you. Source not read or reconstructed. | Header in `renderStatus()` |
| **21st.dev `Rate Limit Meter`** and **ReUI `chart-12`** ("pace bead") | Pair what's left with the reset and the burn rate in one mark. Became the tick: time left in the window, on the same ring as quota left. | `timeLeft()` in the model, `.tick` on each dial |
| **The friend's sketch** (owner's attachment) | Ring per window, percent in the centre, source chips under it, a dashed ring with `?` for a failed read. | The dial band |
| **Stitch** (project "Nagi v3 glance variants", one generated screen) | Asked it for the same brief to see where a second hand would go. It agreed on the composition and put the source chips **under** each dial, which is what fixed the one-row fit. | `.chips` under `.acct` |
| **Lucide 1.72.0** (ISC, already licensed in `web/lucide-LICENSE.txt`) | Five glyphs for empty and source states: `waves` (凪 is calm water), `hourglass`, `plug`, `unplug`, `circle-question-mark`. | `GLYPHS` in `web/project-icons.js`, drawn at a 1.75 stroke |
| **macOS System Settings** (owner's taste anchor) | Grouped rows, one decision per row, a switch at the row's end. | Settings sheet and setup step 1 |

## Used as process, not as parts

- **product-engineering**: the route (audit, direction, five concepts, selection, bar, build, verify).
- **frontend-design**: the plan-then-critique passes; its list of generated-page tells (tracked capitals, a hero number with a gradient, identical rounded cards) is in the bar's don'ts.
- **interface-design** guide: status as colour plus shape plus word; undo over confirm (Disconnect keeps its confirm: it changes another app's settings); density values for rows.
- **accessibility** guide: names, roles and states on every control; the keyboard pass in `design/v3/harness/check.mjs`.
- **motion** skill and best-practices: CSS and the Web Animations API over a library for a static panel; animate only what changed.
- **web-design-guidelines** (Vercel's list, fetched fresh): checked the panel against it. Held: `:focus-visible` rings, buttons for actions and links for navigation, labelled icon-only buttons, hidden decorative SVG, a `role="status"` header, tabular numerals, `…` not `...`, a label and its switch as one target. Two deliberate departures: headings stay in sentence case (the house voice), and the dial sweep animates `stroke-dasharray`, not a transform, because the arc's length is the value.
- **Playwright (WebKit)**: every screenshot, the contrast measurements and the keyboard checks.

## Looked at and left

| What | Why not |
|---|---|
| **Arc `usage-meter`, BoardUI `meter` / `progress`** | Bars. The Ledger concept tried them; one line per window is the layout the critique rejected. |
| **Arc `activity-rings` (Pro), ReUI `chart-7`** (concentric rings) | The Orbit concept. Past four rings it stops reading and it can't tell a failed read from an empty window. |
| **affectUI `agent-crew`, `agent-queue`, `agent-inbox`** | Cards per agent with Approve, Retry and Pause. Nagi is read-only, and cards are the widget look the owner rejected. |
| **Aura catalog** (searched "menu bar widget usage rings gauge") | Returned dashboards and tile boards: the opposite of the brief. |
| **ThreeUI** | 3D scenes. Nothing in a 400 px read-only glance wants one. |
| **shadcn, shadcn-studio, shadcn-space, shadcnuikit, ReUI blocks** | React and Tailwind blocks that need a `components.json` and a build. Their radial charts were read for ideas only. |
| **Hugeicons** | A fine family, but its Pro snapshot is licensed to this workspace and Nagi is a public MIT repo. Lucide was already vendored with its licence, so the five glyphs came from there. |
| **Fontshare, Typewolf** | Considered a display numeral for the dials. At 15 px inside a 50 px ring a second face is noise, GNOME's own UI face is Inter-based, and the Mac shows the panel at 0.85. Inter stays, with tabular figures and the optical-size axis for the count. |
| **GSAP skills** | The two moving things are one `animate()` call each. |
| **Mobbin** | Wanted for menu-bar and widget flows. Its MCP needs sign-in and was unavailable in this run. |
| **Figma** | No Figma file exists for Nagi; the board and the panel are code. |
| **Higgsfield, image generation** | No imagery in the panel, and no spending was authorised. |
| **chrome-devtools MCP** | Failed to connect in this session; Playwright WebKit covered it, and is closer to the WebKitGTK and WKWebView the panel ships in. |

## Stitch variant, for the record

Stitch produced the same order (header, dials, list, ended, chips). It differed where I disagree: tracked capital labels, 11 to 12 px grey captions, a green and red outcome bar, bordered pill chips in the footer. Those break the floors or the colour grammar and were not taken. The project stays private in Stitch; nothing from it is loaded by the panel.
