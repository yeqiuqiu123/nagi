# Direct-source implementation evidence — 13 November 2026

Development checkout: `nagi-direct`, base `8d33569`. No installed runtime was
modified. Hook lifecycle tests use a disposable home, never the owner's settings.

## Claude

A real read-only HTTPS GET to the fixed Anthropic OAuth usage endpoint succeeded
from this computer using the existing login, without refresh. Exploration printed
only key names and types. Confirmed top-level five_hour/seven_day objects with
float utilization and string resets_at; seven_day_opus/seven_day_sonnet and other
model buckets may be null. Extra spend/currency fields exist and are discarded.
The request did not install or connect a source. This is endpoint-shape evidence,
not proof of a running tray, Mac login, live hooks or delivered OS banner.

Official hook input/lifecycle reference inspected:
https://code.claude.com/docs/en/hooks . Hook input has session_id/cwd, optional
agent_id/agent_type, and SessionStart optionally has model. Notification's
permission_prompt is ask evidence. Stop finishes a turn. There is no guaranteed
session-name field. Titles therefore use neutral Claude session / subagent type,
never prompt or last_assistant_message. Pre/PostToolUse carry liveness only.

T3 source revision `4f0b74e190261c8233ae52af17b0fd1734e99e50`,
`apps/server/src/provider/Drivers/ClaudeHome.ts:65-87`, sets
CLAUDE_CODE_ENTRYPOINT=t3-code for SDK launches. The hook sink accepts only known
standalone entrypoints and omits T3/unknown SDKs. T3 allows an entrypoint override;
coverage remains partial and this is not a universal process-origin attestation.

## Codex

Bounded structural inspection of recent local rollout headers found T3 Code
originators in the default ~/.codex/sessions tree. T3 source's CodexProvider.ts
sets CODEX_INTERNAL_ORIGINATOR_OVERRIDE and initialize client name to T3 Code;
its configured homePath may change CODEX_HOME. Thus the default home can overlap,
and non-default T3 homes are outside this source's scope. Exclude T3 originators;
unknown originators are omitted rather than guessed standalone.

Sampled token_count rate_limits keys include limit_id, limit_name, primary,
secondary, plan_type, credits, individual_limit, spend_control_reached and
rate_limit_reached_type. They contain no current account identity. Header
creator_account_id identifies creation, not necessarily the account at a later
quota observation; it is not used to attribute quotas. Until a quota event
provides explicit account_id, return account_unverified. This is an intentional
unsupported provenance gap on the inspected writer, not evidence of zero usage.

Official protocol source inspected:
https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs .
Rollout internals are version sensitive; fixture compatibility is bounded to
observed session_meta/event_msg shapes, with unknown records ignored.

Codex upstream `SessionMeta.creator_account_id` explicitly says "Never updated
on resume" (protocol.rs, inspected current main lines 3284-3286). This confirms
it cannot safely attribute a later quota observation. Fixture account_id quota
events exercise a future explicit provenance extension only, **not** an observed
current-writer capability. Default local Codex limits stay unavailable until
such provenance is supplied upstream. No login/JWT read was added to bypass it.

Codex bounds: inspect eight UTC dated session directories, at most 4,096 directory
entries per day and 64 rollout files; read at most 128 KiB header + 256 KiB tail
per file. No archived session traversal. This deliberately partial scope may
omit older long-lived runs or starts outside the tail. Explicit completions can
stand alone with null startedAt; stale unmatched starts never count as running.

## Low-limit alert verification

Python fixtures verify integer/off validation, legacy settings reads, fresh-check
selection, per-account/window/reset durable deduplication, threshold changes,
source preference, stale/expired suppression, and reserve/release/claim. Legacy
v2 notification routes retain their old event dialect. Linux native-consumer
fixtures validate the new DTO and panel-only click; no real OS banner was sent.
The new fixed D-Bus panel action carries no URLs or agent controls.

