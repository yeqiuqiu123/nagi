# Sources API v1 — phase 1 backend contract

Binding revision for the separately built wizard. This specializes
[sources-contract.md](sources-contract.md), phase 1. Existing v2 glance, limits,
settings, icons and notification DTOs/routes remain unchanged. No frontend or
non-T3 reader is included.

## Authentication and transport

All routes below are private, including catalog/schema/discovery. Reuse native
NagiProof or X-Nagi-Session; loopback bind, exact Host and optional same-origin
Origin, same-user peer, no cross-site fetch, cookies, CORS or redirects. POST
requires application/json and X-Progress-Desk: 1. Strict JSON (no duplicate keys,
nonfinite values, unknown keys), 1..4096 bytes; queries are refused. Responses
are no-store. A test is bound to the browser session or native owner instance.
Secrets must never appear in responses, logs or errors. Pairing input appears
only in the authenticated JSON body and transient private test memory, never URLs.

## Shared DTOs

Time = UTC ISO timestamp. Handle = opaque random base64url string (43 characters).
SourceId = 32 lowercase hex, except reserved `legacy-t3`. Revision = nonnegative
integer, initially 0. Flags exact keys: agents,lineage,limits,stuckDetection,
asksYou,deepLinks. Coverage exact keys agents,lineage,limits,asksYou,stuck,deepLinks;
values complete|partial|unsupported|unverified|account_dependent (last only limits).
T3 flags are all true; coverage complete except limits account_dependent.
SourceTag = {id,harness:"t3",label,placement:"local"|"tailscale"}.
Outcome and ProviderOutcome are existing v2 DTOs, with all six truth states;
`checking` is unavailable with null checkedAt/data. Last-known dates do not advance.
SourceRead = {source:SourceTag,capabilities:Flags,agents:Outcome,
 limits:{codex:ProviderOutcome,claude:ProviderOutcome},coverage:Coverage,warnings:[]}.
No origins, hostnames, addresses, paths or secret references in these DTOs.
Source-supplied project/agent titles remain sanitized v2 metadata.

## Read endpoints

- GET /api/sources/v1/catalog → {version:1,harnesses:[{id,displayName,iconKey,
  available:boolean,status:"available"|"coming_soon",capabilities:Flags,copyKey}]}.
  Order: t3,openbot,pi,omp,codex,claude,hermes,openclaw,opencode. Only T3 available;
  others have false effective flags. Copy keys: t3_protocol2,
  openbot_export_required,pi_sidecar_required,omp_pi_family_planned (oh-my-pi, a
  Pi-family entry added 13 Nov),codex_passive_limits_planned,
  claude_sidecar_required,hermes_scoped_export_required,
  openclaw_scoped_gateway_required,opencode_versioned_adapter_required.
- GET /api/sources/v1/schema/<harness> → {version:1,harness,available,modes,
  capabilities,requirements}. T3 mode protocol2, requirements [read_only_pairing];
  others modes [], requirements [coming_soon]. Unknown harness → 404.
- GET /api/sources/v1 → {version:1,revision,sources:[SourceRead]}.
- GET /api/sources/v1/glance → {version:1,dtoVersion:2,
  extensions:["nullable_links"],platform,checkedAt,sources:[SourceRead],
  settings:<v2 effective settings>,warnings:[<v2 storage codes>]}.
  Each source includes its own glance and limits. No global aggregate. Ordering
  is harness order, then label/id. No policy → sources []; legacy v2 still reports
  not_set_up. One failed instance retains its own dated cache only.

## Discover, test, connect, disconnect

POST /api/sources/v1/discover exact {adapterIds:[unique catalog IDs],
 placement:{kind:"local"}|{kind:"tailscale"}|{kind:"tailscale",peerRef:Handle}}.
Response {version:1,candidates:[{candidateId:Handle,harness,placement,
 peerRef:Handle|null,installed:"yes"|"no"|"unknown",running:same,readable:same,
 evidence:[binary_found|endpoint_found],expiresAt:Time}],
 peers:[{peerRef:Handle,label,online:boolean}],warnings:[tailscale_unavailable]}.
Warnings can be empty. Local discovery checks CLI/app locations and T3's known
3773 descriptor, never starts or pairs. Tailnet discovery runs only bounded
`tailscale status --json`; no port scan or SSH. Peer records expire after five
minutes. Owner-facing peer labels may be shown only in the wizard. Remote
candidates remain unknown until the owner tests that selected endpoint.

POST /api/sources/v1/test exact {configuration:{adapterId:"t3",label,
 placement:{kind:"local"}|{kind:"tailscale",peerRef:Handle},mode:"protocol2",
 options:{port:<integer 1..65535>},pairing?:<string>}}.
