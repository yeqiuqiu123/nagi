# Nagi project bar (Fable 5.2, creative call 4 of 5, 13 Nov 2026)

**Brief:** the product agreement (12 Nov) plus the owner's pick: "i like now line and lineage and lull but we should really up visibility and readability". **Device:** Linux tray panel, 400×690, WebKitGTK.

## How the three ideas combine
**One drawing, three jobs.** Now Line leads, Lineage is its geometry, and Lull is a detail.
- **Now Line owns the page.** Limits sit above the rose line as dated lines, the count sits on it, and agents sit below.
- **Lineage owns the vertical strokes.** The axis is the trunk, and each parent forks drawn branches to its children.
- **Lull owns one short horizontal stroke per running row.** It grows from nothing to full row width at the stuck threshold. Under a third it is not drawn.
- **Grammar:** vertical means time and parentage, horizontal means silence, and rose means now or "asks you". Nothing else gets a line or a colour. *(Amended 13 Nov: provider brand colour on the model word and node, at the owner's request. Claude terracotta, Codex green and Gemini blue; Grok and unknown providers stay neutral. Titles, trunk and branches stay neutral, rose stays reserved, and silence moved from amber to yellow so it never reads as Claude.)*

## Bar per surface
| Surface | Principal reference | At the bar means | Exceptional quality | Unacceptable outcomes |
|---|---|---|---|---|
| Panel 400×690 | `mizu/1440-first.png` | Every running agent named with parent, model, run time and silence; every account's window with % and reset date; no scrolling for the 2-second facts | **Arm's-length legibility** (category 1) | Counts replacing titles; tiles, rings, toggles; a ring or 0 for a failed check |
| Tray readout | `istat-menus/1440-first.png` | Count readable at 1×; a mark when anything is stuck, waiting or empty | — | A glyph that needs the panel to explain it |
| Rows and nesting | `linear/1440-first.png` | Title leads, one quieter metadata line, children hang visibly from their parent | **Structure you can read without reading** (category 2) | An indent standing in for the branch; a completed parent counted as running |

**Supporting:** `a24-klaassens` for the count numeral.

## Must beat
1. **Mizu on the glance.** In 2 seconds Nagi names the three agents and their parents where Mizu prints "Agents 2".
2. **Mizu on limits honesty.** Three accounts, five windows, each with a date. Codex 1 at 0% is never averaged with, or hidden behind, Codex 2 at 67%.

## Readability floors (add-on gates, measured in the WebKitGTK capture)
- **Titles:** 15 px, weight 500 or more, line-height 1.3 or more.
- **Secondary** (model, run time, silence, dates, % left): 13 px, weight 400 or more, never below.
- **Smallest text anywhere:** 12 px. No tracked capitals under 13 px. No mono under 13 px.
- **Count numeral:** 44 px or more. Serif only at 20 px and above; sans below.
- **Contrast, both themes:** titles 12:1, secondary 7:1, tertiary and dimmed prefixes 4.5:1.
- **Strokes that carry meaning** (axis, branches, silence rule, now line): 1.5 px or more at 3:1.
- **No weights under 400**; dim with a tested colour, never opacity.
- **Readable in 2 seconds at arm's length:** the running count; any stuck or "asks you" row; the lowest window and its reset date; which project each agent belongs to.
- **Fits without scrolling tonight:** 3 running, their 2 completed parents, 3 account lines and the collapsed ended line.

## Truth add-ons
- **One line per account**, the lowest window first: `Codex 1 · empty · until Mon 16 Nov 21:58`; the tray marks the same window `empty`. Claude's Session, Weekly and Weekly · Fable all print, each as name, % left, date. *(Amended 13 Nov after the call-5 sign-off: an empty window reads `empty` in the panel and the tray, never a bare `0%`.)*
- **A completed parent** prints the word "completed", holds its branches and stays out of the count.
- **"Couldn't check"** appears only on a failed read, with the attempt time.
- **Ended** stays one collapsed line, naming its count and projects.

## Tells and don'ts
- **Three ideas fighting:** a second axis, a bracket beside the branches, or a silence strip on limits.
- **Hairlines:** 1 px branches, 9 px tracked caps, grey-on-grey metadata, italic serif captions.
- **Windows drift:** tiles, cards with borders, acrylic, accent-filled pills, segmented toggles, progress bars for limits.
- **Dashboard creep:** sparklines, history, totals, per-provider charts, more than one hero number.
- **Bigger type bought by truncation.** Titles wrap to two lines; they don't clip to an ellipsis.
- **Status colour everywhere.** Yellow (formerly amber) marks only silence past halfway; provider colour marks only the model word and node.