An archived checkout at commit acd4dc7 was sent over the supplied SSH alias to a
new `/tmp/nagi-direct.*` directory on the Mac. `swift build` succeeded and
`bash test.sh` passed 25 tests across seven suites, including low-limit decoding,
copy and reserve/claim/release. No Swift source changed after that archive.
The installed application, Application Support and reader service were untouched.
This is compilation and core delivery-rule evidence, not a delivered OS banner.

Final hardening also tests hook restoration after failed disconnect storage,
uses a monotonic in-process Claude poll floor in addition to the durable dated
backoff, and excludes SDK-marked Claude hooks even if an entrypoint is overridden.
Official Notification types additionally support elicitation questions and
responses without storing message/title content; idle notifications are not asks.

Remaining qualification: parent frontend integration and different-model review;
real native OS banner/click journeys; macOS Keychain use (fallback/missing cases
are fixtures); real Claude lifecycle hooks (only temp-home fixture installation
was permitted); Codex's current-writer quota account-provenance gap described above.

## Cursor beta — fixture-only, 13 November 2026

The owner approved the Cursor source, but **no Cursor is installed on the Linux
machine or the Mac in the supplied research inventory**. This implementation did
not inspect real credentials or the owner's existing `~/.cursor/hooks.json`, and
did not install, connect, sign in, refresh, contact usage-summary, or send an OS
notification. All Cursor runtime behavior below is tested with **fake fixtures in
a temporary HOME**. Documentation verification is not provider acceptance.

The copied research is `design/cursor-research.md`. Binding revision 3 was committed
first as `0d38197`, on `nagi/cursor-source` from `nagi/limit-alerts` at `c6ab6d3`.
This is a stacked draft over PR #9 (over #8 and #7); no other branch is modified.

Official hooks reference rechecked: https://cursor.com/docs/hooks . Its documented
`subagentStart` is a **permission hook**, not a passive notification: invalid or
missing JSON on exit 0 can block spawning; its output describes allow/deny. Nagi
therefore does **not install subagentStart**, preToolUse, or before-shell/read
hooks and emits **no approval decision**. Lineage capability is false/unsupported.
A supplied subagentStart fixture preserves explicit parent_conversation_id only;
this proves the sanitizer's mapping, not a working installed lineage journey.

Installed observer events produce no output or model/context changes. Prompt
submission clears prior-turn evidence but never proves execution. Recent post-tool,
response/thought/edit observations can make a running row. Stop removes the matched
generation without asserting final completion; later activity can reappear after
auto-continuation. No asks-you or stuck claim. Silence drops rows after 15 minutes,
never turns them idle. Missing baseline/events remain unavailable/partial.

Fixtures cover atomic install/remove, unrelated-hook preservation, file modes,
private three-backup retention, failed registry commit rollback, failed disconnect
rollback, failed atomic replacement, post-replace sync rollback, concurrent owner
edits, silent malformed/oversized/slow-stdin behavior, bounded lock wait and log
rotation. Sanitizer output excludes prompts, responses, file/shell contents,
account emails, model, transcript paths and full workspace paths.

Credential fixtures cover XDG CLI auth, malformed/missing/expired JWTs, injected
Keychain success/failure and IDE fallback. SQLite opens only mode=ro&immutable=1,
queries only cursorAuth/accessToken, and creates no sidecars in the fixture.
Encrypted cursor-safe-storage:v1 values return cursor_login_invalid; no decrypt
or unlock is attempted. The macOS helper uses SecItemCopyMatching with
kSecUseAuthenticationUIFail in a two-second bounded reader subprocess. Its native
Keychain behavior is **not live-verified**; the reader tests inject its result.
The token crosses only a private bounded stdout pipe to the reader, never argv,
environment, persisted files, DTOs, notifications or surfaced exceptions.