Label: normalized nonempty plain text, max 80 characters. For local, pairing is
forbidden; for tailnet, required. Remote origin is derived from the selected
peer's inventory IPv4; a direct HTTP(S) `/pair#token=...` link may instead select
that same peer's inventory address/DNS name and port. Also accept T3's wrapper
`t3code://pair?pairingUrl=<encoded pair URL>` and a bare bootstrap token. Current
T3 pairing codes are 12 characters from `23456789ABCDEFGHJKLMNPQRSTUVWXYZ`;
older opaque printable tokens of 16..3500 characters are also accepted. Reject other
origins, paths, credentials, queries, fragments and non-tailnet addresses before
any exchange. Never fetch a pasted link. HTTPS ts.net certificates are verified.
Response {version:1,testId:Handle|null,expiresAt:Time|null,capabilities:Flags,
 coverage:Coverage,agents:{status,checkedAt,reason},
 limits:{codex:{status,checkedAt,reason},claude:{status,checkedAt,reason}},
 requirements:[local_auto_pair|pairing_exchange|coming_soon],warnings:[]}.
Test reads the credential-free protocol-2 descriptor only; it does NOT mint or
exchange credentials. A successful descriptor test reports agents/limits
not_set_up, reason not_configured, with unverified coverage, and a two-minute
one-use testId. This intentionally specializes the earlier provisioned-secret
proposal: connect now performs explicit owner-authorized pairing. Unsupported
catalog entries return unsupported/protocol_unsupported with null testId.
Unreachable/protocol mismatch returns unavailable/cannot_reach_source or
unsupported/protocol_unsupported, no testId. Test does not persist or notify.

POST /api/sources/v1/connect exact {testId:Handle,expectedRevision:Revision} →
{version:1,revision,source:SourceTag,capabilities:Flags,coverage:Coverage}.
Local: fixed CLI `auth session issue --scope orchestration:read --label
'Nagi (read-only, this computer)' --ttl 365d --token-only --log-level none`,
matching the Mac setup helper (CLI or installed Mac app server entry). Output
is piped to a bounded private credential writer, never console/capture/logs.
Only default local T3 port 3773 is pairable (no profile/home override).
Remote: POST /oauth/token as application/x-www-form-urlencoded with
 grant_type=urn:ietf:params:oauth:grant-type:token-exchange,
 subject_token=<bootstrap>,
 subject_token_type=urn:t3:params:oauth:token-type:environment-bootstrap,
 requested_token_type=urn:ietf:params:oauth:token-type:access_token,
 scope=orchestration:read,client_label=Nagi (read-only),client_device_type=desktop.
Require Bearer, matching issued_token_type, positive expires_in and scope exactly
`orchestration:read`; any downgrade/upgrade/duplicate scope is rejected. Validate
an authenticated shell with the same environment identity as the tested descriptor
before saving. One commit lock covers revision, conflict,
consumption and pairing; simultaneous connects cannot mint twice. Duplicate origin
is 409/source_exists before mint. Failed pairing consumes testId, stores no source
and returns a closed error; retry requires a new test. No automatic retry after
uncertain issuance. Credentials are owner-only and separate from registry JSON.

POST /api/sources/v1/disconnect exact {sourceId,expectedRevision} →
{version:1,revision,disconnected:boolean}. Revision increments only on removal.
Unknown valid ID returns false. Retires that instance's pending delivery records,
stops future reads and removes its Nagi-owned credential; never revokes upstream
or deletes a legacy/external credential. Legacy v2 routes remain legacy-only.

Per-source pending notifications: GET /api/sources/v1/notifications →
{version:1,events:[{sourceId,event:<v2 event>}]}.
POST /api/sources/v1/notifications/reserve {sourceId,id}, claim/release
{sourceId,id,reservation}; responses identical to existing v2 reserve/claim/release
except version:1. Existing v2 notifications remain legacy-only. Source-local
journals and new notification hashes include structured source/environment/native
identity; legacy event IDs, leases, baseline and claims are preserved.

## Errors and client states

Wizard errors exact {error:<closed code>}: 400 invalid_request,
401 owner_required, 403 origin_denied, 404 not_found, 405 method_not_allowed,
409 test_expired|configuration_changed|source_exists|peer_expired,
413 request_too_large, 422 pairing_invalid|scope_mismatch|connection_failed|
local_pairing_unavailable, 503 storage_unavailable|capacity_reached.
Common existing auth/bootstrap errors retain their legacy strings. No upstream
body, exception, token, link or private network value is echoed. Busy network
operations remain synchronous: disable submit while pending; use returned truth
states, never optimistic live counts. A 409 requires refetch/retest. Keep pairing
input out of telemetry and clear it after submitting. Never automatically retry
connect. A server crash after upstream issuance may leave an orphan observer
session; no source is visible until atomic registry commit. Operator revocation
belongs to T3, not Nagi.

