# Message house

**Promise:** When you're running a lot of coding agents, one look at your menu bar tells you what each one is doing and how much room you have left.

| Pillar | What we say | Proof |
|---|---|---|
| **Your agents, by name** | Each running agent by its title, hanging from the agent that started it, with its model, how long it's run and how long it's been quiet. A quiet agent turns yellow past halfway and is marked stuck at 15 minutes; one that needs you is marked in rose. | p1, p2, p13 |
| **Your limits, honestly** | One line per account, lowest window first, with the % left and the date it resets. Two Codex accounts are never averaged. If a check fails, it says so and when it tried. | p3, p4 |
| **Yours alone** | A small reader on 127.0.0.1, a read-only token, no account, no cloud, no telemetry. Another computer only over your own Tailscale. | p5, p6, p7, p8, p14 |

**Objections**
- *"Another dashboard?"* No. It's a menu-bar glance with one job and no history, charts or controls. (p14)
- *"Does it read my code or prompts?"* It reads agent titles, states and limit windows through T3 Code's read-only API. Prompts, transcripts and tool output never enter it. (README "Local owner boundary")
- *"I don't use T3 Code."* Today Nagi reads T3 Code; Codex, Claude Code, OpenBot, Pi, oh-my-pi, Hermes, OpenClaw and OpenCode are coming soon, and each is a small adapter you can help write. (p12)
- *"Will it phone home?"* No. The only connections it makes are to the T3 Code servers you set up. (p7)
