# Nagi v3 concept selection

Fable 5.2, 18 Nov 2026. Board: `design/v3/concepts/index.html` (open it in a browser; night and day at 400 px). The owner asked for this run without checkpoints, so the pick is mine and the reasons are here. Their rejection still overrides it.

**Pick: Soundings, with two parts of Ledger folded in.** Rank: Soundings, Ledger, Tide Table, Orbit, Still Water.

## How they were judged

Four questions, in this order.

1. **Truth.** Can it show a failed read, an empty window, a dated value and five separate windows without merging or guessing?
2. **The 2-second glance.** Lowest limit and whether it lasts; who is running; who needs me.
3. **The critique.** Does it replace sentences with something drawn, and use the width?
4. **Taste.** Apple-grade and calm; not a widget board, not a dashboard.

| | Truth | Glance | Less text | Taste | Fits 690 px tonight |
|---|---|---|---|---|---|
| **1. Soundings** | Yes: dashed ring, `empty`, grey dated arc, one ring per window | Yes | Yes: 9 limit lines become 1 row | Yes | Yes, about 640 px |
| **5. Ledger** | Yes | Yes | No: still a line per window | Yes, but plain | Yes |
| **2. Tide Table** | Partly: 5 h and 7 d on one scale misleads | Slow: needs the axis read | Yes | Original, but hard | Yes |
| **3. Orbit** | No: failed and empty look alike | Limits only | No: the legend is the table | Derivative of Activity rings | No |
| **4. Still Water** | No: "lowest 9%" hides the other windows | Exceptions only | Yes | Cards drift to the widget look | Yes |

## Per concept

1. **Soundings: build it.**
   - **Strength:** the ring with a time tick answers two questions in one mark: how much is left, and whether it lasts until the reset. Lowest-first order puts the problem in the top-left corner. The status column on agent rows uses the empty width and stays grey unless something needs you.
   - **Weakness:** a setup with six or more windows needs a second row of dials (about 109 px). Accepted: it is still shorter than the table it replaces, and nothing is hidden behind a scroll.
   - **Kept honest by:** exact dates one click away on every dial, and in every accessible name.
2. **Ledger: no, but take two parts.**
   - **Take:** the right-aligned value column, and the idea of a time tick on a meter.
   - **Why not:** one line per window is the layout the critique rejected.
3. **Tide Table: no.**
   - **Why:** titles get half the width and would truncate. Mixed window lengths have no honest shared scale. Lineage has no place.
   - **Keep:** nothing in the panel. The idea that rose marks "now" survives only as "rose marks what needs you now".
4. **Orbit: no.**
   - **Why:** it spends 240 px on a figure that still needs a legend, and it cannot tell a failed read from an empty window.
5. **Still Water: no.**
   - **Why:** it hides agent names behind a click, the failure the first project bar was written to beat, and it summarises windows that must stay separate.
   - **Keep:** its promotion rule. In the chosen concept, the row that asks you sorts to the top of the list.

## What changes from the mock-up when built

- **A source chip sits beside an account name only when two sources report the same provider.** Otherwise the source is in the dial's detail and its accessible name. This keeps most captions to a name.
- **The lineage branches are drawn from the real parent node,** as today; the mock-up approximates them with CSS.
- **Selecting a dial opens that account's exact lines in place** (window, percent left, full reset date, when it was checked, which app read it). The mock-up does not show this state; `design/v3/shots/` does.