## Migration and custody

Without nagi-sources.json, an existing owner-only nagi-t3.json becomes the stable
in-memory legacy-t3 instance, using the same credential and journal unchanged.
Read performs no registry/policy/credential migration write. First authorized
registry mutation preserves that binding by reference, including notification
history. Registry and new credentials are 0600; credentials live in a 0700
source-secrets directory, no-follow and owner checked. No installed runtime,
installer behavior, native opener grammar, source controls or provider credential
changes are part of phase 1.

### Scheduling and aggregate bounds

At most 16 instances are configured. Source polling schedules independently with
four workers and at most four simultaneous T3 read calls. New instances have a
20-second total read deadline, including waiting for an I/O slot; legacy T3
retains its existing read budgets. Feed GETs return the current snapshot without
waiting on pending source I/O, so initial outcomes can be `unavailable/checking`.
The normal refresh interval remains 20 seconds per instance.

Source envelopes are bounded to 8 MiB. If necessary, the largest individual
agent/provider payloads are omitted, preserving every source tag and the other
measures/sources. Omitted measures become `unavailable/coverage_incomplete` with
null data; the affected source warnings and glance warnings include
`response_truncated`. Never turn truncation into quiet or zero counts. The
source-qualified notifications endpoint offers up to 256 events globally,
oldest first; other unclaimed events remain pending in their source journals.

## Phase 1 follow-up: manual addresses, ordering and Linux banners

The existing owner, origin, strict JSON, redaction, expiry and revision rules
apply unchanged. No new endpoint or secret-bearing response is introduced.

### Manual test configuration

`POST /api/sources/v1/test` additionally accepts exact:

```json
{"configuration":{"adapterId":"t3","label":"Computer 2","placement":{"kind":"manual"},"mode":"protocol2","options":{"port":3773},"pairing":"<T3 pairing link>"}}
```

For an address plus a bare pairing token, `options` additionally contains
`origin`, e.g. `"http://100.80.1.2:3773"`. `port` remains a required integer
1..65535 for consistency with the existing form. A pairing link carries its own
origin/port; its `/pair#token=...` wrapper is parsed, never fetched. The existing
`t3code://pair?pairingUrl=<encoded pair URL>` wrapper is accepted too. If both
`options.origin` and the link supply origins, they must identify the same
scheme/host/port or the request fails. A bare token requires `options.origin`.
Manual placement accepts no `peerRef` and does not depend on discovery/Tailscale
inventory being available.

Both explicit and link-derived origins pass the same `source_origin` validator:
HTTP to exactly `127.0.0.1:<port>` (Linux listener UID verified before any secret),
HTTP to canonical IPv4 in 100.64.0.0/10 with a port, or HTTPS to a lower-case
`*.ts.net` name with verified TLS. Reject other addresses, IPv6, alternate IPv4
spellings, userinfo, paths, queries and fragments on origins, including empty
query/fragment delimiters. Pairing links permit only the closed `/pair` path and
`token=` fragment; no redirects or arbitrary link fetching. Invalid/manual
origin or pairing input is 422 `pairing_invalid`; malformed DTOs are 400
`invalid_request`. No submitted address/token is echoed or logged.

The response is the existing test DTO. `requirements:["pairing_exchange"]` applies
to every manual connection, including loopback: it never auto-mints a local CLI
session. Connect remains exact `{testId,expectedRevision}` and consumes that
owner-bound tested target, exchanging for exactly `orchestration:read` before
publishing. SourceTag remains unchanged: manual loopback becomes placement
`local`, other accepted origins become `tailscale`. Neither raw address nor
`peerRef` enters glance/list/notification DTOs. Discovered-peer origin pinning
remains unchanged.

### Source ordering and notification upgrade

Both source list and glance order by catalog harness order, then label, then
source ID; ordering never interleaves harnesses solely because of labels.

The Linux tray and D-Bus-activated notifier use only
`GET /api/sources/v1/notifications` and its reserve/claim/release POST routes.
Every reservation and claim/release includes `sourceId`; reserve is exact
`{sourceId,id}`, claim/release `{sourceId,id,reservation}`. A malformed envelope or
source identity must never trigger a send. There is no fallback to the old feed
or separate client delivery journal. The existing `legacy-t3` instance uses the
same durable journal, IDs, leases and confirmed claims, so upgrading/restarting
or persisting the registry cannot replay a claimed legacy event. Only successful
acknowledged OS sends are claimed; failures release their reservation.
`local.nagi.notifications`, GTK event IDs, validated T3 open actions and D-Bus
activation stay unchanged. macOS native code is outside this change.

