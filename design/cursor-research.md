## Cursor — partial local agents and limits; supported cloud-agent reads

> [!WARNING]
> **No installed Cursor runtime was detected by the requested checks, so none of these adapters was validated against a live account.** Local SQLite and dashboard contracts are reverse-engineered and have changed substantially. Current official docs also distinguish legacy Pro/Ultra monthly plans from a newer subscription with an Ultra tier and weekly usage. A plan name alone cannot select the right quota semantics.

Research date: **13 November 2026**. Research only; no integration, settings change, installation, sign-in, quota request or release approval.

### Install and detection

**Both requested machines were reached.** The Mac SSH command succeeded; its result supersedes the earlier companion report's SSH timeout for this particular inspection. Commands used `which cursor`, `which cursor-agent` and one-level `ls -1A` of the supplied directories. Names only were listed. No Cursor file contents, database schema/rows, token values, cookies or Keychain entries were read. No process command lines or environments were inspected.

| Local evidence | Linux | Mac via `ssh <the Mac>` |
| --- | --- | --- |
| `which cursor` | No PATH result | `cursor not found` |
| `which cursor-agent` | No PATH result | `cursor-agent not found` |
| `~/.cursor` | Contains **`hooks.json` only** | Absent |
| `~/.config/Cursor` | Absent | Absent |
| `~/Library/Application Support/Cursor` | Not applicable | Absent |

**Interpretation: not detected on PATH or at these standard data roots.** This is not an exhaustive installed-app inventory: GUI app bundles, alternate homes, portable installations, custom user-data paths and the newer CLI name `agent` were not checked. An isolated `hooks.json` does not prove installation, configuration contents or hook execution. No additional Cursor directory traversal was needed.

### Capability verdicts

“Supported” means a documented candidate interface, conditional on account access and version validation; it does not mean connected here. “Partial” means useful bounded observations are possible but coverage or semantics are incomplete. “Unsupported” means the requested guarantee was not established through the inspected surfaces.

| Capability | Verdict | What Nagi can honestly report |
| --- | --- | --- |
| IDE/Composer title and project | **Partial overall; saved metadata supported by existing readers** | Stored name, conversation ID and workspace when present; schema-dependent and not a live roster. |
| IDE/Composer running/finished, existing files only | **Partial** | A saved completion/status observation; current running state is **unsupported as a dependable guarantee**. |
| IDE/CLI live lifecycle with deliberately configured hooks | **Partial candidate** | Documented turn/tool/subagent events; baseline, crashes, continuation and installed-version behavior must be qualified. |
| IDE/CLI parent/child | **Partial** | Child markers and transcript containment; explicit hook parent relation when available. No universal reliable parent field established in saved metadata. |
| Background/cloud agent title, state and repository | **Supported candidate via official API** | Paginated roster, durable metadata and current run status; **unsupported from local files alone**. |
| Cloud parent/child tree | **Unsupported through inspected roster schema** | Leave parent unknown. Subagent definitions and aggregate usage do not constitute a runtime child roster. |
| Pro/legacy Ultra monthly utilization and reset | **Partial via private dashboard API** | Provider-reported percentages, optional amount/cap and billing-cycle end, using an existing login session. |
| Purely offline plan remaining/reset | **Unsupported** | Dated cached observations only; no authoritative local subscription allowance established. |
| Fixed modern request count from plan name | **Unsupported** | Only display a request quota when the legacy endpoint explicitly supplies a denominator. |

### Read-only surfaces, best first — IDE and Composer

**Exact default roots:**