HTTP fixtures cover the fixed host/path and session cookie, 401, 429, redirect and
5xx rejection, successful parsing and sanitized transport errors. Usage fixtures
cover percentages (including 0.36 meaning 0.36 percent), explicit used/limit or
remaining/limit, consistency and numeric validation, billingCycleEnd expiry,
300-second force/restart floor, bounded backoff, and suppression of old quotas
after a failed login. Generic Cursor 1 / Month goes through the existing
source-qualified low-limit dedup/reserve/release/claim flow. Linux native-consumer
fixtures confirm panel-only clicks; real OS delivery remains untested.

**Overlap is unresolved.** No verified T3-vs-standalone Cursor discriminator was
established in the documented hook payload/environment. T3-hosted Cursor may
appear under both selected sources. There is no title/path/time heuristic or
aggregate count. No claim of overlap prevention is made.

### Real-user qualification before release

1. Review the owner's hooks without logging their contents; connect on an actual
   Cursor IDE and CLI build, compare every unrelated entry/mode, inspect the Hooks
   output channel, and confirm prompts/tools/subagent spawning are unchanged.
2. Exercise prompt submit, a run with only model output, tools, cancel, stop with
   another hook's auto-continuation, new generations, window close, missed events,
   and 15-minute silence. Check that no idle/completion/asks-you claim is invented.
3. Verify the installed build emits the observer names and expected IDs/version;
   Cursor's docs currently provide no passive subagentStart. Lineage stays disabled
   until a safe documented signal exists and is version-qualified.
4. With owner-authorized sign-in, compare Cursor 1 / Month and reset against the
   actual account dashboard. Modern weekly subscriptions/multiple plan pools may
   not fit this private monthly usage-summary shape; do not infer their allowance.
5. On macOS verify an already-accessible Keychain entry reads silently; a locked
   or denied item must never prompt. Test IDE credentials, encrypted rejection and
   WAL lag. Immutable reads may miss a just-written login until Cursor checkpoints.
6. Run the same conversation through T3's cursor driver to establish overlap and
   seek a real discriminator. Verify low-limit banner and click with real native
   consumers, including once-only behavior after restart, then disconnect and
   confirm all Nagi hook entries and source logs are removed.

### Frontend handoff to Opus (web ownership preserved)

- Add Cursor icon and beta badge; copyKey cursor_direct, this-computer-only mode
  hooks, empty options. Consent requirements cursor_hooks_opt_in and
  cursor_usage_opt_in must be shown before connect, with passive hooks and existing
  login usage reads described separately.
- Suggested catalog copy: "Local agent activity and monthly limits. Beta."
  Coverage copy: "Recent activity only. Child-agent links and requests for you
  aren't available." Mention the possible T3 overlap where sources are selected.
- Limits must iterate provider cursor and render Cursor 1 / Month. Missing login:
  "Sign in to Cursor to read limits." Expired: "Sign in to Cursor again to read
  limits." Invalid: "Cursor's saved login couldn't be read. Encrypted logins aren't
  supported yet." Don't promise that signing in fixes an encrypted format.
- No pair/port/URL/token fields, no Cursor deep links, no supported-lineage badge,
  no complete-empty roster reassurance. Existing web tests passing do not verify
  a Cursor wizard/render; those files remain owned by Opus.

### Cursor verification readback

Implementation commit **e2ad21b27a11a2aa167df60bf3f99cb3f4769b70**:

- `python3 -m pytest tests -q`: **310 passed**, including 13 Cursor fixture tests.
- `node --test tests/*.test.cjs`: **80 passed**. Existing frontend regression
  coverage only; no Cursor web implementation or rendered acceptance is claimed.
- `git diff --check`: passed; `web/*` diff from the base is empty.
- `git archive HEAD mac tests/tray-label-cases.json tests/project-identity-cases.json`
  was piped through `ssh <the Mac>` to a new temp directory
  `/tmp/nagi-cursor.UwWT4Z`. `swift build` passed and `bash test.sh` passed
  **28 tests across seven suites**, including Cursor notification decoding,
  panel-only click rules, provider-aware tray handling and the existing link
  policy. No application install or runtime changes. No source changed after
  the tested archive; this later evidence-only commit records the result.
