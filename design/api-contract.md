# Nagi API v2 — agents and limits

Agreed scope: two questions only: what this computer's T3 agents are doing, and
whether subscription limits are close. `/glance` is primary. `/overview` is a
compatibility alias for the SAME glance, not a dashboard/history view. Linux is
implemented first; Mac native v2 integration is deferred. No Company, OpenBot,
GitHub, Needs-you, harness or legacy Progress Desk API is served.

## Transport and auth retained

Python 3.11+, stdlib only. Bind 127.0.0.1; exact Host/Origin and fetch metadata;
Linux client socket UID must match the reader (unresolved ownership =>403).
Every API requires existing native mutual HMAC proof or an unexpired random
`X-Nagi-Session`. Install secret never goes on the wire. Public static assets carry
no private records. Existing `/auth/challenge`, `/auth/launch`, `/auth/redeem` shapes
and native session recovery remain. Launch targets are `/glance` and `/overview`
only. Sessions expire after 900 seconds; only native code mints 10-second one-use
tickets. Challenge store evicts oldest at 128; sessions/tickets retain their caps.
All responses no-store, nosniff and no-referrer; no CORS, credential URLs or cookies.
No upstream tokens, raw errors, prompts, transcripts, tool arguments/output,
credential fingerprints, email, workspace filesystem paths or hostnames reach DTOs.
401 = missing/invalid/expired owner auth; 403 = origin/peer policy; 400 = invalid
JSON/settings; 404 = retired/unknown route or unexpected query; 405 = unsupported method;
413 = excessive body. None of the routes can control T3 or another source.

## Common outcome object

Every source object has EXACT common fields, followed by the data specified below:
`{status, attemptedAt, checkedAt, reason, data}`.

- `status`: `ok | quiet | unavailable | last_known | not_set_up | unsupported`.
- `attemptedAt`: current timezone-qualified UTC ISO attempt time (never source time).
- `checkedAt`: last successful check time, or null. For last_known it stays dated.
- `reason`: null on fresh success, otherwise a closed reason code from the route.
- `data`: successful DTO, a dated cached DTO for last_known, otherwise null.

`quiet` is a successful complete empty observation, not missing. `unavailable`
means configured but unreadable/unreachable/invalid with no usable cache.
`last_known` is a successful prior observation retained after failure; it is never
live and generates no new notification. `not_set_up` means this computer lacks
selected policy/paired reader or provider installation. `unsupported` means the
source/platform/account cannot supply the requested measure. Failed attempts do
not replace successful timestamps or cache. Source outcomes use HTTP 200; auth,
validation and internal durable-store errors retain HTTP error status.

## GET /api/glance

Response EXACT shape:
`{version:2, platform:linux|macos|unsupported, checkedAt:ISO,
 agents:<outcome>, settings:<settings DTO>, warnings:[<storage warning>]}`.
Agents reason: `not_configured | cannot_reach_t3 | invalid_source | protocol_unsupported | checking | cyclic_lineage`. `checking` is the initial,
unavailable snapshot while the first background poll is in flight.
Agent data: `{environmentId:string, projects:[project], ended:[project],
 counts:{running:int,waitingOnYou:int,stuck:int,ended:int},omittedRows:int,warnings:[]}`.

Project: `{id:string,title:string,agents:[agent]}`. Projects and siblings sort by
case-folded title, then id. All selected local projects appear only if they have
active work, active descendants or recently ended work. Data is bounded at 512
projects, 4096 supplied threads. Request omitOlderSettled=1 so T3 bounds settled
coverage (currently newest 25 top-level settled rows plus ties/required ancestors).
The ended window filters these source-retained rows; it is not a historical paging
guarantee. Malformed/orphan/duplicate rows are isolated and counted in omittedRows;
data.warnings contains rows_omitted whenever that count is nonzero. An outcome with
omissions is ok with an explicit warning, never quiet, even if no retained row is
currently active/ended. Intentional deleted/out-of-window filtering is not an omission.
An invalid envelope remains unavailable.