## Backend review hardening

Discovery performs bounded subprocess/probe I/O outside the service state lock;
feed snapshots, notifications and wizard state remain available during discovery.
An unsafe, wrong-mode or malformed legacy `nagi-t3.json` is omitted from the
implicit source registry (v2 still returns its original invalid-source truth).
It never disables the catalog or wizard, and is never repaired by a read.

The private registry additionally stores `environmentId` for newly connected T3
instances, validated against both the tested descriptor and authenticated shell.
Connect returns 409 `source_exists` for an already configured environment even
when origins differ (IP versus ts.net). Older entries without identity remain
readable; connect resolves their identity from an existing successful observation
or a bounded descriptor probe. Legacy comparisons resolve the current live
`nagi-t3.json`, not the registry's historical policy or identity. No additional
identity/address/secret field is added to source tags or wizard responses.
Mac setup leaves legacy policy and credentials alone whenever a sources registry
already exists; connection changes then belong to the owner-authenticated wizard.

Linux notification validation skips malformed items individually. It never sends
an invalid item, and valid events in the same bounded envelope remain deliverable.
Local pairing subprocesses receive only HOME, PATH, LANG, USER and TMPDIR; the
Mac app-server process additionally receives ELECTRON_RUN_AS_NODE=1. The pipe
writer also gets a minimal environment. NODE_OPTIONS, T3 home/profile overrides
and other reader environment values are never inherited.

Successful disconnect atomically unpublishes the selected source first, then
removes its private journal and source-specific lock under lifecycle exclusion.
Unlink operations do not follow symlinks or remove foreign-owned files. Other
sources' journals and the shared state lock remain untouched. Nagi-owned observer
credentials are deleted as before; external legacy credentials are preserved.
Queued reads and stale notification requests cannot recreate retired caches/locks.

Expired test records and their pasted bootstrap tokens are purged independently
of incoming traffic, using an autonomous deadline timer. Monotonic expiry also
bounds retention during a backward wall-clock step. Closing the service cancels
the timer and discards remaining test secrets; active connect operations retain
only the credential material needed to finish their already authorized exchange.

## Direct local sources — binding revision 2 (13 November 2026)

This revision supersedes the phase-1-only restrictions above for `claude` and
`codex`. The owner explicitly approved Claude OAuth usage reads and reversible
hook installation **only at connect**. All owner authentication, strict JSON,
revision, one-use test, lifecycle and private-store rules remain in force.
`web/*` is owned by the separate frontend implementer.

### Local wizard and private bindings

Discovery additionally accepts `placement:{kind:"this_computer"}` (the existing
`local` spelling remains accepted). Claude and Codex detection checks only their
known default data directories and PATH binaries, without credentials or startup.
Evidence adds `data_found`; running/readable remain unknown until observation.
Catalog copy keys become `claude_direct` and `codex_direct`; each adapter is
available when its corresponding implementation lands, never before.

Test configuration, with no pairing, port, path, token or secret reference:

```json
{"configuration":{"adapterId":"claude","label":"This computer","placement":{"kind":"this_computer"},"mode":"direct","options":{}}}
```

Codex uses `adapterId:"codex",mode:"rollouts"` with the same empty options.
Only this computer and the reader owner's default `~/.claude` / `~/.codex` are
supported. The server pins canonical roots privately. One connection per harness
and root is allowed. SourceTag permits `harness:"claude"|"codex"` and placement
`"this_computer"`; T3 tags are unchanged.

Test is credential-free and non-mutating. It checks readable metadata roots and
safe settings structure, returns a two-minute owner-bound testId, `not_set_up`
with reason `not_configured`, unverified coverage, and requirements
`["claude_hooks_opt_in","claude_usage_opt_in"]` or `["passive_rollouts"]`.
A missing root returns unavailable / `local_data_missing`, no testId. Connect's
existing `{testId,expectedRevision}` is the explicit opt-in. It saves a private
binding `{version:1,home:<canonical owner home>}` rather than origin/credentialFile.
No provider token is copied into that binding. Disconnect removes the binding,
source journal and only that source's Nagi hook commands; it never revokes login.
Hook installation/removal fails closed as 422 `hook_install_failed` /
`hook_remove_failed` and preserves the connected record on failed removal.
Settings must be an owned regular file, not a symlink; writes preserve all other
settings and hooks, use an owner-only backup plus atomic replacement, and compare
the original bytes before replacement. Registry failure rolls installed hooks back.
No setup write happens during discovery, test or background reads.