| Surface | Linux | macOS |
| --- | --- | --- |
| Global IDE database | `~/.config/Cursor/User/globalStorage/state.vscdb` | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` |
| Per-workspace database | `~/.config/Cursor/User/workspaceStorage/<workspace-id>/state.vscdb` | `~/Library/Application Support/Cursor/User/workspaceStorage/<workspace-id>/state.vscdb` |
| Workspace association | Same workspace directory, `workspace.json` | Same workspace directory, `workspace.json` |
| Agent transcript mirror | `~/.cursor/projects/<project-slug>/agent-transcripts/` | `~/.cursor/projects/<project-slug>/agent-transcripts/` |
| Optional tracking metadata | `~/.cursor/ai-tracking/ai-code-tracking.db` | `~/.cursor/ai-tracking/ai-code-tracking.db` |

These are **public-source paths, not files found here**. Linux IDE readers may honor `$XDG_CONFIG_HOME/Cursor/...`; explicitly configured/portable roots require separate selection. The IDE's capitalized `Cursor` directory and the CLI's lowercase `cursor` credential directory are different. [cursaves path implementation][CS-P]; [CodexBar auth implementation][CB-A]

1. **Saved header metadata is the least intrusive existing surface.** Modern readers handle a dedicated `composerHeaders` table in the global database: `composerId`, `workspaceId`, `createdAt`, `lastUpdatedAt`, `isArchived`, `isSubagent`, `recency`, `checkpointAt`, and JSON `value` have been observed. `value.name` supplies the saved title; column availability varies. The table and columns are reverse-engineered. [chat-history reader][CH-I]; [aistack's first-hand schema investigation][AS-R]
2. **Older generations need distinct compatibility profiles.** Global `ItemTable(key,value)` key `composer.composerHeaders` contains `allComposers[]`, including `composerId`, `name` and `workspaceIdentifier`. Still older workspace `ItemTable['composer.composerData']` contains `allComposers[]`. Migrated workspace values can retain only `selectedComposerIds`/`lastFocusedComposerIds`; these are selected tabs, not running agents. `workspace.json` has `folder` or `workspace` URI; use this or `workspaceIdentifier.uri`, not a guessed decoding of the directory hash. [cursaves discovery implementation][CS-P]
3. **Conversation records are richer but more sensitive.** Global `cursorDiskKV(key,value)` key `composerData:<composerId>` can contain `name`, `createdAt`, `status`, `unifiedMode`, `modelConfig` and message headers. Saved `status` examples include `none`/`completed`. `bubbleId:<composerId>:<bubbleId>`, `checkpointId:...`, `messageRequestContext:...` and newer `agentKv:...` contain conversation/tool/code data; Nagi does not need them for the initial glance. A reader must not infer that `none` means running. [cursaves reverse-engineering notes][CS-D]

**Future SQLite reads must remain passive.** Use bounded read-only transactions and preserve WAL visibility. A live `immutable=1` connection can hide recent WAL changes; ordinary SQLite reads can need existing shared-memory sidecars. If safe read access is unavailable, report unavailable rather than creating sidecars, checkpointing, vacuuming or opening a writable connection. Do not naively copy just the main file or assume separately copied DB/WAL files form an atomic snapshot. This research opened no local database. [AS-R]; [CB-A]

**Freshness is not execution.** Database mtime also reflects editor state and secrets. Open tabs, recent writes, a live Cursor process, `isAgentic`, or an unarchived header do not prove a current turn. A completed saved generation does not prove that the conversation cannot accept another prompt. Aistack observed the header/message schema change during its own investigation; this is direct evidence against treating disk layout as a stable API. [AS-R]

**Parent/child is bounded.** Header `isSubagent` identifies a child category, not its parent. Older composer IDs prefixed `task-toolu_...` are another child hint. New transcript trees can place children under `agent-transcripts/<parent-id>/subagents/`; preserve that explicit containment when available, without assigning unrelated child records by title, recency or project. These are Task children; branching, forks and coordinated projects need separate evidence. [CS-D]; [CLI changelog, 17 October 2026][CLI-C]

**Authentication and stability:** reading metadata needs owner filesystem permission, **not the Cursor login token**. Storage is reverse-engineered, **low stability**, with multiple generations in circulation. An initial adapter should have explicit schema detection and fail to unavailable on unknown shapes. No local runtime was available to determine which profile is installed.

### Read-only surfaces — `cursor-agent` / Agent CLI

**Default session roots on both Linux and macOS:** `~/.cursor/chats/<workspace-hash>/<session-id>/`, containing `meta.json` and `store.db`. Staff confirmed that this chat tree is local-only; IDE and CLI history were separate at the dates of their replies. Do not infer a local IDE conversation from a CLI session or cloud synchronization from a shared account. [Cursor staff, 9 April 2026][STAFF-CLI]; [Cursor staff, 20 April 2026][STAFF-SPLIT]

**Prefer `meta.json` for listing.** An existing reader consumes `schemaVersion` (known profile: `1`), `title`, `cwd`, `createdAtMs`, `updatedAtMs`, `hasConversation` and `isSubagent`. These provide title/project/times and a child flag without loading message blobs. Missing `cwd` means project unknown. A workspace hash or lossy project slug must not be converted back to an invented path. Optional ACP sessions have a separate `~/.cursor/acp-sessions/<session-id>/` tree; treat that as separate discovery, not proof every CLI run uses it. [chat-history CLI parser][CH-C]; [ACP storage issue][ACP-I]

**Exact SQLite fallback:** `store.db` contains tables `meta(key,value)` and `blobs(id,data)`. CodeBurn reads `meta` key **`'0'`**, whose value is hex-encoded JSON with `agentId` and `createdAt` (also a `blobEncryptionKey`, which the Nagi reader should exclude). Its message reader decodes content-addressed JSON/protobuf blobs; observed root fields are message IDs **1**, workspace URI **9**, timestamp **26**. This is reverse-engineered and unnecessary for the first metadata adapter. [CodeBurn CLI provider source][B-CLI]

**Optional title fallback:** `~/.cursor/ai-tracking/ai-code-tracking.db`, table `conversation_summaries`, queried by `conversationId`, has `title`, `model`, `updatedAt`. CodeBurn uses these fields to enrich transcript records. No authoritative running flag or quota/reset was established there. [B-CLI]

**Transcript shapes:** legacy `agent-transcripts/<id>.txt` and newer `agent-transcripts/<id>/<id>.jsonl` coexist. JSONL may include `turn_ended`; nested `subagents/` gives bounded lineage evidence. A mirror may be delayed or written at the end. A missing end marker is not proof of running, and a turn end is not necessarily a session end. CodeBurn deduplicates IDE records, transcripts and CLI stores by conversation ID; Nagi should too. [CodeBurn storage and coverage notes][B-CLID]; [CLI-C]

**Official CLI commands are not an observer daemon.** `agent ls` opens a history picker; `--resume`, `resume`, ACP server mode and print/stream-json mode can load or execute agents. `agent status` is authentication status, not a running-agent roster or plan quota command. Do not launch these from a passive detector. CLI configuration documents `CURSOR_CONFIG_DIR` and Linux/BSD `XDG_CONFIG_HOME/cursor` overrides; verify whether the selected build moves session storage with the config root. [CLI parameters][CLI-P]; [CLI authentication][CLI-A]; [CLI configuration][CLI-F]

**Authentication and stability:** saved metadata needs **no login token**. File schemas and protobuf fields are **low stability**; the default chat path has staff confirmation but no stable published storage contract. Existing readers demonstrate history extraction, not complete current running state.

### Documented hooks — recommended future live-state path

**Hook configuration is documented:** user `~/.cursor/hooks.json` or project `<project>/.cursor/hooks.json`, on both operating systems. Hooks can supply `conversation_id`, `generation_id`, `workspace_roots`, `cursor_version`; `beforeSubmitPrompt`, `stop`, `sessionStart`/`sessionEnd` and tool events describe lifecycle. `subagentStart` supplies `subagent_id`, `parent_conversation_id`, `tool_call_id` and type. `subagentStop` has completed/error/aborted status. Its documented example does not establish a matching child ID, so concurrent-child closure needs a version-specific correlation test. No explicit chat-title field was established; enrich from saved metadata. [hooks contract][HOOKS]

**Use an observer export, never a policy hook.** Future setup should preserve existing hooks, emit only IDs, event/status/timestamp and project metadata, and use event-specific neutral responses. Never return a follow-up, prompt/context injection, modified tool input, deny or approval decision. Permission hooks can block on malformed responses; this is why installing an observer is a separate deliberate setup step. No hooks were opened or installed here. [HOOKS]

**Treat lifecycle conservatively:** prompt-submit occurs before execution, so initially “submitted,” not proven running. A stop can be followed by automatic continuation; tool completion is not conversation completion. Crash/missed-event gaps must become unknown, not idle. A future exporter needs recovery/baseline coverage and bounded liveness evidence. Hooks are documented and more stable than SQLite, but the October CLI changelog records fixes to Task completion hooks and child transcript paths, so the installed version matters. [CLI-C]

**Existing menu-bar evidence:** `Halo-Welt/agent-monitor` already observes Cursor through hooks and renders session/subagent trees. Its own privacy note says its logs can include prompts, file contents and shell output. It supports feasibility, but its raw capture format is unsuitable for Nagi's minimal export. Study the event mechanism; do not reuse its content collection wholesale. [pinned Agent Monitor README][MON]

**No login token is needed for local hook output.** Cloud project hooks run remotely, and some early read-only cloud turns have no hooks; local hook files therefore cannot supply a complete cloud roster. [HOOKS]

### Background/cloud agents — official API, independent of desktop files

**Use the documented HTTP surface**, not the desktop's local SQLite store:

| Read | Exact endpoint at `https://api.cursor.com` | Projection |
| --- | --- | --- |
| Roster | `GET /v1/agents?limit=20&cursor=<nextCursor>` | `id`, optional `name`, lifecycle `status`, `env`, `url`, creation/update times, `latestRunId` |
| Project | `GET /v1/agents/<id>` | `repos[].url`, `startingRef`; repository may be absent |
| Run roster | `GET /v1/agents/<id>/runs` | Run identity and status |
| Current run | `GET /v1/agents/<id>/runs/<runId>` | `CREATING`, `RUNNING`, `WAITING_FOR_BACKGROUND_WORK`; terminal `FINISHED`, `ERROR`, `CANCELLED`, `EXPIRED` |

