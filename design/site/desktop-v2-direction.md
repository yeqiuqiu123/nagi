# Desktop v2 direction (Fable 5.2, creative call 6, 13 Nov 2026)

Answers `desktop-v2-brief.md`. Applies at 961 px and wider. **Phone CSS is not touched.**

**The direction in one line: the tree reaches right.** The trunk stays on the panel's rail. Its branches now come in two lengths: a short one to the left column, a long one across to the right column. One band runs the full width.

> **Warning: the page lands at 2,000 px, not 1,540.** Today's page is 3,078 px at 1440 with the new copy (the saved screens show 2,921, from before it). The opening is 784 px of that and is fixed by the panel's reserved slot. Everything below it falls from 2,294 px to 1,216 px. **Scrolling at 1440×900 halves, from 2,178 px to 1,100 px.** Halving the whole page would mean cutting a section or the panel's slot, and I won't.

A working prototype is in `design/site/concepts/desktop-v2/` (see the last section). Every number here was measured on it.

## 1. Composition at 1440

One character is about 16 px across; the left-hand numbers are page y in px.

```
x     128   186         418         649         881         1112        1312
      edge  col 1       col 2       col 3       col 4       col 5       edge
   0  凪 nagi                                                  Source on GitHub
 100  caption · Pause               lede
 140  ┌───────────────────────┐
      │ limits                │     Am I about to hit my limits?
      │ 3 running             │     one answer line
 359 ═╪═●═════════════════════╪═════ rose now line, the full viewport ═════════════
      │ agents                │     What are my agents
      │                       │     doing right now?
      │                       │     one answer line
      │                       │     ● git clone … && ./install.sh
      │ 15 ended              │       Copy
 729  └─┬─────────────────────┘
 784    │   (the panel's reserved slot ends)
 850    ├─● When it's closed, it's just a number.
        │   intro, two lines (cols 1–3)                 alert note (cols 4–5)
 980    │   凪 3        凪 3 · ?     凪 3 · ●     凪 3 · empty  凪 –
        │   meaning     meaning      meaning      meaning       meaning
1067    │
1137    ├───────────────────────────────────────────◦ It stays on your computer.
1193    ├─○ It only says what it knows.                three short paragraphs
        │   panel string     when · instead of
        │   panel string     when · instead of
        │   panel string     when · instead of
1460    │   When it can't see, it says so.
1514    ├───────────────────────────────────────────○ What it reads today.
1570    └─● Install Nagi                             ├─● T3 Code      how
            requirements, two lines                  ├─● Claude Code  how
            git clone … && ./install.sh              ├─● Codex        how
            Copy                                     └─◦ Cursor       in beta
            what happens next · fine print             Coming soon … Write an adapter
1937        凪 nagi means a calm sea.                Source on GitHub · MIT licence
2000
```

### The grid
**One grid for the whole page:** a 58 px rail gutter, then five equal columns with 32 px between them, inside the existing 1,184 px content box.
- **CSS:** `main { display: grid; grid-template-columns: 26px repeat(5, minmax(0, 1fr)); column-gap: 32px; align-items: start; }`. No wrapper and no reordering are needed.
- **At 1440** each column is 199.6 px, starting at x 186, 418, 649, 881 and 1,112.
- **The opening's copy column moves onto column 3** (x 649, was 616): `.opening { column-gap: max(88px, calc((100% - 186px) * 0.4 - 278px)); }`. The gap to the panel grows from 88 to 121 px. Nothing else in the opening changes.
- **Header and footer** keep the full content width, so their right edge is column 5's right edge.

### Where each section sits
| Section | Columns | Rows | Top at 1440 | Height |
|---|---|---|---|---|
| Opening | all | 1 | 100 | 684 |
| Tray legend | 1–5 | 2, `margin-top: 48px` | 832 | 235 |
| Privacy | 4–5 | 3–4, `margin-top: 52px` | 1,119 | 249 |
| Honesty | 1–3 | 4 | 1,175 | 285 |
| Sources | 4–5 | 5–6, `margin-top: 36px` | 1,496 | 290 |
| Install | 1–3 | 6 | 1,552 | 321 |
| Footer | all | `margin-top: 64px`, `padding-bottom: 40px` | 1,937 | 63 |

`grid-template-rows: auto auto 108px auto 92px auto`. Rows 3 and 5 are the fixed steps that make each pair stagger.

**Inside the tray band** (`display: grid; grid-template-columns: subgrid`):
- The heading spans all five columns.
- The intro takes columns 1–3 and the alert note takes columns 4–5, on the same row.
- The legend is five cells, one per column: readout on top, meaning under it.

**Reading order is the DOM order:** tray, privacy, honesty, sources, install. In each pair the right section sits 56 px higher, so it reads first.

