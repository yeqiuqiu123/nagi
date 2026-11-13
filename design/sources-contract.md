# Modular sources: proposed backend contract

Status: **proposal, 13 November 2026**. This document authorizes no installation,
pairing, service activation, runtime migration or network exposure. It describes a
Python 3.11+ implementation using only the standard library.

The owner now wants a friendly choice of harnesses and computers. Keep the same
two questions, read-only glance, owner boundary and existing visual identity.
Setup writes **Nagi's connection preferences**, never agent instructions, provider
credentials, source configuration or approval decisions. An explicit “open” action
can hand the operator to the source application; Nagi cannot send, stop, answer,
approve, resume through RPC or control an agent.

## Approved direct-source exception (13 November 2026)

The owner approved direct local Claude usage reads, reversible passive hooks at
wizard connect, passive Codex rollout observations and low-limit alerts. The
binding [Sources API revision 2](sources-api.md#direct-local-sources--binding-revision-2-13-november-2026)
supersedes this proposal wherever they differ: OAuth reads are explicitly
opt-in, no token refresh; connect alone may edit Nagi's hook entries; file/hook
agent observations are partial rather than a complete roster. Keep all secret,
owner-auth, freshness and account-provenance rules. No runtime installation or
live settings edit is authorized by this development build.

The later owner-approved [Codex sign-in revision 4](sources-api.md#codex-sign-in--binding-revision-4-13-november-2026)
adds explicit connect-time consent for reader-only sign-in/usage access. It
supersedes the older Codex no-auth rows below only for opted-in bindings, with
salted account identity, auth-change-qualified fallback and closed errors. Existing
passive bindings require reconnecting; dashboard/private-route custody is unchanged.

## Decisions

1. A **source instance** is one selected harness, profile/home and execution host.
   An adapter kind is reusable code, not the identity of a connection. Two T3
   servers, or two Codex homes on one computer, are distinct instances.
2. Group **harness → connection/computer → project → agent and children**. With one
   connection, omit the extra connection heading. The heading uses an operator
   label such as “This computer” or “Computer 2”, never a discovered hostname.
   This keeps the source's availability and coverage visible. Do not merge
   unrelated projects merely because their titles match across harnesses/hosts.
3. Preserve v2 projections and truth semantics **inside a new source envelope**.
   Do not add fields silently to existing EXACT v2 objects/routes. Existing T3
   consumers keep working while the new clients opt into the source API.
4. Prefer an existing scoped API; otherwise consume an explicitly provisioned,
   sanitized host export. Parsing an existing file is acceptable when documented
   or version-tested; it does not make an incomplete live roster complete.
5. Capabilities are **per measure and per configured mode**, not optimistic claims
   attached to a product name. Each connection can answer agents, limits, both,
   or neither. Discovery reports installation separately from readability.

## SourceAdapter interface

The following is an interface sketch, not runnable code added to the reader.
`Outcome`, `AgentData`, `ProviderData`, project/agent/window fields refer to
[API v2](api-contract.md). Adapters construct explicit DTOs; raw dictionaries from
sources never pass through to HTTP responses or caches.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping, Protocol, TypedDict

Truth = Literal[
    "ok", "quiet", "unavailable", "last_known", "not_set_up", "unsupported"
]
Json = object  # Strict bounded JSON values, validated before/after adapter calls.

@dataclass(frozen=True)
class Identity:
    id: str                 # Registry key: t3, openbot, pi, codex, claude, hermes, openclaw.
    display_name: str       # Static product name; never a hostname/account email.
    icon_key: str           # Bundled icon registry key, never a URL or source-supplied SVG.

@dataclass(frozen=True)
class Capabilities:
    agents: bool
    lineage: bool
    limits: bool
    stuck_detection: bool
    asks_you: bool
    deep_links: bool

class SourceTag(TypedDict):
    id: str                 # Random stable Nagi instance ID; not Identity.id.
    harness: str
    label: str              # Owner-chosen safe connection label.
    placement: Literal["local", "tailscale"]

class Outcome(TypedDict):
    status: Truth
    attemptedAt: str
    checkedAt: str | None
    reason: str | None      # Closed code, not raw exception text.
    data: Json              # AgentData or ProviderData from v2, or None.

class ProviderOutcome(Outcome):
    warnings: list[str]      # Existing v2 provider warning codes.

class Detection(TypedDict):
    candidateId: str         # Short-lived opaque handle; not a path or IP.
    harness: str
    placement: Literal["local", "tailscale"]
    peerRef: str | None
    installed: Literal["yes", "no", "unknown"]
    running: Literal["yes", "no", "unknown"]
    readable: Literal["yes", "no", "unknown"]
    evidence: list[str]      # Closed codes: binary_found, data_found, endpoint_found, etc.
    expiresAt: str

class SourceRead(TypedDict):
    source: SourceTag
    capabilities: dict[str, bool]
    agents: Outcome
    limits: dict[str, ProviderOutcome]  # Existing account/window data and warnings.
    coverage: dict[str, str]    # Closed values described below, not free-form diagnostics.
    warnings: list[str]

class DetectContext(Protocol):
    """Selected platform/peer inventory, allowlisted roots, and absolute deadline."""

class ConfigureContext(Protocol):
    """Owner-verified context with private store and one-use secret-handle resolver."""

class ReadContext(Protocol):
    """Private binding, clock, settings, cancellation/generation and I/O budgets."""

class ConfiguredSource(Protocol):
    """Private immutable validated binding; secret fields are excluded from repr/logging."""

class SourceAdapter(Protocol):
    identity: Identity
    potential_capabilities: Capabilities

    def configuration_schema(self) -> Mapping[str, Json]:
        """Closed JSON-schema-like form description; contains no saved values."""

    def detect(self, context: DetectContext) -> list[Detection]:
        """Observe only; do not launch, pair, enable, repair or persist anything."""

    def configure(self, value: Mapping[str, Json],
                  context: ConfigureContext) -> ConfiguredSource:
        """Validate/stage Nagi binding; never edit the harness. No network pairing."""

    def read(self, configured: ConfiguredSource,
             context: ReadContext) -> SourceRead:
        """Return independently projected v2 agents and provider limits + source tag."""
```

Registry selection is a static allowlist; no arbitrary Python import, entrypoint,
plugin download or shell template from a setup request. `configure()` builds a
private binding, while only the connect operation commits it. The service owns
dated caches and notifications, so every adapter uses the same failure semantics.
Transport clients receive credentials opaquely through the private binding; DTO
construction has no need to expose them.

`coverage` has the exact keys `agents`, `lineage`, `limits`, `asksYou`, `stuck` and
`deepLinks`; values are `complete | partial | unsupported | unverified`, except
`limits` may be `account_dependent`. These describe selected-mode coverage, not
freshness; `Outcome.status` describes freshness/readability. Capability flags mean
the installed mode has usable support; a transient connection failure does not
erase its capabilities. Potential capability is not enabled capability. A
credential-free install probe must not claim full agent-read coverage.

### Projection rules and necessary wire evolution

Reuse v2's `projects`, recursive `children`, `ended`, counts, omitted-row warning,
source timestamp rules, normalization, quotas/accounts/windows and six truth states.
The source tag on the enclosing read applies to every nested object. Never pass a
non-T3 envelope to the existing T3-specific projector; share only field validators
and generic grouping after an adapter has normalized its source evidence.

The **new envelope's DTO dialect** is `dtoVersion:2` with `extensions:["nullable_links"]`.
This is an explicit opt-in extension: agent `links` retains the keys `desktop` and
`web`, but either value can be null. Sources with no verified session opener use
both null. Legacy `/api/glance` still has the exact original T3 link strings; it
never receives this extension. Do not synthesize a T3 link for a foreign session.
Native clients must handle null and validate each supported source's closed link
grammar before non-T3 links can be enabled.

No new agent state is invented. Unknown source states, a mere recent file or
`notLoaded` on a different Codex server cannot be relabeled `idle`, `completed` or
`running`. If the adapter cannot provide a live roster, agents is `unsupported`
for a file-only mode, or `unavailable` when a configured runtime/export failed.
Limits can still be `ok`. A log reader may show dated `last_known` rows only from
a **previous complete successful roster observation**; it cannot manufacture that
baseline from an unmatched historical start event. Historical metadata can enrich
a known row, not create a spurious live count. Do not introduce a history view.

When a valid runtime export lacks an explicit title, use the existing neutral
title fallback. When it has no project association, use one stable synthetic
"Sessions" project within that source; never extract a project from prompt text
or merge it with a same-named project in another source. Missing provider/model
and run times stay null. This lets the minimal OpenBot running/idle export fit
the DTO honestly while its capability/coverage fields describe the omissions.

For partial live coverage, isolate unknown/malformed rows into `omittedRows` and
warnings; the source must remain `ok` with a visible coverage gap, never `quiet`.
An API that fundamentally cannot enumerate the selected scope is not a complete
empty read. `waitingOnYou` is evidence-backed only; when `asksYou` coverage is
partial/unsupported, false flags mean “no known ask,” never “definitely no ask.”
The client must hide the reassuring absence claim and show the coverage limitation.
Absence of an ask under incomplete coverage forbids stuck detection.

Use an existing source environment ID when available; otherwise derive a stable
opaque environment ID from the connection ID. Source agent/project IDs remain
opaque inside the source envelope. For merged lookup, cache and notification keys,
use a structured tuple `(sourceId, environmentId, nativeId)`; do not concatenate
ambiguous IDs with colons. Hash a canonical JSON encoding for durable keys.
Parent links must remain within that source and project; keep v2 cycle/depth checks.
Conversation forks, message-parent edges, compression continuations and task
dependencies are **not** concurrent subagent lineage.

Times retain their meaning. `startedAt` is current-run start, not conversation
creation; absent run start stays null. `lastActivityAt` is source activity, not poll
time or export heartbeat. Normalize a genuine source completion into the DTO's
`latestRunCompletedAt` provenance value; use `updatedAt` only for the existing
qualified failed-row fallback. Unknown end times remain null; do not invent an
Ended entry. Last-known data and unknown liveness never generate new notifications.

## Configuration schema by adapter

All schema objects reject unknown keys and wrong types. The common form is:

```text
{adapterId, candidateId?, label, placement, mode, options, secretRef?}
placement = {kind:"local"} | {kind:"tailscale", peerRef:<opaque selection>}
```

`label` is normalized plain text, at most 80 characters, defaulting to a generic
connection name. `candidateId` is optional for manual setup; selection is not a
trust grant. `options` is a mode-specific closed object. Paths/origins are accepted
only in the authenticated setup request, resolved privately, and omitted from
read/list/test responses. No config schema accepts a command string, environment
dictionary, provider key, raw transcript endpoint or arbitrary URL path.

| Adapter/mode | Private configuration input | Safe starting capability and constraint |
| --- | --- | --- |
| T3 / `protocol2` | `origin`; provisioned `secretRef` for exactly `orchestration:read`, or reuse existing private legacy credential reference | Agents/lineage/limits/asks/deep links; existing conservative stuck checks. Origin validator and scope validation remain unchanged. |
| Codex / `rollout_limits` | Selected `home` path or collector binding; bounded active/archive inclusion | Limits only, dated and account-qualified; live agents unsupported. No auth store reads. |
| Codex / `existing_server` | `unixSocket` OR approved WS origin; provisioned transport `secretRef` if needed; selected home/coverage identity | Agents and limits only after endpoint/version/coverage validation. Read-only method allowlist; require non-repair listing mode. Never start a server or resume threads. |
| OpenBot / `metadata_export` | Selected `snapshotPath` or collector binding, explicit approved-agent selection | Running/idle subset once production export exists; other metadata/limits disabled until a versioned export supplies them. Retained legacy exporter is not automatically enabled. |
| Claude / `sidecar` | Selected `snapshotPath`/event directory, optional selected metadata root, collector binding | Agents/lineage/asks only with complete hook lifecycle; limits with status-line export. File-only metadata mode does not claim a live roster. No replacing a user's hooks/status line automatically. |
| Hermes / `summary` | Existing dashboard origin/profile plus scoped collector binding; or explicitly selected read-only metadata export | Partial session summary; live agents/asks require runtime export. Disable normal `hermes usage --json` polling because it may refresh credentials. |
| Pi / `sidecar` | Selected agent/session root and versioned runtime export or collector binding | File metadata only without export; live capabilities require an already owned event stream/extension. No network RPC spawning. |
| OpenClaw / `gateway_read` | Approved Gateway origin, profile reference, `secretRef` for read-scoped device token, provisioned identity/signing-helper reference | Agents/provider-supported limits after handshake test; no default stuck/asks/deep-link promise. Stdlib reader uses a supported host helper/collector for device signing. |

A **collector binding** is `{peerRef, collectorId, sourceRef, secretRef}`; these are
opaque IDs chosen from provisioned endpoints. It is not a filesystem mount, an SSH
command field or an arbitrary RPC proxy. Selecting a data root found without a CLI
must explain that only data was found. Missing production support should be a
clear setup result, not a disabled but apparently connected tile.

Pairing links are **inputs for an explicit setup handoff**, never general fetch
targets. For supported providers, validate a closed scheme/origin/path and let
the owner's native pairing flow return a one-use private credential reference.
Do not treat invitations, login callbacks or bootstrap tokens as ongoing observer
credentials. Ongoing reads cannot acquire broader authority than the selected mode.

### Secret custody

Reuse `runtime_paths.py` and the existing private-store mechanisms. Proposed
`nagi-sources.json` is versioned, owner-only and contains instance IDs, validated
private options and references, never inlined provider tokens. Separate secret
files under an owner-only source-secrets directory use 0600, random filenames,
atomic writes and no-follow/owner validation. Secret-bearing objects suppress
repr; failures return closed codes only. No secret in process arguments, URLs,
environment dumps, exceptions, DTOs, fixture files or logs.

The native setup helper may import an operator-provided **source observer
credential** through a pipe/private descriptor and issue a short-lived opaque
`secretRef`. Existing bearer files are never found by broad directory search.
Browser code cannot request an arbitrary credential filename or read the install
secret. If a future browser-only secret-import route is needed, specify it
separately with a narrow size limit and existing owner checks; the four wizard
operations below use refs only and retain the current 4 KiB request bound.

Resolve roots privately; only owner-approved canonical trees can be traversed.
Reject special files, foreign ownership and symlink escapes; use bounded regular
file reads and explicit filename/type allowlists. Credentials remain excluded even
if they share a source root. Live SQLite fallbacks use read-only connections and
short read transactions, with WAL behavior tested; never `immutable=1` on a live
changing database, migrations, pragmas that write, or copied incomplete DB/WAL
sets. Prefer the source API/export. T3 database access remains forbidden.

## Discovery and placement

Discovery is deliberate and bounded: check selected harness executables, app
bundle metadata, known non-secret data directories, registered source locators and
source-owned listeners. Use a credential-free public descriptor where one exists.
Do not run arbitrary wrapped executables, source doctor/repair commands, auth
status, model discovery or auto-starting CLI modes. “Installed,” “running” and
“readable with Nagi's selected scope” are independent results.

For remote selection, read an existing Tailscale peer inventory through a bounded
read command/API, if available, then test only the peer and known source endpoint
the owner selects. Tailnet membership does not prove a harness is installed.
Use `found_on_peer` only after an authenticated registered collector or a supported
public source descriptor establishes it. Offline peer discovery stays unknown,
not “no agents.” No tailnet-wide port scan, automatic SSH, key distribution,
package installation, Serve/Funnel change or service activation.

Wizard labels can say “Installed here,” “Running here,” or “Found on Computer 2.”
Network topology stays server-side behind `peerRef`; do not return hostnames,
IPs, raw paths, installation IDs or account emails in glance DTOs. A native
computer picker can display an already authorized peer label before producing
the opaque reference; do not reuse `hostname` as an agent/provider identity.

| Source | Local | Direct remote over Tailscale | Collector requirement |
| --- | --- | --- | --- |
| T3 | Existing protocol-2 HTTP/WS | Existing permitted origins, read-scoped credential and provisioned host route | None for the present API. |
| OpenBot | Selected production export; limited automation GETs are not a complete source | No documented direct read-scoped automation listener; Team API is a different integration | Recommended metadata-only host export/collector. |
| Pi | Documented metadata files; configured live sidecar | No general observer network service established | Required for file/sidecar reads on another host. |
| Codex CLI/app | Passive quota logs or already existing supported server | Existing authenticated endpoint only, version/coverage dependent; current WS is experimental | Preferred for broad runtime credentials and file coverage. |
| Claude Code | Configured hooks/status-line sidecar, saved metadata | No general read-only roster service established | Required; never share the raw config tree. |
| Hermes | Existing dashboard summary/export | Dashboard transport exists but its master token grants control | Scoped collector recommended; never import the master token by default. |
| OpenClaw | Read-scoped Gateway | Documented Tailscale placement with device identity and proper ingress | Use helper/collector if stdlib cannot perform the signing handshake. |

A remote collector is a **future, separately provisioned metadata surface** on the
source host, sharing adapter/projection code but not exposing Nagi's loopback
owner API. Prefer one per host with explicit source selections and a separate
source-read token scoped to those selections. It returns only normalized source
DTOs through fixed read endpoints. No filesystem/RPC forwarding, shell execution,
raw histories, credentials or provider probes which refresh auth. A connection
cannot enumerate unselected source roots. Revocation affects only its observer
token, never the harness's own login.

Transport choices are verified HTTPS on a provisioned `.ts.net` origin or an
owner-managed secure tunnel with peer identity. Preserve the existing narrow T3
HTTP-to-Tailscale-IP transport as-is. New collectors should default to HTTPS;
Tailscale routing alone does not establish process authorization. Refuse
redirects, proxies, userinfo, unapproved DNS rebinding targets and non-tailnet
remote origins before resolving secret refs. Validate exact origin/peer binding
on every connect/read. Do not turn the public static Nagi page or existing reader
ports into remote APIs. Sleeping computers yield last-known/unavailable truth.

## Multi-source reads, merging and limits

Keep independent poll/cache/sequence state for each source. Use bounded worker
concurrency (initially four total), per-source deadlines and scheduling/backoff.
A hung source cannot prevent settings, auth, healthy-source publication or the
20-second normal refresh cadence. Enforce a whole-read budget in addition to
socket deadlines; limit fan-out and per-source rows/bytes. Start with existing
512-project/4,096-thread/8 MiB ceilings per source, a maximum of 16 configured
instances, and a global render/response byte cap. Global truncation must carry a
visible warning and never become `quiet`; do not silently hide selected sources.

Polling returns successful projected observations. The service applies cache
policy independently for agents and each provider account, carrying source
timestamps through all layers. Config changes increment a source generation;
late reads from the old origin/profile cannot populate the new cache. Disconnect
invalidates generation immediately. Event streams require baseline+sequence
recovery; gaps trigger a bounded fresh read, never inference from silence.

Truth rules are unchanged from v2, applied **per source and measure**:

| Truth | Meaning in a modular glance |
| --- | --- |
| `ok` | Successful usable observation; any omission/partial-coverage warning remains visible. |
| `quiet` | Successful complete empty agent observation of the selected scope. Never empty/missing quota windows. |
| `unavailable` | Configured but unreadable, unreachable, malformed or not yet checked; no usable prior observation. |
| `last_known` | Previous successful observation after a failed refresh, with original checked times. Never live counts/alerts. |
| `not_set_up` | Selected source has not been configured/provisioned, or the required installation is absent. |
| `unsupported` | This mode/version/platform/account cannot supply the requested measure. |

Use `attemptedAt` for the attempt, `checkedAt` for the actual successful check.
Missing measures never become zero, and connecting a second harness must not
blank the first. Show unconfigured discovery candidates only in setup, not as
permanent unavailable sections in the glance. Persisted connections whose sources
temporarily disappear remain visible with their own outcome.

**No single success bit for the whole panel.** A new source read endpoint returns:

```text
GET /api/sources/v1/glance
{
  version:1, dtoVersion:2, extensions:["nullable_links"],
  platform, checkedAt,
  sources:[{source,capabilities,agents,limits,coverage,warnings}],
  settings:<existing settings DTO>,
  warnings:[<closed storage/coverage warning>]
}
```

The source list is ordered by stable harness registry order, then connection
label/ID; projects/siblings retain v2 sorting. Each source has its own collapsed
Ended group and bounds. Counts are source-local. A header may sum **fresh,
non-overlapping known counts** only, with an explicit partial/unknown label when
some sources cannot supply live state. It must exclude last-known counts and
context-only ancestors. If duplicate execution coverage is unresolved, omit a
global total instead of presenting an inflated count.

### Overlapping orchestration and underlying harnesses

T3/OpenBot/Hermes/OpenClaw may execute Codex/Claude/Pi. Connecting the orchestrator
and its underlying home can expose the same run twice. Default to **orchestrator
coverage for its hosted runs**, standalone coverage for independent CLI/app runs.
Use explicit native-session correlation only when a source supplies a stable
external session ID and host/profile identity. Never deduplicate by matching
titles, cwd strings, model, prompt or approximate timestamps. Ask the setup UI to
choose coverage when it cannot be proven; mark overlap and suppress a misleading
global count/duplicate notification meanwhile. Source-local views remain honest.

Account IDs are also source-local. Limits retain provider → accounts → source
window IDs, headlines/secondary windows, resets and account-specific truth.
Sources can report the same subscription. Do not add percentages, choose the
minimum, merge accounts by email, or infer identity from model/provider names.
Initial UI shows **source-qualified account lines**. A later explicit account
alias can select a preferred observation source; it is a Nagi preference and
never exposes or derives credentials. Distinct windows with the same duration
remain distinct. Multiple metered buckets require bucket-qualified stable window
IDs; never discard them just because two are called primary.

Use the existing 15-minute freshness ceiling and retain only unexpired cached
windows; a source can impose a stricter ceiling. Cached source responses and
sidecar rewrites cannot renew a provider check time. Where a source's passive
snapshot has no provable quota check time, keep it unavailable rather than label
the collector time as that check. API-key/no-window accounts are unsupported;
provider failures are unavailable, not unsupported. Normalize `remainingPercent`
only from a valid usage fraction/percentage and a reset; no balance-to-window
conversion. Generic numbered account labels replace private display identities.

For a passive log/sidecar, require explicit non-secret account provenance before
merging observations into an account line. A connection/home ID alone cannot
prove that a sign-in did not change; unresolved or conflicting provenance yields
`account_unverified` and no current percentage. A status-line sidecar needs a
source API-response/check marker to date a quota observation; repeated renders of
an unchanged cached object cannot advance that date.

### Notifications and liveness

Retain current v2 thresholds and reserve/acknowledge/claim delivery semantics.
Transitions and notification IDs include source identity. Reconnecting, renaming
a source, changing thresholds or importing legacy configuration must not replay
existing failures. A source's first successful roster establishes its baseline.
Disconnection stops new events and retires its pending delivery records; it does
not clear unrelated sources' journals. Do not manufacture a failed transition
when an adapter crashes or the remote machine sleeps.

`stuck_detection` is enabled only after complete current-run evidence can rule out
open tools, blocking children and pending human requests. A whole source's tool/
ask coverage gap forces unknown, even if elapsed time is large. Sidecar heartbeat
proves exporter freshness only. New adapters default to `stuck:null` and no stuck
notification. Preserve long-tool suppression; no timeout heuristic is marketed as
a universal hung-agent detector.

## Owner-authenticated wizard API

Implement routes in the current server's private allowlist and existing auth
middleware. Every setup endpoint, including discover/test/list/schema, requires
owner proof or an unexpired `X-Nagi-Session`. Retain loopback bind, exact
Host/Origin/fetch checks, Linux peer UID, mutual-HMAC native bootstrap, no cookies/
CORS, `no-store`, strict bounded JSON, and `X-Progress-Desk:1` on POST. Unknown
keys/methods/queries fail closed; public HTML contains no discovery records.

Flow: pick harnesses → choose “This computer” or a selected tailnet peer → inspect
what was found → provision only the supported observer/export through a native
handoff if needed → test → connect. Explain concrete missing capabilities in the
result, such as “Limits available; live agent status needs an export.” The primary
glance stays read-only; setup controls are connection preferences only.

| Route | Exact request intent and safe response |
| --- | --- |
| `GET /api/sources/v1` | List selected connections: `{version:1,revision,sources:[<source tag + effective capabilities/coverage + latest measure statuses>]}`. No private options, paths, origins or secret refs. |
| `GET /api/sources/v1/schema/<adapterId>` | Static versioned schema, supported modes, potential capabilities and closed setup requirements. Reject unknown adapter IDs. |
| `POST /api/sources/v1/discover` | `{adapterIds:[<allowlisted>],placement:{kind:"local"}|{kind:"tailscale",peerRef}}` → `{version:1,candidates:[Detection],warnings:[]}`. No persistence or network-wide scan; candidates expire after five minutes. |
| `POST /api/sources/v1/test` | `{configuration:<closed common form>}` → `{version:1,testId,expiresAt,capabilities,coverage,agents:<status/check time/reason>,limits:{provider:<status/check time/reason>},warnings:[]}`. No source data rows, private config, raw errors or secrets. Test uses only safe read calls and does not persist a connection or trigger notifications. |
| `POST /api/sources/v1/connect` | `{testId,expectedRevision}` → `{version:1,revision,source:<tag>,capabilities,coverage}`. Test is one-use, expires in two minutes and is bound to owner session, canonical private config digest and credential generation. Atomic commit of tested config only; no supplied URL/token can be swapped after test. |
| `POST /api/sources/v1/disconnect` | `{sourceId,expectedRevision}` → `{version:1,revision,disconnected:boolean}`. Stop reads, invalidate generation, remove only that Nagi connection/owned observer secret, retire its pending notifications. Repeated already-disconnected IDs succeed without touching the harness. |

Connect remains allowed for a provisioned but sleeping source only after a prior
validated identity/compatibility test retained by the same connection; a brand-new
unreachable origin cannot be “tested” by silence. An unprovisioned/unsupported
candidate may be saved only as a setup draft, not a connected live source.

Test/candidate records live in a bounded owner-session-bound memory store, not in
URLs, logs or public assets. Resolve `secretRef` only after placement/path/origin
validation; never return it. Expired test is 409/`test_expired`; revision conflict
is 409/`configuration_changed`; unsupported mode or missing required setup is a
200 test outcome with closed requirements. Authentication/ownership denial stays
401/403; malformed JSON/keys 400; unknown routes 404; methods 405; size 413;
private-store failure 503. Source connection failures use outcome truth, never raw
upstream HTTP bodies or exception strings. Retain strict duplicate-key/nonfinite
JSON rejection and bounded path/JSON depth.

New-source reason codes are a separate closed registry, not additions silently
accepted by the legacy T3 routes: `not_configured`, `not_installed`,
`export_required`, `cannot_reach_source`, `invalid_source`, `protocol_unsupported`,
`scope_insufficient`, `checking`, `coverage_incomplete`, `cyclic_lineage`,
`account_unverified`, `account_unsupported`, `windows_missing`, `stale_source` and
`probe_failed`. Responses may include only applicable codes, plus the existing
v2 account/window/storage warnings. Keep wizard requirements and HTTP error codes
separate from source outcomes.

`test()` is orchestration around `configure()` and `read()`, not an adapter method
that can secretly pair or fix a harness. If a safe test needs a collector/export
which is absent, return `not_set_up` with a specific setup requirement. A test
cannot call model/provider-refresh endpoints, create sessions or broaden scopes.
Disconnect removes Nagi-owned copies only: revoking an upstream observer token is
an explicit operator action in the source, never provider logout. Do not delete
external credential files that predated Nagi.

## Migration of the existing T3 source without behavior change

1. Extract a `T3Adapter` around **existing** `T3Reader`, T3 projection and quota
   mapping. Retain URL rules, peer-UID/TLS checks, protocol header, omission flags,
   favicon restrictions, scope checks, five-minute config cache and all bounds.
   Do not replace the transport with a generic RPC gateway. Preserve the known
   config-refill discovery cost; do not add unsupported T3 request flags.
2. When no new registry exists, expose an **in-memory legacy T3 instance** backed
   by the current `nagi-t3.json`. Reading it performs no migration write, token
   copying, re-pairing or runtime access beyond the normal private reader. No
   policy still means not set up. Give this instance a stable reserved identity;
   renaming/migrating it cannot reset notifications.
3. Keep `/api/glance`, `/api/limits`, project-icon routes, settings and notification
   responses byte-shape compatible with T3-only v2. New clients use the new source
   route; do not change native parsers before they opt in. Legacy provider keys
   remain `codex`/`claude`; new envelopes can register additional provider keys
   without pretending legacy clients understand them.
4. Preserve the legacy T3 journal/cache/transition keys through a compatibility
   lookup until an authorized registry migration atomically associates them with
   the reserved source. No double baseline, failure replay, duplicate source
   reads or changed account labels. Use a per-source namespace for new sources
   rather than feed new provider keys into the old journal validator.
5. A wizard connect can persist the registry and reference the **same** private
   legacy credential file. Do not run installers as part of this conversion.
   `mac/setup-mac.sh` and `install_reader.py` remain compatible with current flags;
   the wizard becomes an additional setup route, not an immediate replacement.
6. The installed private runtime and development checkout have independent
   custody. This research changes neither. A later release must compare intended
   code/policies on both, plan any explicit registry/journal migration, and verify
   Linux `nagi_links.py`/notification targets plus macOS `SourceLinks.swift` before
   enabling non-T3 links. Old T3 links remain closed and valid. Generic URL opening
   is not an acceptable migration shortcut.

## Phased build order and acceptance

| Phase | Deliverable/value for this owner | Acceptance before enabling it |
| --- | --- | --- |
| 1 | T3 adapter extraction, source registry, local/selected-peer discovery and four-step wizard; retain today's useful glance | Existing T3 DTO/settings/account/icon/auth/notification tests pass unchanged. No policy/journal rewrite on read. Owner denial/unknown-origin/expired-test/conflict paths fail closed. One failing source cannot blank another. |
| 2 | Codex **passive quota** adapter, then existing-server roster when safely attachable | Redacted structural fixtures from 0.167.0 and older supported versions; nullable windows, malformed/truncated/rotated logs and dated checks. Demonstrate account association and overlapping T3 coverage. No credentials or startup RPC. File-only mode explicitly lacks live agents. |
| 3 | OpenBot production metadata export, reusing the existing development exporter and selected-agent policy | OpenBot owns the source change. Package/Mac support must actually exist; readback of running→idle/failed, visibility and completeness. Extend with safe title/model/project/lineage/asks/dated quota only where source evidence exists. Vikunja is not an execution feed. |
| 4 | Claude Code hook/status-line sidecar for standalone sessions and subscription windows | Deliberate reversible setup which preserves existing hooks/status line; baseline/restart/gap handling, child association, pending asks and long tools. Record quota observation age honestly; no API execution to generate telemetry. |
| 5 | Hermes selected-profile summary/export, then verified passive quota snapshot | Treat the customized local revision separately; distinguish five-minute recent activity from running. Verify compression vs delegation lineage. Normal quota CLI refresh remains forbidden. Remote use goes through scoped export. |
| 6 | Pi runtime sidecar/extension using the documented event/RPC schema | Do not start another Pi. Verify branch vs subagent semantics, `agent_settled`, stream recovery, open-tool suppression. Limits remain unsupported unless a new evidenced surface appears. |
| 7 | OpenClaw, then OpenCode, when selected by the owner; shared remote collector for file/sidecar modes can move earlier if needed | Real installed-version/auth readback, scope/method denials and pagination/reconnect. OpenClaw device signing uses a supported helper. OpenCode V1/V2 are distinct compatibility profiles. No public exposure or broad master credentials. |

Start remote support with **T3**, whose transport already exists. Bring the shared
collector forward only when the owner actually selects a remote file/sidecar
source; it must be provisioned as its own reviewed runtime surface. OpenClaw's API
is feasible, but installing it solely to build an adapter would not help this
owner before the already present harnesses.

Verification for implementation should exercise real saved-result readback in
disposable owner-only development data, denied operations and existing CI, then
the selected Linux/Mac journey. No release claim can rely solely on fixture tests
or the unreachable Mac from this research. Keep unsupported/partial capability
copy visible and test failure of one source alongside a healthy second source.
This task adds design documents only and requires no service or live runtime test.