Follow pagination. Read execution from runs, not agent lifecycle. Discard final `result` text. **Parent/child is unsupported in the inspected roster schema:** `customSubagents` describes configured definitions; no runtime parent ID was established. [official v1 reference][CLOUD]; [OpenAPI schema][CLOUD-Y]

**Version caveat:** the prose includes lifecycle `IDLE`, while the inspected OpenAPI `AgentSummary.status` enum lists only `ACTIVE`/`ARCHIVED`. Preserve unknown lifecycle values and trust run states for execution. This is a concrete beta-contract mismatch. The legacy alternative is `GET /v0/agents` and `/v0/agents/<id>`, with flatter `name`, `status`, `source.repository` and `target` fields; implement a separate version profile if needed. [CLOUD-Y]; [legacy v0 reference][CLOUD-0]

**Auth:** dashboard-generated user API key or service-account API key, HTTP Basic with key as username and empty password, or Bearer key. **No IDE login token is required.** No fixed local credential-file path is documented for an observer; provision the key into the existing private runtime boundary. No method-restricted observer scope was established; enforce a closed GET allowlist and never use an Admin `admin:*` key merely for roster reads. Official API, **public beta / medium stability**; no authenticated calls made here. [API authentication and limits][API]

Per-agent `GET /v1/agents/<id>/usage` is token accounting including subagents, **not the Pro/Ultra remaining monthly allowance**. It cannot supply a subscription reset by itself. [CLOUD]