### Why the right column leads
**A branch never crosses text.** A long branch has to pass through the left column, so it travels in the gap above the left section's heading. That puts each right heading 56 px above its left partner. It also means the last branch on the trunk is a short one, to Install.

Measured clearances, to hold at every width:
- **Long branch to Privacy (y 1,137):** 70 px under the legend, 38 px above the Honesty heading.
- **Long branch to Sources (y 1,514):** 54 px under Honesty's last line, 38 px above the Install heading.
- **Floor:** 32 px on both sides of any branch.

### Routing
- **Trunk:** unchanged. It leaves the panel's rail (x 150) under its last ring and ends 10 px above the lowest node. Take the lowest node by y, not the last in the DOM.
- **Branches:** the same path as today, `M tx,y-10 Q tx,y tx+10,y H nodeX-r-1`, one 10 px elbow each. Node x is still 16 px left of the heading, so the long branches come for free once the headings move. At 1440 the nodes are at x 170 (left) and x 865 (right).
- **Sources' own rail:** from the bottom of its parent ring straight down to 10 px above the last child. Each child hangs on a 10 px elbow, node 22 px in, text 16 px after the node. These are the panel's own depth-step numbers.
- **The now line:** untouched. It's still the only full-width horizontal and the only rose stroke.

### 961 to 1199
**Same composition, same grid, fluid.** Checked at 980, 1024 and 1100.
- **Columns shrink** to 136 px at 961. The legend's meanings wrap to four lines and the right headings to two. Height is 2,074 at 1200, 2,173 at 1024 and 2,222 at 980.
- **The copy column keeps its 88 px gap,** so below 1200 it isn't on column 3. Don't force it.
- **Existing fault, not from this work:** below about 1100 the lede runs to three lines and touches the first question. Fix it in the opening, for example a 19 px lede from 961 to 1099.

### 1600 and wider
**Nothing changes.** The page stays capped at 1,280 px and centred. Only the margins and the rose line get longer. Check 1920 and 2560 against the alignment gate.

## 2. Sticky and scrolling
**Nothing is sticky. Everything scrolls.** My earlier veto on a sticky panel stands, for two reasons:
- **The now line.** A pinned panel either drags a fixed rose line through moving text or detaches the page line from the panel. Both break the one idea.
- **No need.** At 2,000 px the page is 2.2 screens. The panel is out of view for one screenful.

## 3. Node vocabulary
**Each node is one the panel already draws, used for what the panel uses it for.** Copy the fills, strokes and radii from `site/panel/nagi-glance.css`.

| Section | Panel node | Drawn as | Why |
|---|---|---|---|
| Tray legend | `n-running` | Solid `--title`, r 5 | The number in the tray is the count of running agents |
| Privacy | `n-group` | Ring, r 3, `--stroke` 2 px | The panel's ring for a computer: "It stays on your computer." |
| Honesty | `n-limit` | Ring, r 4, `--stroke` 2 px | The ring beside every limit line; the quoted strings are limit and reach readings |
| Sources | `n-parent` | Ring, r 4.5, `--secondary` 1.75 px | A parent with children on its own rail |
| Sources: T3 Code, Claude Code, Codex | `n-running` | Solid `--title`, r 5 | Read today |
| Sources: Cursor | `n-pending` | Ring, r 3.5, `--secondary` 1.75 px | The panel's "starting" ring: beta |
| Install | `n-asks` | Solid `--rose`, r 5 | The page's one "asks you". Unchanged |

- **Coming-soon apps get no node.** Nothing unbuilt is on the tree. They're one fine-print sentence under the list.
- **Source nodes are `--title`, never provider colours.** Those stay inside the panel.
- **The tray readouts and the honesty rows get no nodes.** Sources is the page's only sub-tree.
- **The opening's rose dot beside the command stays** as it is.

## 4. Motion
**No new kind of motion. Nothing scroll-linked.**

| Moment | Change |
|---|---|
| Short branch draw | None: 260 ms, `cubic-bezier(0.77, 0, 0.175, 1)`, once |
| Long branch draw | Same easing, 420 ms, once. Its node appears as the stroke lands, not when it starts |
| Sources' rail | After its parent ring lands: the rail in 260 ms, then each child branch in 260 ms, 90 ms apart, node with branch. The panel's own cadence. Once |
| A pair entering view | Each section still triggers itself. The right one enters first because it's higher. Don't chain them |
| Tray five-up | No motion. The readouts still refresh as text on each story beat |

**Reduced motion:** every stroke and node is drawn at load, as today.

**Layout shift stays 0:** the grid rows are CSS and the strokes are drawn into the existing absolutely positioned SVG.

## 5. Height, and what was cut or merged

