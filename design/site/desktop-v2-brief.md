# Desktop redesign brief (Fable call 6)

Written 13 Nov 2026 by the builder for Fable.

## The owner's words
> "the site is nice but its way too boring having everything on left side, i think it looks good on mobile but not on desktop, too much scrolling having it look the same"

## What's being asked
**Redesign the desktop layout (961 px and wider) of the Nagi website. Mobile (960 px and below) stays as it is.** The owner likes mobile.

Today the desktop page puts the opening in two columns: the live panel on the left, and the lede and the two questions on the right. After that, every section hangs one after another from the same trunk on the left, in a single 600 px column. At 1440 that makes a long, left-heavy scroll, and nothing uses the right two-thirds of the screen.

**The goals:**
- **Use the width.** Sections shouldn't all stack in one column on the left.
- **Scroll less.** Aim for roughly half the current desktop page height at 1440, without cramming.
- **Keep the idea and the identity.** "The Line" stays: the panel's own now line carries across the page, and its rail (the trunk) and branches organise the page. Keep the panel's tokens, Inter and the 凪 mark. Rose means now or "asks you". Keep the Apple-grade calm: no gradient-and-glow hero, no bento grid of cards, nothing Windows-like.
- **The hero is still the real, live panel** (an iframe of `site/panel/`, 400 px wide, CSS never scaled or restyled).

## Read first
- The page: `site/index.html`, with all its CSS inline, plus `site/js/site.js`, which draws the trunk, branches and page line in an SVG `#geo`.
- Your earlier direction: `design/site/creative-direction.md`, `concept-selection.md`, `project-bar.md`, and the builder's `art-direction-spec.md`.
- The current screens: `design/site/screens/1440-*-full.jpg` and `375-*-full.jpg`. Run it yourself with `python3 -m http.server 8765 --directory site` from the repository root; Playwright Chromium is at `~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.

## Content changes landing at the same time (truth on main)
Nagi now reads more than T3 Code. Design for this content; the builder writes the final copy.
- **Sources today:**
  - **T3 Code**, read-only, on this computer or on another one over your Tailscale;
  - **Claude Code** and **Codex**, read directly on this computer;
  - **Cursor**, in beta.
- **Coming soon:** OpenBot, Pi, oh-my-pi, Hermes, OpenClaw and OpenCode, plus a "Write an adapter" link.
- **New: low-limit alerts.** One notification per limit window when what's left drops to a percentage you set (10% by default), until that window resets.
- **Privacy is still local-first,** with one honest addition: to show limits from a direct source, Nagi uses your own sign-in and sends it only to that provider (Anthropic, OpenAI or Cursor).
- **The footer** gains "MIT licence".

The sections stay, but you can regroup or merge them:
1. **Tray legend:** "When it's closed, it's just a number."
2. **Privacy:** "It stays on your computer."
3. **Honesty:** "It only says what it knows."
4. **Sources**
5. **Install**

## What I need back
Write `design/site/desktop-v2-direction.md`. It's a direction a builder can implement exactly, not a mood:
- **A desktop composition at 1440,** sketched in ASCII or SVG with real proportions. Say where each section sits, how the trunk, branches and now line route through a multi-column layout, and what happens between 961 and 1280 and above 1600.
- **What stays sticky or scrolls,** if anything. The panel could stay in view as you read, for example, but that's your call.
- **The node vocabulary per section.** This is the open taste follow-up from the fresh judge: the section nodes are all identical hollow rings.
- **Motion changes,** if any. It has to stay within the existing rules: rare, purposeful, and reduced motion honoured.
- **A rough target page height at 1440,** and what you cut or merge to get there.
- **Anything you'd veto.**

You may build a throwaway prototype under `design/site/concepts/desktop-v2/` if it helps, but don't edit `site/`. The builder implements it.

## Hard constraints (unchanged)
- **Privacy:** fictional demo data only. Never read credentials, tokens, T3's database or `~/.config/nagi`.
- **Every claim must be true of main;** anything unbuilt is "coming soon".
- **The site must score Lighthouse 95+** in every category, pass AA contrast in light and dark, honour reduced motion, work at 375 px, and keep CLS at 0.
- **It stays static,** with no third-party requests and no storage.