### Limits, authentication, remote and stability

**Plan generation matters.** Current docs call Pro ($20/month) and the earlier Ultra ($200/month) legacy plans: two included pools, Cursor Models and Other Models, reset monthly with the billing cycle. New X Subscription accounts instead have a weekly Cursor-model pool and separately purchased third-party usage. The Ultra label exists in both generations. [legacy-plan documentation][PLANS]

**Historical allowance, not a constant:** Cursor staff stated in June and August 2026 that Pro included $20 and Ultra $400 of third-party/API usage, plus a separate first-party pool. These dated statements do not establish today's numeric denominator for an uninspected account. Neither is a request count. Display the actual returned amount/cap when trustworthy, otherwise only reported percentage. [June staff allowance clarification][STAFF-PLAN]; [August staff clarification][STAFF-PLAN-AUG]

**Exact reverse-engineered quota surface:** existing menu-bar trackers CodexBar and CodeBurn use:

| Endpoint | Auth and relevant fields | Status / stability |
| --- | --- | --- |
| `GET https://cursor.com/api/usage-summary` | Cursor web session cookie. Root `membershipType`, `limitType`, `billingCycleStart`, `billingCycleEnd`; `individualUsage.plan.{enabled,used,limit,remaining,autoPercentUsed,apiPercentUsed,totalPercentUsed,breakdown}`; `individualUsage.onDemand.{enabled,used,limit,remaining}`. | Private dashboard interface; low stability. Primary candidate for monthly usage/reset. |
| `GET https://cursor.com/api/auth/me` | Same cookie; account `sub`, used for identity matching. | Private; optional identity check, do not expose email/name. |
| `GET https://cursor.com/api/usage?user=<ID>` | Same cookie; `gpt-4.numRequestsTotal`/`numRequests`, `gpt-4.maxRequestUsage`, `startOfMonth`. | Private legacy request-plan fallback only. |

