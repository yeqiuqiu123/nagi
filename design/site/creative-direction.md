# Nagi website: creative direction (Fable 5.2, creative call 1 of 5, 13 Nov 2026)

Inputs: `design/site/brief.md`, the panel's `project-bar.md` and `art-direction-spec.md`, `design/site/seeds/`, the reference captures. Saved verbatim apart from formatting.

> **Warning.** "Open source" can't be claimed without a licence. Until the owner picks one, every concept says `Source on GitHub · licence coming soon`.

**Lead with concept 1, The Line.** Take it to the slice, with concept 5's table as its honesty section and concept 3's discipline on the first screen. Concept 2 is the fallback if the page-wide line fails at 375 px.

## Thesis
**The site is a glance too.** You look up, get the truth, look away. Every competitor sells power (armies, teams, eight arms); Nagi sells **relief**, and proves it by putting the real instrument on the page and saying only what it says. It will be remembered for **one rose line that leaves the live panel and crosses the page**, and for printing `couldn't check · tried 06:03` where others print 0.

## Held in all five
- **Wordmark:** `凪 nagi` exactly as the panel header (Noto Serif glyph, Inter 620), only scaled.
- **Colour:** panel tokens verbatim, system theme, no toggle. Rose means now or "asks you"; yellow appears only inside the panel.
- **Type:** Inter; headlines in the numeral's cut (opsz 32, 560, −0.03em). One mono on the whole site: the install command, system mono at 15 px.
- **Voice:** the panel's. The two questions are printed verbatim.
- **Motion:** the panel's own engine and nothing scroll-linked. Reduced motion loads `?scene=still`.
- **375 px:** the panel runs at its Mac density (340 px, real relayout), never a scaled image.

## 1. The Line (lead)
- **Problem:** a screenshot beside a headline shows the panel but not its grammar.
- **Idea:** the page is the panel's drawing at page scale. The panel's now line continues, pixel-aligned, across the viewport, and a trunk runs down the left with each section hanging from it as a branch.
- **Refuses:** section cards, icons, a link-bar nav, any filled button.
- **Mood:** a quiet window at night.
- **Identity:** Install is the page's only "asks you", shown as a rose node beside the command with `Copy` as plain text.
- **Motion:** the story scene plays once. The page line arrives with the panel's 700 ms travel, and each branch draws once on entering view (260 ms, never scrubbed).
- **Opening:** above the line, beside the limits table, "Am I about to hit my limits?"; below it, beside the rows, "What are my agents doing right now?". The command and GitHub sit under the second question.
- **Journey:** the questions sit on the parts that answer them, so ten seconds is enough. The first branch is privacy, in three sentences: "No cloud, no account, no telemetry. Nagi reads T3 Code on your computers and talks to nothing else. Read-only: it can't stop, send or approve." The last node is the command again.
- **References:** `linear` (row rhythm), `a24-klaassens` (one numeral), `ghostty` (two actions).

## 2. Two Seconds
- **Problem:** five states make one promise, and a single hero can only show one.
- **Idea:** the live panel is pinned right while six short captions scroll left; each caption cuts the panel to its scene (still, asks, stuck, limits, offline, quiet).
- **Refuses:** leader lines (lines carry meaning), crossfades, device frames.
- **Mood:** an instrument manual.
- **Identity:** captions at title size with the panel's own strings quoted inline.
- **Motion:** scene changes are instant cuts on the next frame, as in the product.
- **Opening:** the panel and "Two questions. Two seconds."
- **Journey:** caption five is the offline state, where trust is earned: last-known values, greyed count, no alarms. The command sits below the sixth.
- **References:** `linear`, `istat-menus` (real readouts as hero, minus the gauges).
- **Risk:** pinned scrollytelling is a known template, and at 375 px it becomes a stack of stills.

## 3. One Object
- **Problem:** the README is dense, so the opposite is one screen.
- **Idea:** one viewport holds the panel, one sentence, the command and GitHub. Everything else is a second plain page, "How Nagi stays private", set as a document.
- **Refuses:** scrolling on the home page, sections, a footer of links.
- **Mood:** a gallery label.
- **Identity:** the sentence is "Nagi shows what your agents are doing and when your limits reset."
- **Motion:** only the story scene.
- **Opening and journey:** the same screen, with a one-line privacy claim under the command linking to the document.
- **References:** `ghostty`, `a24-klaassens`.
- **Risk:** it clears every gate easily but explains privacy least, and it is the most forgettable.

## 4. In Place
- **Problem:** half the product is the tray readout, and no other concept shows it.
- **Idea:** the page is an empty desktop in `--bg`. At top right, at real size, sits `凪 3 · ●`; the panel hangs from it with no animation, and clicking the mark toggles it. Copy sits bottom-left.
- **Refuses:** drawn menu-bar chrome, wallpaper, a MacBook.
- **Mood:** a desk at 2 a.m.
- **Identity:** the tray label is the logo lockup, with marks cycling through `· ?`, `· ●` and `· empty`.
- **Motion:** none beyond the panel.
- **Opening:** mostly empty, with one small mark and "It lives up here."
- **Journey:** the tray legend doubles as the explanation; privacy and install follow as plain paragraphs.
- **References:** `istat-menus` (bar readout), `mizu` (beaten by having no mock-up).
- **Risk:** on a 375 px screen there is no tray, so the conceit collapses.

## 5. Everything It Says
- **Problem:** honesty is a claim until it is specified.
- **Idea:** the page is an index of the panel's whole vocabulary in three columns: what Nagi says, when it says it, and what it never says (`0%`, `Error`, `Resets in 3d`). Focusing a row loads that scene in the panel.
- **Refuses:** adjectives, feature lists, anything not quoted from the code.
- **Mood:** a type specimen.
- **Identity:** catalogue typography, with numbered rows and tabular alignment.
- **Motion:** row focus cuts the scene.
- **Opening:** "Nagi can say 23 things. Here they are." The number must be counted from the copy deck.
- **Journey:** trust is strongest here, the ten-second read weakest. The command is the last row.
- **References:** `creative-reference-library` (index), `grail` (flat confidence).
- **Risk:** it rewards the second visit, not the first.

## Rejected comparison for the board
**`superset` (now Paradev): "Run an Army of Coding Agents".** It fails this brief on every line:
- **Voice:** it promises scale where Nagi promises attention.
- **Hero:** a dot-matrix backdrop, a funding pill and three buttons stand in for a product that is cropped below the fold.
- **Trust:** a cookie banner sits on a page that should say "no telemetry".

Pin `istat-menus` beside it as the nearer trap: the owner loves the app, but its hero is a bento of readouts on a blue gradient.