- No configured CI workflow or installed gitleaks/trufflehog scanner was found
  in this checkout/tool PATH. No formal secret-scanner success is claimed.
  Only synthetic fixture credentials were written/read for this integration.
  Different-model review remains with the parent before marking the PR ready.

Read-only inspection of the installed T3 app's bundled server source additionally
found provider-cursor/CursorAgentSdk using an in-process SDK/createAgentPlatform.
No documented standalone-vs-T3 hook-origin marker was established by that
inspection. Shell-sandbox markers and T3 startup profiling settings are not
hook-origin attestations and were not repurposed as filters. Whether this SDK
actually fires user hooks still needs the real-user overlap check above.

## Codex sign-in follow-up — revision 4

The owner subsequently approved reader-only Codex sign-in access at wizard
Connect. [Sources API revision 4](sources-api.md#codex-sign-in--binding-revision-4-13-november-2026)
supersedes the earlier Codex no-login limitation above. No frontend, installed
runtime, Mac, other checkout, login mutation or token refresh is part of this PR.

Primary-source inspection pinned upstream `openai/codex` at
`69231e119bfca0b14453515e97d99688ce1c47c9`. `AuthDotJson` declares `tokens` and
optional `last_refresh`; `TokenData` declares `access_token` and `account_id`.
The backend client's `get_rate_limit_status` uses a GET, the ChatGPT path is
`/backend-api/wham/usage`, and headers include Bearer auth and
`ChatGPT-Account-Id`. Its generated `RateLimitStatusDetails` /
`RateLimitWindowSnapshot` types declare `primary_window`, `secondary_window`,
`used_percent`, `limit_window_seconds` and `reset_at`. Nagi reads only the two
included-usage windows. This is upstream-code evidence, not a successful live
provider response. No owner auth key names or values were intentionally inspected.

New fake fixtures cover private/no-follow file access, missing/invalid/expired
sign-in, JWT expiry, 401, 429, 5xx/redirect/error reduction, bounded responses,
account change during I/O, auth-change cutoff for rollout fallback, stable salted
account keys, matching T3 DTO mapping, minimum polls/backoff across force/restart,
API/fallback alert dedup, pending-alert retirement and cross-source alert election.
The suite isolates both HOME and inherited CODEX_HOME, and test transport is fake.

**Verification incident:** the first focused run occurred before the new test
isolation guard. It inherited the workstation CODEX_HOME and enumerated real
rollout paths (visible in two failed assertions). A connected-reader test could
also have opened real auth and attempted usage; that run was not instrumented to
prove or exclude either. No auth values were printed in its output. All subsequent
runs use the temporary-home guard. Do not describe the entire work session as
fake-only or claim that initial run established live authenticated acceptance.

Current T3 provider instance ids cannot be joined to ChatGPT accounts without
additional evidence. Both source-qualified Codex lines remain. For duplicate
prevention, opted-in direct Codex owns local alerts even during an outage; other
local T3 Codex accounts remain visible but cannot alert while it is connected.
Legacy passive Codex connections do not suppress T3 alerts. This conservative
tradeoff and the unimplemented frontend consent/reason copy are release risks.
Independent cross-model review and live endpoint acceptance remain outstanding.

Verification after isolation: `python3 -m pytest tests -q` passed 313 tests;
`node --test tests/*.test.cjs` passed 80 tests. After the final binding-type
hardening, the focused Codex/Claude/alert suite passed 44 tests. `git diff --check`
and Python compilation passed. No dedicated secret-scan executable is installed;
credential non-export is covered by synthetic leak-sentinel assertions and code
inspection, not a claim of a completed external secret scan.