Amounts in the inspected plan/on-demand models are **cents**. Percent fields use **0–100 units**, so `0.36` means `0.36%`. Preserve separate pools; do not average them into an invented overall limit. `plan.breakdown.total` is not the plan cap. Prefer reported percentages when dollar fields are missing/zeroed; never back-calculate an allowance from a marketing plan label. CodexBar supports both old request and newer usage models. [CodexBar response models][CB-S]; [percentage/parser implementation][CB-U]; [CodeBurn quota implementation][B-Q]

**Reset date:** use the response's `billingCycleEnd` for the established monthly plan profile, with a successful-fetch observation timestamp and original timezone. Do not assume calendar-month start/end or add 30 days. Official billing docs establish monthly replenishment for legacy plans; exact account timing remains unavailable here. An annual invoice cadence is not evidence that included allowance resets yearly. [billing documentation][BILLING]; [CB-U]

**No public individual quota API was established.** Cursor staff explicitly said in May 2026 that no public individual usage API/CLI existed. Today's inspected public cloud API gives per-agent usage, and Admin/Analytics APIs serve different scopes; none established a Pro/Ultra personal remaining/reset replacement. The working dashboard paths above are evidence of reverse-engineering, not an official integration promise. [staff usage-API reply][STAFF-API]; [API]; [CLOUD]

**Exact credential custody — locations only, never inspected locally:**

| Credential source | Linux | macOS | Reader implications |
| --- | --- | --- | --- |
| IDE login token | Global IDE `state.vscdb`, `ItemTable`, key **`cursorAuth/accessToken`** | Same table/key in the macOS global path above | Used for private quota requests; not needed for local agent metadata. |
| Newer encrypted IDE token | Platform handling unverified by this research | Same key may contain **`cursor-safe-storage:v1:`**; Keychain service **`Cursor Safe Storage`**, account **`Cursor Key`**, older account **`Cursor`** | CodexBar and CodeBurn support this macOS change. Background polling must not trigger a Keychain prompt. |
| CLI login token | **`$XDG_CONFIG_HOME/cursor/auth.json`**, default **`~/.config/cursor/auth.json`**, field **`accessToken`** | Login Keychain service **`cursor-access-token`**, account **`cursor-user`** | Existing independent readers support these paths. CLI `cli-config.json` is not itself the macOS token. |
| CLI file-store override | Selected build/configuration must be verified | Staff document **`AGENT_CLI_CREDENTIAL_STORE=file`**, writing **`~/.cursor/auth.json`** | An explicit alternate mode, not the universal CLI default. |
| Web session | Selected browser's cookie store or deliberately provisioned private session | Same | Main recognized cookie **`WorkosCursorSessionToken`**; account-wide session, not a scoped read token. |

CodexBar/CodeBurn derive the web cookie as `WorkosCursorSessionToken=<user-id>%3A%3A<access-token>`, deriving the user ID from JWT claims. They validate expiry and can read usage without refreshing the login. This is not ordinary Bearer auth to `/api/usage-summary`, and the public cloud API key is not demonstrated to substitute for that cookie. Leave refresh tokens untouched; expire to unavailable/re-authentication-needed. These are sensitive account credentials even though the request method is GET. [CB-A]; [B-Q]; [independent CLI credential reader][Q-CLI]; [staff Keychain/file-store explanation][STAFF-AUTH]

**Pure local quota remains unsupported.** `contextUsagePercent` is context occupancy, not subscription usage; transcript character/token estimates do not reveal allowance or reset. Saved histories also omit other machines/cloud work. Cache only a real dated remote observation and retain its age on errors. For the new unified/weekly account profile, CodexBar has separate handling, including `POST /api/dashboard/get-sand-usage-status` and `usagePercent`/`nextResetTimestampUtc`; do not relabel its monthly billing end as a weekly reset. Keep this outside the first legacy-plan adapter until validated for the selected account. [CodexBar provider notes][CB-D]