| At 1440 | Today | v2 |
|---|---|---|
| Page height | 3,078 | **2,000** (accept 1,960 to 2,040) |
| Below the opening | 2,294 | 1,216 |
| Scrolling on a 900 px screen | 2,178 | **1,100** |

**Nothing is removed. The height comes from regrouping:**
- **Tray legend:** five rows become one five-up row, as the readouts would sit along a menu bar.
- **Privacy beside Honesty, Sources beside Install.** Five stacked sections become one band and two pairs.
- **Spacing:** the 128 px between sections becomes 48 to 108 px. The space now runs sideways too.
- **Sources:** the heading's names move into the list, so it drops from two lines to one. Three paragraphs become four rows and one fine-print sentence.
- **Privacy:** the same words in three short paragraphs.
- **Install:** the requirements sentence trimmed to two lines at 663 px.
- **Footer:** 128 px above it becomes 64.

**Added at no cost in height: low-limit alerts.** One note in the tray band, columns 4–5, beside the intro: 15 px, `--tertiary`. It belongs there because it's the other thing Nagi does while closed. In the DOM it goes after the legend.

**If the owner wants it shorter, cut in this order:**
1. Install's fine print (GTK, WebKitGTK, Swift) moves to the README. Saves 76 px, to about 1,925.
2. Stop there. "When it can't see, it says so." stays.

### Copy constraints for the builder
The prototype's words are stand-ins except where they're today's.
- **Right-column headings: 24 characters or fewer,** to hold one line at 34 px from 1200 up. "Works with T3 Code, Claude Code and Codex today." takes three lines there. The prototype uses "What it reads today." and puts the names in the list.
- **Each source row:** a name at weight 620, then how it's read, in `--secondary`. Two lines at most.
- **The alert note:** three lines at most at 431 px.
- **Type in the bands:** headings 34 px and prose 17 px, unchanged. Readouts 23 px at weight 600 with the 凪 at 24 px. Meanings, honesty answers and source rows 16 px. Notes and fine print 15 px.

### What reaches phones
The CSS at 960 px and below is untouched, but two markup changes are shared:
- **Sources becomes the list with its own rail.** I checked it at 375 and it holds.
- **The alert note** appears as a paragraph after the legend.

The prototype is 4,239 px at 375. Compare that with today's phone page once the copy is final.

## 6. Vetoes
- **Anything sticky or pinned,** and anything scroll-scrubbed.
- **A second vertical rail down the middle.** That's a column divider. The only second rail is Sources' own, 22 px in, the length of its list.
- **Flat pairs:** two headings on one baseline with the right one left without a node. Without its node the right column falls off the tree and the trunk becomes decoration.
- **A branch with two elbows,** or any branch within 32 px of text.
- **A centred trunk with sections alternating either side,** or the panel moved to the right. That's the timeline template.
- **Cards, borders, tints or dividers** on the five-up, the pairs or the source list. Space and the grid carry them.
- **Rose on the `3 · ?` readout** or anywhere new. Rose stays on the now line, the Install nodes and `Copy`.
- **Provider colours, logos or icons** for the sources. No logo wall.
- **Nodes for coming-soon apps.**
- **A third column in the opening,** or a tray readout in the header. The first screen keeps its discipline.
- **Hiding content by breakpoint.** If something goes, it goes at every width.
- **Readouts larger than 24 px.** They're quotes from a menu bar, not a hero numeral.

## 7. Amendments to the project bar
- **Branches, 961 and up:** on the five-column grid as above. The bar's "three sentences at most" and "tray legend first" stand.
- **New gate, routing:** no stroke within 32 px of text; the right section of a pair leads by 56 px; the trunk ends at the Install node at every width.
- **New gate, grid:** from 1200 up, the opening's copy column is on column 3 within 0.5 px.
- **New gate, nodes:** each section's node matches the table in section 3.
- **Height:** 1,960 to 2,040 px at 1440 with final copy.

All existing gates stand: line alignment, strokes, colour, type, truth and motion.

## 8. The prototype
**Throwaway. Don't ship its code.** It proves the proportions and the routing.
- **Files:** `design/site/concepts/desktop-v2/index.html` and `site.js`. It loads the real panel from `site/panel/`.
- **Run it** from the repository root: `python3 -m http.server 8766`, then open `http://127.0.0.1:8766/design/site/concepts/desktop-v2/`.
- **Screens:** `design/site/concepts/desktop-v2/shots/`: 1440 in both themes, the 1440 first screen, and 1024.
- **The `site.js` change is small:** a map from `data-node` to class and radius, Sources' rail, and the trunk ending at the lowest node.
- **Not built in it:** the 420 ms long-branch draw and the staged draw of Sources' rail. Every branch draws in 260 ms and the rail appears at once.
- **Not run on it:** Lighthouse, axe and the alignment gate. Those are the builder's to run on the real page.
