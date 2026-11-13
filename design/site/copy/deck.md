# Nagi site copy deck

Reader: a developer who runs several coding agents at once (T3 Code today), arriving from GitHub, a post or a friend. Awareness: knows the pain (tabs, a quiet agent, a surprise limit), doesn't know Nagi. One job per surface in `surfaces.md`.

## Headline variants (angle · VOC/proof)
1. See what your agents are doing and how much you have left. · both questions · v1 v2 · [proof:p1] [proof:p3]
2. Know which agent went quiet before your limits run out. · the quiet agent · v4 · [proof:p2] [proof:p3]
3. Your agents by name, and your limits by date. · specifics · [proof:p1] [proof:p3]
4. What are my agents doing? Am I about to hit my limits? · the reader's own two questions · v1 v2
5. A calm look at every agent you're running. · the name (凪, calm sea) · [proof:p1]
6. Two questions, answered from your menu bar. · surface · v1 v2
7. Every agent you're running, and every limit you're near. · coverage · [proof:p1] [proof:p3]
8. Run eight agents and still know what each one is doing. · scale · v8 · [proof:p1]
9. Stop clicking through tabs to find the agent that's stuck. · tabs pain · v5 · [proof:p2]
10. See who's working, who's gone quiet and when your limits reset. · tricolon wildcard · [proof:p1] [proof:p2] [proof:p3]
11. The menu-bar glance for people who run a lot of agents. · category · [proof:p9]
12. Your agents and your limits, one look away. · glance · [proof:p1] [proof:p3]
13. Know where every agent is, without leaving what you're doing. · flow · [proof:p1]
14. Agents working, limits holding. Check it with one look. · wildcard, status line · [proof:p1] [proof:p3]
15. Notice the agent that's been waiting on you for 40 minutes. · approval wait · v4 · p1 (asks you)
16. Find out your weekly limit is empty before the agent does. · limits surprise · v6 · [proof:p3]
17. A quiet panel for a lot of busy agents. · contrast wildcard · [proof:p1]
18. Glance up. Your agents and limits are right there. · gesture · [proof:p9]
19. Keep a lot of agents running without losing track of one. · reassurance · [proof:p1] [proof:p2]
20. Everything your agents are doing, next to the clock. · placement wildcard · [proof:p9]

**Top 3 (my pick before judging):** 1 (says both jobs in the reader's words), 2 (the scene that hurts, with its consequence), 4 (the reader's own questions, verbatim).

## Lede variants
1. When you've got several agents running, Nagi sits in your menu bar and names each one under the agent that started it, with how long it's been quiet. Above them, each account's lowest limit shows the % left and the date it resets. [proof:p1] [proof:p2] [proof:p3]
2. You start a few agents, switch to something else, and lose track. Nagi keeps one small panel in your menu bar: every running agent by name, the ones that have gone quiet, and each account's limit with its reset date. [proof:p1] [proof:p2] [proof:p3]
3. Open the panel and the answers are already there: which agents are running and who started them, which one has gone quiet, and how much of each limit is left before it resets. Nothing to set up beyond your first connection. [proof:p1] [proof:p2] [proof:p3]
4. It's a small, read-only panel in your menu bar or tray. It runs on your own computer, names every agent you're running and shows each account's limits with their reset dates. [proof:p1] [proof:p3] [proof:p7] [proof:p14]
5. Nagi answers the two questions you keep asking while agents work: what is each one doing, and how close are you to a limit? It shows the answer in your menu bar in about two seconds. [proof:p1] [proof:p3]
6. Each agent you're running appears by its title, hanging from the one that started it. A line under it grows as it goes quiet. Above, every account shows its lowest limit and when it resets. [proof:p1] [proof:p2] [proof:p3]
7. Your agents keep working while you do something else. When you look up, Nagi tells you which ones are still going, which one needs you and how much of your limits you've used. [proof:p1] [proof:p3]
8. One glance shows every running agent and every account limit. It runs only on your computer, reads without changing anything and sends nothing anywhere. [proof:p1] [proof:p3] [proof:p7] [proof:p14]