**Remote:** the collector belongs on the UI host for IDE state, on the execution host for CLI state, and on the selected credential host for account usage. SSH workspace URIs do not imply that IDE history lives on the remote filesystem. Export sanitized metadata over Nagi's existing authenticated private transport; do not share raw Cursor homes, databases, cookies or keys. Local and development custody remain independent. [CS-D; Nagi repository instructions]

### Recommended adapter design

1. **Split capability and custody.** One Cursor provider can expose `local-ide`, `local-cli`, `cloud` and `account-usage` connections, but each reports independent detected/available/stale/unsupported state. Credential-free saved metadata can work while cloud/usage are disconnected. Keep all reads in the existing owner-only collector/private runtime; dashboard and tray receive only projections.
2. **Start with narrow metadata discovery.** Detect explicitly selected roots and known schema profiles; prefer header rows and CLI `meta.json`. Allowlist conversation ID, saved title, project URI, child marker and dates. Never fall back to prompt-derived titles. Bound file sizes, query duration and history depth. Use same conversation ID to deduplicate IDE headers, stores, transcript mirrors and child exports; do not deduplicate distinct accounts or hosts by title.
3. **Add hooks only as a future setup feature.** Preserve the user's current config. Export sanitized lifecycle events with conversation/generation IDs, timestamps and version. Test submit/stop/auto-continue/cancel/crash and parallel children before claiming live completeness. Startup with only historical metadata is unknown. A gap stays unknown until reconciled; a timeout alone must not claim finished or stuck.
4. **Use official cloud GETs separately.** Provision a key explicitly, enforce host/path/method allowlists, paginate and observe run state. Throttle metadata polling to fit documented rate limits and honor `429`. Persist only dated metadata; do not open conversation/stream/artifact bodies for a glance. Parent remains null until an explicit supported relation is available.
5. **Make network quota opt-in and account-bound.** Prefer a dated sanitized export from an already approved tracker if one exists; none was detected/checked here. Otherwise a dedicated host-side reader can reuse an explicitly selected session, read-only and without token refresh. Poll slowly, back off on rate limits, fail closed on account changes and retain measurement time. The quota helper owns credentials; Nagi's frontend never receives them.
6. **Project the actual units.** Keep Cursor Models, Other Models, legacy requests and on-demand spend separate. Show percentage/reset with unknown amount/cap when necessary. Never sum the same account's quota across IDE/CLI/cloud or across machines. Preserve provider total only if returned; do not copy third-party default-zero or averaged-percent fallbacks into Nagi's truth rules.
7. **Acceptance before enabling:** obtain sanitized fixtures for the owner's installed version and account generation, then verify two concurrent turns, a Task child, automatic continuation, cancellation, crash/stale recovery, duplicate transcript/DB IDs and an account switch. Confirm an actual monthly reset field and percentage units using a permitted account read. This report does not authorize those later credential/database probes or configuration changes.

### Open risks and final verdict

- **Coverage:** no local installation/version/account readback; alternate installations were outside the requested detection. Existing `hooks.json` contents remain unknown.
- **Running state:** file history is not a dependable current roster. Hooks need complete startup/recovery semantics and child correlation; cloud lineage remains unavailable.
- **Schema drift:** older `ItemTable` indexes, modern `composerHeaders`, `agentKv` and CLI store formats require separate profiles. The published cloud prose/OpenAPI lifecycle mismatch is unresolved.
- **Credentials:** quota needs a broad login session; macOS encryption/Keychain access adds an explicit setup boundary. Linux encrypted-token support and custom CLI file-store roots are not proven here.
- **Allowance semantics:** legacy Pro/Ultra monthly pools differ from new Ultra weekly usage; historical $20/$400 figures must not become hardcoded current caps. Numeric allowance can remain unknown while utilization/reset is usable.

**Recommendation: add Cursor as a partial source with honest per-capability states.** Credential-free history metadata is feasible now; reliable live local activity needs an approved observer export, cloud status has a documented API, and plan limits require an explicitly authorized private-dashboard reader or existing sanitized tracker export. Do not advertise a complete passive offline Cursor roster or quota meter.