Capabilities (exact existing flag names):

| Harness | agents | lineage | limits | stuckDetection | asksYou | deepLinks |
| --- | --- | --- | --- | --- | --- | --- |
| Claude direct | true | true | true | false | true | false |
| Codex rollouts | true | true | true | false | false | false |

Both have partial agents/lineage coverage, unsupported stuck/deepLinks; Claude
asksYou partial, Codex unsupported, and limits account_dependent. These flags
mean supported observations, **not** a complete live roster. No aggregate count
across sources is introduced. Source links are `{desktop:null,web:null}`.

### Claude evidence and limits

The reader alone reads `Claude Code-credentials` from macOS Keychain using fixed
`/usr/bin/security` argv, a minimal environment and timeout, or the owned regular
`~/.claude/.credentials.json` fallback. Only `claudeAiOauth.accessToken`,
`expiresAt`, `subscriptionType`, `rateLimitTier` are inspected. No refresh. Expired
credentials or HTTP 401 produce unavailable / `claude_login_expired`; open Claude
Code to sign in. Missing login is `claude_login_missing`, malformed login is
`claude_login_invalid`. Raw exceptions and response bodies never escape.

GET `https://api.anthropic.com/api/oauth/usage` uses Bearer auth and
`anthropic-beta: oauth-2025-04-20`, fixed HTTPS host/path, no redirects or proxy.
The token never enters argv, environment, logs, Nagi files, DTOs or notifications.
`five_hour`, `seven_day`, `seven_day_*` buckets with finite 0..100 utilization
and future resets map to existing windows/secondaryWindows; labels are Session,
Weekly, Weekly · <model>. Account label is always Claude 1. Polling is at least
300 seconds even under force-refresh, with bounded exponential 429/5xx backoff.
Reasons add `provider_rate_limited`, `provider_unavailable`, `invalid_usage`,
`stale_source`, `windows_missing`. Checks date successful HTTP responses only;
the 900-second stale ceiling and unexpired-window rule still apply.

