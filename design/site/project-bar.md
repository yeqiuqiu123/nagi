# Nagi website: project bar (Fable 5.2, creative call 3 of 5, 13 Nov 2026)

**Brief:** `design/site/brief.md` (13 Nov) and concept 1, The Line, with the eight pushes in `concept-selection.md`; owner ruling pending. **Judged at:** 1440×900 and 375×812, light and dark, motion on and reduced. **The embedded panel stays under `design/project-bar.md`;** the site never restyles, scales or patches it.

## Project categories
1. **One drawing.** Reference `a24-klaassens/1440-first.png`: one object and one numeral hold a viewport. Here: cover every word and the first screen is still Nagi, because the page line, trunk, branches and nodes are the panel's own strokes, continued.
2. **Ten-second truth.** Reference `ghostty/1440-first.png`: one object, one sentence, two actions. Here: after ten seconds a stranger can say what Nagi is, name both questions and find the command, and every string beside the panel is the string the panel prints.

## Bar per surface
| Surface | Principal reference | At the bar means | Unacceptable |
|---|---|---|---|
| First screen, 1440 | `ghostty/1440-first.png` | Lede, two questions with one answer line each, command, GitHub, panel, then space. Limits question above the line, agents question below | A third action, a nav bar, a badge |
| First screen, 375 | `linear/390-first.png` | Both questions above the panel; panel live at 340 px, its first line inside the first viewport; trunk leaves the panel's own rail | A cropped or scaled panel; horizontal scroll |
| Branches | `linear/1440-first.png` | Heading leads, three sentences at most, hung from the trunk by a drawn branch; tray legend first | Cards; a hairline table; eight "Coming soon" rows |
| Install | `ghostty/1440-first.png` | The command shown is the command copied; it breaks only at `&&`; `Copy` confirms in words, to screen readers too | A mid-token wrap; a filled button; `./install.sh` alone |

## Must beat
1. **Mizu on the hero.** Mizu shows a picture of a panel in a picture of a MacBook, cropped at 390. Nagi's is the shipped code running; with JavaScript off, the still capture, with alt text that says what the panel says.
2. **Tailscale on privacy.** Its first screen is a superlative and a consent banner. Nagi's claim takes three sentences and the page obeys them: zero third-party requests, no cookies, no storage, no analytics, self-hosted fonts.

## Add-on gates
- **Alignment:** page line within 0.5 px of the panel's now line from 375 to 1920, both themes, every scene, and after resize, font load and replay. When the panel's line moves, the page line moves in the same frame.
- **Strokes:** trunk and branches use the panel's stroke (1.5 px or more, 3:1), radius and nodes. The site draws no other rule or divider.
- **Colour:** rose only on the now line, the Install node and `Copy`; yellow never outside the panel. Rose text passes 4.5:1 in light.
- **Type:** body 16 px or more; smallest text 13 px, footer included; mono 15 px; no weight under 400. Headlines and body 7:1, tertiary 4.5:1.
- **Truth:** quoted panel strings and tray rows are read from the fixture, never typed; quoted times match the live panel.
- **Motion:** story plays once, with Pause and Replay; branches draw once. Reduced motion shows the still scene with every line already drawn. The panel's slot reserves its tallest height, so layout shift stays 0.

## Tells and don'ts
- **The timeline template.** A trunk with dots and headings is every changelog. It is Nagi only if it leaves the panel's rail and every node means something.
- **A decorative line:** off by a pixel, late on resize, or still while the panel's moves.
- **The tidy dev-tool page:** copy left, panel right, and a line you could delete without loss.
- **Windows drift:** a bordered box around the command, pills, filled buttons, hairline grids.
- **Rose inflation:** rose links, headings or hover states.
- **Invented or hype strings:** "two seconds" as a headline, "never 0%", "open source" before a licence.
- **A second panel, a sticky panel, scroll-scrubbing, or site CSS that fixes the panel.** A reset date that wraps at 340 px is fixed in the panel source.