[CS-P]: https://github.com/Callum-Ward/cursaves/blob/2919739d35a043f1f35979a758f87d4c936a42b7/cursor_saves/paths.py
[CS-D]: https://github.com/Callum-Ward/cursaves/blob/2919739d35a043f1f35979a758f87d4c936a42b7/docs/how-cursor-stores-chats.md
[CH-I]: https://github.com/ay-bh/chat-history/blob/807a6c37729579ca46f736266fac48587cfa1a9c/src/cursor_ide.rs
[CH-C]: https://github.com/ay-bh/chat-history/blob/807a6c37729579ca46f736266fac48587cfa1a9c/src/cursor_cli.rs
[AS-R]: https://github.com/alp82/aistack/blob/1929bb69ba87c9dd5d798feb5f7c39980454532f/docs/research/harness-adapters-2026-08.md
[B-CLI]: https://github.com/getagentseal/codeburn/blob/40d58800c13422d8681862482bab02380e42582f/src/providers/cursor-agent.ts
[B-CLID]: https://github.com/getagentseal/codeburn/blob/40d58800c13422d8681862482bab02380e42582f/docs/providers/cursor-agent.md
[B-Q]: https://github.com/getagentseal/codeburn/blob/40d58800c13422d8681862482bab02380e42582f/src/quota/cursor.ts
[CB-A]: https://github.com/steipete/CodexBar/blob/7447bc77c2497323d9c41e40164ce705533493c8/Sources/CodexBarCore/Providers/Cursor/CursorAppAuth.swift
[CB-S]: https://github.com/steipete/CodexBar/blob/7447bc77c2497323d9c41e40164ce705533493c8/Sources/CodexBarCore/Providers/Cursor/CursorStatusProbe.swift
[CB-U]: https://github.com/steipete/CodexBar/blob/7447bc77c2497323d9c41e40164ce705533493c8/Sources/CodexBarCore/Providers/Cursor/CursorStatusProbe%2BUsageSummary.swift
[CB-D]: https://github.com/steipete/CodexBar/blob/7447bc77c2497323d9c41e40164ce705533493c8/docs/cursor.md
[Q-CLI]: https://github.com/kunchenguid/quota-axi/blob/5734c41eee52eb9a80ba67f47269ebc06c0c41fc/src/providers/cursor-cli-credential.ts
[MON]: https://github.com/Halo-Welt/agent-monitor/blob/c51c5d98f2d148cdec9d9a740243338bd9e5ae1a/README.md
[HOOKS]: https://cursor.com/docs/hooks
[CLI-C]: https://cursor.com/docs/cli/changelog
[CLI-P]: https://cursor.com/docs/cli/reference/parameters
[CLI-A]: https://cursor.com/docs/cli/reference/authentication
[CLI-F]: https://cursor.com/docs/cli/reference/configuration
[CLOUD]: https://cursor.com/docs/cloud-agent/api/endpoints
[CLOUD-Y]: https://cursor.com/docs-static/cloud-agents-openapi.yaml
[CLOUD-0]: https://cursor.com/docs/cloud-agent/api/v0
[API]: https://cursor.com/docs/api
[PLANS]: https://cursor.com/docs/account/pricing/legacy-cursor-plans
[BILLING]: https://cursor.com/help/account-and-billing/billing
[STAFF-PLAN]: https://forum.cursor.com/t/how-much-usage-is-available-on-the-200-subscription/163309
[STAFF-API]: https://forum.cursor.com/t/usage-api-cli-command/160967
[STAFF-CLI]: https://forum.cursor.com/t/cursor-agent-create-chat-and-how-to-delete-old-chats/156640/7
[STAFF-SPLIT]: https://forum.cursor.com/t/cursor-cli-past-chats-not-showing-up/152450/20
[STAFF-AUTH]: https://forum.cursor.com/t/errsecitemnotfound-couldnt-find-your-saved-login-in-the-macos-keychain/167325/7
[ACP-I]: https://github.com/zed-industries/zed/issues/58887

[STAFF-PLAN-AUG]: https://forum.cursor.com/t/usage-limits-in-teams-vs-individual/167937/7