In the source glance, a fresh direct Claude limits outcome takes precedence over
**local T3** Claude limits (owner's approved preferred observation); suppressed
T3 measures become unsupported / `preferred_direct_source`, data null. A failed,
stale or disconnected direct source restores T3 immediately. Remote T3 remains
source-qualified. No account identity is inferred from titles, email or model.

Hook events: SessionStart/SessionEnd/UserPromptSubmit/Stop/SubagentStart/
SubagentStop/Notification/PreToolUse/PostToolUse. The stdlib sink always exits 0,
prints nothing, bounds stdin and lock wait, rotates 0600 JSONL in the Nagi data
dir, and emits only allowlisted sanitized metadata. Prompt, response, tool input,
notification text and transcript bodies are discarded. Use a neutral `Claude
session` title (or subagent type); hooks do not supply a trustworthy session
name. Never turn the first prompt into a title. The event records `titleSource`
so this choice is auditable. Explicit lifecycle starts/turn starts create rows;
Stop completes a turn, SessionEnd closes the session, tools update liveness only.
Permission-prompt notifications set asks-you; next tool/prompt/stop clears it.
No stuck claim from silence; absent recent liveness is unavailable rather than
an immortal running row. Pre-connect sessions and lost hook events are coverage
gaps, never an empty complete roster.

Overlap uses a real discriminator: T3's Claude launch environment sets
`CLAUDE_CODE_ENTRYPOINT=t3-code`; those hooks are discarded. Unknown SDK entrypoints
are excluded conservatively. Codex uses session_meta originator/source metadata:
T3 originators are excluded, unknown origins are omitted. Never match cwd/title/time.

### Codex evidence

Read only bounded metadata headers and tails of owned regular
`~/.codex/sessions/**/rollout-*.jsonl`; never sqlite/auth stores, CLI or app-server
startup. Explicit task_started/task_complete/turn_aborted events establish run
state and timestamps. A stale unmatched start is not live. Session metadata
supplies project basename/model and explicit subagent-source parent IDs; fork
parents are not concurrent lineage. Neutral title fallback avoids prompt content.
File-only coverage remains partial, with no stuck or pending-ask assurance.

Quota check time is the enclosing token_count event time, never mtime/poll time.
primary/secondary windows retain bucket-qualified IDs, finite utilization, future
resets and the 15-minute ceiling. One generic numbered account line requires an
explicit non-secret account identity in source metadata/events. A home or plan
alone is insufficient: missing/conflicting provenance is unavailable /
`account_unverified`, no current percentage. This intentional limit must remain
visible if the installed writer omits account identity.

### Low-limit events and settings (PR C)

Existing settings resources add `limitAlertPercent`: integer 1..50 or string
`"off"`, default 10. Old two-field files/requests gain the default; invalid types,
booleans and out-of-range alert thresholds are rejected. The same store and
owner-authenticated settings route are used.

Source notification events add an alternate exact shape:
`{id,kind:"low_limit",provider,accountId,accountLabel,windowId,windowLabel,
remainingPercent,resetsAt,occurredAt,links:{desktop:null,web:null}}`.
Only fresh successful account/window evidence at or below the threshold emits.
Identity is source/provider/account/window/reset; durable seen keys prevent replay
on restart or threshold change. Once per window/reset, through the existing
source-qualified reserve/claim/release flow. Stale, failed, cached or suppressed
provider observations cannot generate a new alert. Copy: `Codex 1 · 8% left ·
resets Mon 21:58` in the client timezone. Clicking opens Nagi's panel; it does not
launch or resume an agent. Existing failed/stuck event shapes remain unchanged.

Direct agent data warnings additionally permit `partial_coverage`, `rows_omitted`,
`stale_source` and `coverage_incomplete`; Codex provider warnings additionally
permit `account_unverified`. They are closed codes, not diagnostics. Low-limit
reset identities canonicalize the reset instant to UTC so equivalent `Z` and
`+00:00` spellings cannot create another alert. Corrupt/recovered journals suppress
new low-limit alerts until the existing settings-repair path restores custody.
Pending low-limit alerts expire at their reset or after the quota freshness
ceiling. `off` and a newly preferred direct source also suppress reservation;
legacy v2 list/reserve/claim/release never expose or mutate low-limit events.


## Cursor — binding revision 3 (13 November 2026)

This revision adds the owner-approved local Cursor beta source; revision 2 and
all T3/Claude behavior remain binding. No runtime install is authorized here.

### Binding and catalog

`harness:"cursor"`, displayName `"Cursor"`, iconKey `"cursor"`, copyKey
`"cursor_direct"`. The catalog item schema adds optional `beta:true` **only for
Cursor**; all existing entries retain their exact fields. Append Cursor after
OpenCode in catalog ordering. Available means implementation exists, not live
provider verification. Mode is `"hooks"`, placement **only**
`{kind:"this_computer"}`, options `{}`; no custom home, token, URL or pairing.

```json
{"configuration":{"adapterId":"cursor","label":"This computer","placement":{"kind":"this_computer"},"mode":"hooks","options":{}}}
```

Private binding remains `{version:1,home:<canonical owner home>}`. Test is
credential-free and non-mutating; requirements are exactly
`["cursor_hooks_opt_in","cursor_usage_opt_in"]`. Connect alone installs hooks;
disconnect removes only commands matched by `cursor_hook.py` basename plus source
ID and deletes that source's hook log/rotation/lock. Preserve every other hook,
file mode, atomic replacement, private backups (maximum three), concurrent-change
check, and registry-failure rollback. Never edit web-owned UI in this change.

Capabilities: agents true, lineage false, limits true, stuckDetection false,
asksYou false, deepLinks false. Coverage: agents partial, lineage unsupported,
limits account_dependent, asksYou/stuck/deepLinks unsupported. Links are null.
No complete roster or reassuring absence-of-asks claim is supported.

### Passive lifecycle and documented safety gap

Current official https://cursor.com/docs/hooks (checked 13 November 2026) lists
`subagentStart` as a permission hook: invalid/absent JSON on exit 0 can block
spawning, and its documented response requires allow/deny. **Do not install it**:
there is no documented neutral observer response. Likewise no preToolUse or
before-shell/read permission hook is installed. The sink can sanitize a supplied
subagentStart fixture and preserve parent_conversation_id, but production lineage
is disabled until Cursor offers a passive start notification. Never invent a
parent from title, path or time; never emit an approval merely to observe.

Installed events: sessionStart, sessionEnd, beforeSubmitPrompt, postToolUse,
postToolUseFailure, afterShellExecution, afterMCPExecution, afterFileEdit,
afterAgentResponse, afterAgentThought, stop, subagentStop. Sink always exits 0,
prints nothing, bounds stdin to 1 MiB and total execution to one second, bounds
lock wait to 100 ms, rotates two 0600 logs of at most 1 MiB each. Records contain
only conversation_id, generation_id, subagent_id, parent_conversation_id, event,
timestamp, workspace root basename and cursor_version. No prompts, file/shell
contents, status text, identity emails, model or transcript paths are saved.

beforeSubmitPrompt is **submitted**, not running: it clears the previous turn
without creating an active row. sessionStart proves presence only. Post-tool,
response/thought and edit events prove recent activity. stop/subagentStop remove
the matched generation from active observation but do not assert final completion
(another hook may auto-continue). sessionEnd also removes it, with no invented
completion reason/time. New activity after stop resumes observation; an old
generation's stop cannot end a newer one. Unmatched stops do not create rows.
Silence expires through shared project_rows at 900 seconds, with stale_source;
it is never idle. No permission/request event is treated as asks-you.

### Sign-in usage reader

Only the runtime reader touches login material. Linux CLI path is
`$XDG_CONFIG_HOME/cursor/auth.json` (default ~/.config/cursor/auth.json), key
accessToken. macOS CLI uses Keychain service cursor-access-token, account
cursor-user via SecItemCopyMatching with kSecUseAuthenticationUIFail (no UI
prompt), falling back to IDE credentials if absent or inaccessible. Never use the
security CLI, which cannot guarantee no UI prompt.
IDE path is `$XDG_CONFIG_HOME/Cursor/User/globalStorage/state.vscdb` on Linux,
`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` on macOS.
Use sqlite3 URI mode=ro&immutable=1 and select **only** ItemTable key
cursorAuth/accessToken with bounded SQL/time/output. Immutable reads can miss
recent WAL writes; report login unavailable rather than modify/checkpoint data.
`cursor-safe-storage:v1:` is rejected as cursor_login_invalid: silent decryption
is not implemented, no Keychain unlock prompt or refresh is attempted.

Decode only JWT sub and exp, without signature verification (routing and expiry
hints, never authentication proof). GET fixed https://cursor.com/api/usage-summary,
cookie WorkosCursorSessionToken=<sub>%3A%3A<token>. No redirects, proxies, refresh,
secret argv/env/files/logs/DTOs/notifications; eight-second total deadline, bounded
128 KiB response. Poll floor 300 seconds persists across restarts and force reads;
429/transport failures back off up to 3600 seconds. Reasons: cursor_login_missing,
cursor_login_expired, cursor_login_invalid, provider_rate_limited,
provider_unavailable, invalid_usage, stale_source, windows_missing. UI invalid
login copy must mention encrypted/unsupported login and signing in again.

Only Cursor source limits/test DTOs add provider `cursor`; existing T3 and Claude
DTOs are unchanged. One generic account `Cursor 1`, provider/driver `cursor`, one
window id `month`, label `Month`, kind monthly. Read individualUsage.plan only:
finite totalPercentUsed in 0..100, or explicit positive limit and consistent
used/remaining values; billingCycleEnd supplies reset. No plan-name arithmetic,
on-demand pool merge or modern weekly-plan inference. Unsupported shapes return
invalid_usage, expired resets windows_missing. Existing low_limit event validation
adds provider cursor; same source-qualified threshold/dedup/delivery flow applies.

### Overlap and acceptance

No verified T3-vs-standalone Cursor hook discriminator was established. Do not
claim deduplication or infer it from project/time. T3-hosted Cursor runs may appear
in both sources; counts remain per-source. Fixture-only beta until a real user
checks passive hook neutrality, lifecycle/continuation, login/plan compatibility,
WAL freshness, overlap and notification delivery. See direct-source-evidence.md.

## Codex sign-in — binding revision 4 (13 November 2026)

The owner approved a reader-only Codex sign-in read. This supersedes revision 2's
no-login restriction for explicitly opted-in Codex connections. Owner/private-route
checks, read-only glance behavior and separate runtime custody remain unchanged.
No `web/` changes belong to this backend revision.

### Consent and private binding

Keep the existing `adapterId:"codex", mode:"rollouts", options:{}` wizard flow.
Requirements now include `passive_rollouts` and `codex_usage_opt_in`. The existing
Connect action is consent; discovery and test never read credentials or call usage.
Required copy: **“To show your limits, Nagi reads your Codex sign-in and sends it
only to OpenAI. Nagi never refreshes or saves your sign-in.”**

New connects save a private version-2 binding `{version:2,home,usageOptIn:true}`.
Existing version-1 passive connections keep agents working but return limits
`codex_usage_opt_in` until disconnected and connected with the new consent.
The runtime reader uses `$CODEX_HOME` if set, otherwise `<home>/.codex`, for both
sessions and `auth.json`. No paths or credential fields enter public DTOs.

### Auth custody, identity and freshness

Only the runtime reader opens the owned regular `auth.json`, with no-follow and
bounded reads, refusing symlinked ancestors and files readable by other users.
Inspect only `tokens.access_token`, `tokens.account_id`, `last_refresh`, and the
access token's `exp` claim for expiry. Ignore email, titles, refresh token and ID
token. No refresh, CLI launch, account mutation, or writes to Codex's home.
Tokens stay in reader memory: never logs, exception messages, argv, environment,
Nagi files, API DTOs, notifications or caches. Failures use closed reasons only:
`codex_login_missing`, `codex_login_invalid`, `codex_login_expired`,
`codex_account_changed`, `provider_rate_limited`, `provider_unavailable`,
`invalid_usage`, `account_unverified`, `windows_missing`, `stale_source`,
`codex_usage_opt_in`, `checking`.

One account per home, labelled `Codex 1`. Its opaque key is HMAC-SHA256 of the
account id with a random, private per-install salt. No raw account id is persisted.
Re-read auth each runtime observation; stat identity includes inode, size, mtime
and ctime. Recheck after network/rollout reads. A change discards that observation
and old account windows; account changes cannot inherit cache or pending alerts.
Use the later of file mtime, ctime and optional `last_refresh` as the fallback boundary.
Only fresh rollout events strictly newer than that boundary can be attributed to
the signed-in account; otherwise retain `account_unverified`. This is local-file
continuity evidence, not attestation of independently supplied per-process auth.

### Usage request and limits

Preferred read: fixed `GET https://chatgpt.com/backend-api/wham/usage`, with
`Authorization: Bearer <access_token>` and `ChatGPT-Account-Id: <account_id>`.
Stdlib HTTPS only, no proxy use, redirects or configurable host, an eight-second
whole-I/O deadline, and a 128 KiB response ceiling. Never refresh tokens. Expired
JWT or HTTP 401 returns `codex_login_expired` without rollout fallback.

Persist the attempt before I/O. Poll no faster than 300 seconds, including forced
refreshes/restarts/account changes. 429 and transport/5xx unavailability back off
exponentially to 3,600 seconds. Only provider unavailability/rate limiting permits
the provenance-checked rollout fallback. Invalid auth, changed auth or malformed
usage never silently reuse old windows. Cached success expires after 900 seconds;
reset windows disappear without restamping their check time.

Map `rate_limit.primary_window` and `secondary_window`: `used_percent` becomes
`remainingPercent = 100 - used_percent`; `reset_at` is UTC epoch seconds;
`limit_window_seconds / 60` determines kind. Existing DTO ids `primary` and
`secondary`, labels `Session` and `Weekly` (for a seven-day secondary), and dated
`checkedAt` match T3's Codex headlines. Missing/null windows are not zero usage.
Additional model buckets, credits, plan and identity fields are not projected.
If an optional response `account_id` differs from the requested account, reject it.

### T3 overlap and alerts

Current T3 `instanceId` is a configured provider instance, not a proven ChatGPT
account id. Neither email nor titles can be used to bridge it. Therefore keep both
Codex lines source-qualified; no current evidence permits hiding a T3 account as
the same account. A future explicit identity bridge may prefer fresh direct data
only for the proven matching account, preserving all other T3 lines.

Unlike Claude, a **local T3 that is reading Codex owns local Codex alerts**: it
reads every Codex account it runs, while the direct reader sees only the account
signed in to its own home (amended by Opus, 13 Nov; the owner has two Codex
accounts). Ownership needs fresh T3 Codex limits, not a saved connection: when T3
isn't reading, the opted-in direct source alerts, so nothing goes silent. When
ownership moves, a window another source already delivered (same provider, window
label and provider reset instant) is not delivered again. That reset-instant match
is used for alert deduplication only, never to merge or hide account lines. Remote T3
alert ownership remains independent. Direct
API and fallback use the same opaque account/window/reset keys for durable dedup.

### Evidence and handoff

Upstream inspected at `openai/codex` commit
`69231e119bfca0b14453515e97d99688ce1c47c9`:
- [AuthDotJson](https://github.com/openai/codex/blob/69231e119bfca0b14453515e97d99688ce1c47c9/codex-rs/login/src/auth/storage.rs)
  and [TokenData](https://github.com/openai/codex/blob/69231e119bfca0b14453515e97d99688ce1c47c9/codex-rs/login/src/token_data.rs).
- [Usage GET](https://github.com/openai/codex/blob/69231e119bfca0b14453515e97d99688ce1c47c9/codex-rs/backend-client/src/client/rate_limit_resets.rs),
  [headers and mapping](https://github.com/openai/codex/blob/69231e119bfca0b14453515e97d99688ce1c47c9/codex-rs/backend-client/src/client.rs).

Verification uses fake auth, HTTP and rollout fixtures in temporary homes only.
Upstream shape verification does not claim a live authenticated endpoint success.
Opus must add the consent and closed-reason copy before this draft is release-ready.
No install, merge, Mac or installed-runtime access is authorized here.