Project icon (additive, 13 Nov): each project in `projects` and `ended` also carries
`icon`, T3's own project icon in T3's precedence:
`{kind:"monogram",text,color} | {kind:"emoji",emoji} | {kind:"lucide",name,color}` (a
validated projectIcon override; colour from T3's 18-name enum; legacy lucide overrides with
monogram text are monograms; unknown kinds are ignored), else `{kind:"favicon",key}` (an
opaque 32-hex key for T3's automatic favicon), else `{kind:"auto"}` (the panel derives
T3's monogram and colour from the title). No workspace path or favicon path ever appears.

GET `/api/project-icon/<key>` (owner-authenticated) returns that project's favicon bytes, or
404 when there is none. The reader asks T3 through `assets.createUrl` with a
`project-favicon` resource only (orchestration:read; never workspace-file, media-file or
draft-workspace-file), treats T3's `project-favicon-missing` marker as no favicon, and
fetches the signed same-origin `/api/assets/` path without the bearer token. Bodies are at
most 256 KB, typed png, jpeg, webp, gif, x-icon or svg+xml, and must match their magic
bytes. Every response is no-store and nosniff; its CSP is
`default-src 'none'; style-src 'unsafe-inline'; sandbox`, so an SVG can never run as a
document. Results are cached for T3's 30-minute signing bucket; an unreachable T3 is retried
after a minute and never cached as a miss. The glance page's CSP adds `img-src blob:` for
the object URLs it makes from these authenticated fetches.

Agent EXACT shape:
`{id,projectId,parentId,title,state,provider,model,runId,startedAt,lastActivityAt,
 endedAt,endedAtSource,waitingOnYou,stuck,liveness,contextOnly,links,children}`.

- IDs are nonempty opaque text <=512 chars, not necessarily UUID. Parent must be a
  same-project thread; missing/cross-project parent =>null; cycles reject snapshot:
  a cyclic (or deeper than 64) lineage is never detached; agents become last_known
  (the dated prior snapshot) or unavailable, with reason cyclic_lineage. Limits from
  the same read still stand.
- title: normalized plain text <=180, fallback "Untitled thread"/"Untitled project";
  provider/model: normalized plain text <=120 or null. Collapse whitespace, strip
  bidi controls and U+2028/U+2029, cap with an ellipsis. IDs remain strictly validated.
  Provider/model are never inferred
  from hostname. T3 modelSelection is projected, not copied wholesale.
- state: `queued | preparing | starting | running | waiting | completed | failed |
  interrupted | idle`. `cancelled`/`rolled_back` normalize to interrupted.
- runId: source latest run id or null; startedAt/lastActivityAt/endedAt: ISO or null.
  lastActivityAt uses the event-driven thread updatedAt, not polling time. For a
  failed row lacking latestRunCompletedAt, endedAt falls back to updatedAt.
  endedAtSource is latestRunCompletedAt | updatedAt | null, qualifying that fallback.
- waitingOnYou: `{question:boolean,approval:boolean,blocking:boolean}` derived only
  from pending runtime-request metadata. A waiting state alone is not a request.
- stuck: boolean or null. Null means insufficient evidence; no alarm is allowed.
- liveness: `recent | inactive | child_wait | waiting_on_you | unknown`.
  Running and aged past stuckMinutes * 60 seconds =>stuck only when a successful bounded
  detail confirms no open tool. History truncation alone does not imply unknown: current-run coverage is enough.
  Coverage requires the run's initial user message/item or a contiguous visible
  window reaching its start; historical run metadata alone is not proof. Fetch
  at most three additional history pages, 2000 items, 4 MiB and eight total seconds
  per candidate to cover the current run. Inconsistent snapshot sequences, opaque
  compact/deferred evidence or exhausted budget =>unknown. T3 execution item types are command_execution,
  dynamic_tool, subagent, file_change, file_search, web_search and compaction. Any
  unfinished running/waiting item (including an unknown type) yields unknown. Open tools,
  blocking child waits and human requests suppress stuck. A genuinely hung silent
  tool cannot be distinguished from a legitimate long tool by this contract.
- contextOnly: true for an otherwise inactive ancestor needed to group active
  descendants. Its state/times remain source values; it does not add active counts.
- links: `{desktop:"t3code://threads/<encoded env>/<encoded id>",
  web:"https://app.t3.codes/threads/<encoded env>/<encoded id>"}`. No query/fragment.
- children: recursive same agent shape. Never drop sub-agents because they have a
  parent. A parent can appear as context in active/ended groups; counts count each
  actual included active/ended id once, excluding contextOnly rows.

Active = queued/preparing/starting/running/waiting plus required ancestors.
Ended = completed/failed/interrupted with the qualified endedAt within
endedExpiryHours (failed rows fall back to updatedAt), including archived shells when supplied. Older unsettled failures
are excluded. No history beyond that adjustable, collapsed group. Fresh empty
active+ended =>quiet. last_known keeps rows dated, sets no live claims or alarms.

## GET /api/limits

`{version:2,platform,checkedAt:ISO,providers:{codex:<outcome>,claude:<outcome>},
 machine:<outcome>}`. Provider data: `{accounts:[{id,label,windows:[window],secondaryWindows?:[window]}]}`.
Each provider outcome also has warnings:[] of codes invalid_account, invalid_window,
duplicate_window, unexpected_window or account_unavailable; one bad provider/account/window never
invalidates the other provider. Account ids are T3 provider instance IDs; labels are generic provider names plus
a one-based account number. Custom display names and emails are excluded. Provider reason: `not_configured | not_installed | cannot_reach_t3 |
 probe_failed | windows_missing | account_unsupported | stale_source | invalid_source | checking`.
Accounts (additive, 13 Nov): each installed, enabled account keeps its own line and adds
`status: ok|last_known|unavailable|unsupported`, `checkedAt: ISO|null` and `reason: null|code`.
When one account's probe fails while another succeeds, the provider stays ok, adds the
warning account_unavailable, and the failed account carries its own dated last-known
windows (unexpired only, from its own cache, keyed by instance id) or an empty unavailable
line. Labels number this computer's installed accounts in order, so `Codex 2` stays
`Codex 2` whichever account fails. A whole-provider last_known outcome marks every retained
account last_known with its own checkedAt.
Window: `{id:string,label:string,kind:five_hour|weekly|monthly|other,
 remainingPercent:number 0..100,resetsAt:ISO,checkedAt:ISO}`. IDs come from T3;
never deduplicate by duration. Account windows are the headline list (at most two):
Claude five_hour/seven_day; Codex primary/secondary, in that order. Optional account
secondaryWindows contains Claude seven_day_<model> windows with normalized labels.
Unexpected, malformed or duplicate IDs are skipped with a provider warning. Missing
or reset-less windows are absent, never zero. No usable windows =>unavailable or
unsupported, not quiet. Model-only windows may appear with empty headline windows.
Provider timestamps are T3 quota check times; attempts
remain current. Reject observations over 15 minutes old as stale_source; retain only
still-unexpired last-known windows, marked dated. No provider configured/installed
on this computer =>not_set_up. API-key accounts with no subscription windows =>
unsupported. T3's provider snapshot is read through a five-minute Nagi config cache; 20-second
polls never repeat config discovery, including after a failed config attempt. The
inspected protocol's server.getConfig has no deferNetworkDiscovery option; the
bounded five-minute cache refill can perform T3 discovery. No unsupported option
is sent, and no refresh/login/secret reload is called. Quota checkedAt is never
freshened by reading a cache.

Machine data: `{cpuPercent:number|null,memoryUsedBytes,memoryTotalBytes,
 diskFreeBytes,diskTotalBytes,uptimeSeconds}`; bytes/time nonnegative. This is a
footnote only. Linux /proc and existing Mac metrics retained, unsupported elsewhere.
Machine readings failing do not blank subscription limits. No process/hostnames.

## GET /api/settings; POST /api/settings

GET: `{version:2,settings:{endedExpiryHours:24,stuckMinutes:15},
 defaults:{endedExpiryHours:24,stuckMinutes:15},warnings:[]}` before customization.
`settings` contains current effective values; `defaults` always contains the
factory values. `/api/glance.settings` contains just the effective values.

POST exact JSON `{endedExpiryHours:int,stuckMinutes:int}` replaces both values.
Validate types first: booleans, strings, nulls, fractional numbers, missing and
unknown keys are 400; no partial write. Clamp integer endedExpiryHours to **1..168**
and stuckMinutes to **5..120**, inclusive, before persistence. Return the same GET
shape with normalized values, so the UI reflects any clamping. Duplicate keys,
nonfinite numbers, origin/peer/auth denials retain the common error outcomes.
POST is the write method; PUT remains 405 after owner authentication.

Atomic 0600 `nagi-settings.json` persistence under the shared per-machine data dir.
No restart: a successful POST invalidates the poll throttle; the next feed check
or background poll (normally within 20 seconds) projects grouping and liveness
using the new values. The running notifier consumes those resulting transitions,
without a separate preference cache. Lowering a threshold may produce the first stuck event immediately for an existing
silence that crosses the new threshold. The persisted run/activity silence key
prevents repeated banners after any later threshold change. Preferences never
rebaseline or consume an otherwise unreported transition.

Files from the earlier v2 implementation with exact legacy keys
`stuckAfterSeconds`/`endedWithinHours` are interpreted on read: seconds round up to
minutes, then the new bounds apply. Legacy API write keys are refused. Reading
performs no migration write; the next authorized POST persists the new shape.
These are local preferences, not agent records. No source records, T3 settings,
provider credentials or agent controls are changed.

## Recoverable local-state warnings

Settings, glance and notifications responses include `warnings:[]` or storage codes:
`settings_invalid` means the private settings file was unreadable/unsafe/invalid,
so current settings fall back to factory defaults. `journal_reset` means the local
transition journal was unreadable/invalid and was rebaselined; old pending delivery
cannot be recovered. Source feeds continue. A valid authorized settings POST repairs
owner-owned regular preference/journal files atomically to 0600 and clears warnings.
Foreign files, symlinks and unsafe lock paths are never overwritten. No raw paths,
file contents or exception text are returned. Vanished thread conditions expire
seven days after last sighting; migration starts that clock for old undated entries.

## Notifications: reserve, confirmed send, claim or release

GET `/api/notifications` returns
`{version:2,checkedAt:ISO,events:[event],warnings:[]}`. Pending failed/stuck records,
newest last, maximum 256, expire after 24 h. Future-stamped events caused by a
backward clock step are retained but not offered or claimed until time catches up. Live-reserved events are hidden.
Event exact shape: `{id:64 lowercase hex,kind:failed|stuck,threadId,projectId,
 threadTitle,projectTitle,occurredAt:ISO,links:<same closed links>}`.

All following routes are owner-authenticated, same-origin JSON POST:

- `/api/notifications/reserve`, exact `{id}` returns
  `{version:2,reserved:boolean,lease:null|{reservation:<43 base64url>,expiresAt:ISO,event}}`.
  Atomic persisted reservation lasts 30 seconds; one consumer wins. Expired leases
  recover on restart. This is not a delivery claim.
- `/api/notifications/claim`, exact `{id,reservation}` returns
  `{version:2,claimed:boolean,event:event|null}`. Native code calls this ONLY after
  a successful desktop DBus reply. Matching live lease is required; repeated,
  mismatched or expired claims return false/null. Confirmed claims survive restart.
- `/api/notifications/release`, same request, returns
  `{version:2,released:boolean,event:event|null}`. Failed/rejected sends release
  their lease so the event remains pending for a later poll. No send =>no claim.

The Linux installer prepares `~/.local/share/applications/local.nagi.notifications.desktop`
idempotently. Gio uses stable application ID local.nagi.notifications. GNOME sends
use the acknowledged org.gtk.Notifications.AddNotification call; other desktops use
acknowledged freedesktop Notify. Public Application.send_notification is avoided
because it discards errors. GTK actions remain on the main loop; callbacks not
started before their bounded wait are cancelled. Banners open closed desktop thread
links, web fallback. A single stable app.open-thread action accepts the validated link as its string
target, so old banners work after restart. The installer prepares matching
~/.local/share/dbus-1/services/local.nagi.notifications.service; D-Bus activation
starts the notifier and registers that action even while the tray is closed.
Missing desktop entry/bus, permission errors and rejected sends retain pending events.
No real installation/activation or OS banner acceptance is claimed by fixture tests.

The reader polls every 20 seconds without holding its shared state lock during T3
I/O. Settings/claims remain usable; an obsolete in-flight poll is discarded after a
settings change. A malformed source cannot terminate the refresh loop. Baseline
startup does not replay existing failures. A newly failed row with missing completion
evidence uses its qualified updatedAt fallback; up to five seconds of source
clock skew is accepted. Stuck delivery is keyed to run ID plus last activity, so one
silence cannot repeat when thresholds change; genuine new activity resets that key.
Threshold edits never swallow a first transition. No source loss/unknown liveness alarm.

Delivery has an unavoidable desktop/local-store crash boundary: a process can die
after desktop acceptance and before the durable claim. A retry may replace/re-show
the same event (GTK uses the stable event ID); freedesktop may show another banner.
No exactly-once OS guarantee is claimed. Confirmed durable claims are never resent;
reservations prevent concurrent sends, and explicit rejection is always retryable.
Mac native delivery remains deferred and must use this revised protocol later.

## Local T3 policy, custody and compatibility

Owner-only `<shared data>/nagi-t3.json`:
`{version:1,origin:"http://127.0.0.1:3773",credentialFile:"/absolute/private/file"}`.
Credential file exact `{token:string,scopes:["orchestration:read"]}`, 0600, same owner.
The key set stays exact (no mode field); the origin's class decides the transport:

- `http://127.0.0.1:<port>`: this computer's T3. Linux checks the listener's socket
  UID before any credential is sent (unchanged).
- `http://<IPv4 in 100.64.0.0/10>:<port>`: one Tailscale CGNAT address, carried
  inside WireGuard. No peer-UID check (there is no local socket owner to match).
- `https://<name>.ts.net[:port]`: TLS with normal certificate and hostname checks.

Anything else is refused before the credential file is read: other hosts or
schemes, any path, query, fragment or userinfo, IPv6, an http hostname, uppercase
or non-ASCII names. Redirects are never followed. server.getConfig uses the same
origin over ws:// (wss:// for https). This is how a Mac reads the Linux machine's
T3 server over Tailscale with its own read-only token; the token is minted on the
Linux host and moved into the Mac's credential file without being printed.
No auto pairing, token inspection/display, broader scope or DB read. A token is consumed opaquely by the HTTP transport, never exposed in DTOs,
logs, fixtures or committed files. Install/activation/pairing remain separate.
The source adapter accepts protocol 2 only, bounded read-only HTTP paths and only
server.getConfig over WebSocket (through the five-minute cache). No generic RPC proxy or control route exists.

The minimal placeholder is a new isolated glance asset; existing web/ visuals and
old source assets remain untouched and are not routed. Auth bootstrap asset is
reused. The reader's prior owner auth, shared resolver and installers are retained.
Retired module deletion requires an external caller audit; retained compatibility
writers may remain on disk but cannot restore their old HTTP routes in this app.

Implementation bounds: at most 512 projects, 4096 thread shells and 8 MiB per T3
response. Up to 32 aged running threads get bounded liveness checks per poll;
others have unknown liveness and do not alert. Streaming or omitted/truncated
turn evidence is unknown. Source HTTP and WebSocket exchanges each have an eight-second total deadline, including
connect,
upgrade headers and partial frame reads, enforced by a socket shutdown timer. Both
HTTP and WS JSON use strict size/depth-limited decoding; RecursionError is contained. Linux checks the connected T3 server socket UID before sending
its opaque paired credential; a foreign/unresolved listener receives none.

## Auth exchange shapes (retained)

All POSTs require `Content-Type: application/json` and `X-Progress-Desk: 1`;
body is 1..4096 bytes. Public means no owner proof, still subject to all
Host/Origin/fetch/UID checks. Duplicate/unknown JSON keys are rejected.

- Public POST `/auth/challenge`: exact
  `{nonce:<43 base64url chars>,method:GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS,
  path:<exact ASCII request target, no fragment>,bodyHash:<64 lowercase hex SHA256>}`.
  Returns `{instance:<43 base64url>,serverNonce:<43 base64url>,proof:<64 hex>}`.
  Verify server HMAC before issuing any credential or private request body.
- Native POST `/auth/launch`: exact `{path:"/glance"|"/overview"}`. Requires
  `Authorization: NagiProof <instance>.<clientNonce>.<serverNonce>.<64hex>`;
  browser session headers cannot mint a ticket. Returns
  `{url:"http://127.0.0.1:<port>/<view>#nagi-launch=<43 base64url ticket>"}`.
  Ticket capacity 64; exhausted live capacity =>503.
- Public POST `/auth/redeem`: exact `{ticket:<43 base64url>,path:<view path>}`.
  Successful one-use redemption returns `{token:<43 base64url>,
  expiresAt:<Unix seconds>,fragment:""}`. Expired/used/mismatched ticket =>401;
  session capacity 128 =>503. GET/HEAD never redeem. No Set-Cookie.

Proof is HMAC-SHA256 using the ASCII install secret as key, over UTF-8 newline
joined `domain,origin,instance,clientNonce,serverNonce,method,path,bodyHash`.
Domain is `nagi-server-v2` then `nagi-client-v2`; origin includes the actual port.
Challenge expires after ten seconds and is consumed by the authenticated request.
`X-Nagi-Session` contains the redeemed random token; its 900-second lifetime is
absolute. API requests with duplicate/conflicting credentials fail 401. No API
accepts raw Bearer install secrets. Reuse web/nagi-auth.js for bootstrap and
native reauthentication signalling; do not implement JavaScript session renewal.

### Cache compatibility after final review

Old agent display caches gain default omittedRows/warnings/endedAtSource fields
when returned as last_known. Old quota cache rows lacking source window IDs/labels
are not projected into the new contract: they remain unavailable until a fresh
supported read, without inventing source IDs or resetting notification state.
Current-run paging uses only authenticated GET /threads/:id/history with opaque
encoded cursors; no transcript endpoint or generic RPC is added.

## Modular sources API (opt-in)

The phase 1 source envelope and owner-authenticated setup API are specified in
[sources-api.md](sources-api.md). These additional routes do not change any v2
DTO or the existing read-only glance/limits/notification routes above.