## CTA variants
1. Install Nagi (primary; jumps to the install commands)
2. View on GitHub (secondary)
3. Get Nagi
4. Copy the install command
5. See how it works
6. Read the source

## Sections (one draft each, to tune after the concept is picked)

**Two questions**
- *What are my agents doing right now?* Every running agent appears by its title, under the agent that started it, with its model, how long it has run and when it last spoke. A rose dot means it's asking you something. [proof:p1]
- *Am I about to hit my limits?* Each account gets its own line: the lowest window first, the % left and the date it resets. Two Codex accounts stay two lines; nothing is averaged.

**Silence (Lull)**
- A thin line grows under an agent while it's quiet. Past halfway it turns yellow, and at 15 minutes the agent is marked stuck and you get one notification. You can change the 15 minutes in Settings.

**Honest limits**
- If Nagi can't read a limit, it says `couldn't check` and the time it tried. It never shows 0% or an empty bar for a check that failed. [proof:p4]

**Private by design** (heading candidates: "It stays on your computer." / "Nothing leaves your computer.")
- Nagi runs a small reader on 127.0.0.1 that only answers you. It reads T3 Code with a read-only token, so it can't send, stop or approve anything.
- There's no account, no cloud service and no telemetry. Prompts, transcripts and tool output never enter Nagi's responses or its saved files. [proof:p7]
- To watch another computer, Nagi connects over your own Tailscale. Computers never read each other's agents otherwise. [proof:p8]

**Sources**
- Heading: "Works with T3 Code today."
- Line: "Each agent app is a small adapter. These are next:" then the list, each marked `Coming soon`: Codex, Claude Code, OpenBot, Pi, oh-my-pi, Hermes, OpenClaw, OpenCode.
- Link text: "Write an adapter". Target: `design/sources-contract.md` until a CONTRIBUTING guide exists.

**Install**
- Heading: "Install Nagi"
- Line: "On Linux or macOS, clone the repository and run the installer. It asks before it uses sudo, and it never overwrites your data." [proof:p10]
- Command: `git clone https://github.com/yeqiuqiu123/nagi.git && cd nagi && ./install.sh`
- After: "Nagi opens and walks you through connecting T3 Code, read-only."
- Needs: Python 3.11 or newer. Linux: GTK 3, WebKitGTK 4.1 and an AppIndicator tray (the installer checks). macOS: builds the menu-bar app on your Mac.
- Button states: Copy → Copied.

**Open source**
- "Nagi is open source. Read the code, file an issue or write an adapter for the agent app you use." Licence line: *pending the owner's pick.*

## Microcopy
| Where | String |
|---|---|
| Nav | Install, Sources, Privacy, GitHub |
| Demo caption | Demo data. A few minutes of agent work, sped up. |
| Demo controls | Pause, Play, Replay |
| Copy button | Copy / Copied |
| Copy failed | Couldn't copy. Select the command and copy it yourself. |
| Footer | 凪 nagi means a calm sea. |


## Fable's copy judgement (creative call 5 of 5): shipped
Blind and pairwise, each pair judged in both orders. Every winner won in both orders.
- **Headline:** H-b, "A small glance in your menu bar for when you're running a lot of AI coding agents."
- **Answer lines:** L-c's agents half, plus a limits half corrected for truth. "One line per account" was false, because an account with several windows shows one line per window.
- **Actions:** C-a. "Source on GitHub" is the one name for that link everywhere. The sign-off still cuts it from beside Copy, so it appears in the header and the footer.
- **Friendliness rewrites (R17) applied:** the tray heading, stuck, failed limits read, offline, sources and the install requirement lines.
- **Owner pick: pending.** Runners-up for the owner:
  - H-c: "If you run several AI coding agents at once, Nagi shows them all in your menu bar."
  - H-a: "Nagi is a small menu-bar glance for people running AI coding agents."
