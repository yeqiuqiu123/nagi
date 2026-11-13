# Agents and limits — Linux-first backend handoff

Branch **t3/nagi-agents-and-limits**, cut from final review fix head **39d812a**
on t3/loopback-owner-auth-cross-platform. No install, push, service, account,
exposure or live-runtime policy changes. Private real content was not committed.

## Research answers

- **T3:** supported protocol-2 shell GET covers all local projects/threads, with
  omission flags off and a separately paired orchestration:read client. Pending
  request metadata, lineage, model/provider and source times are projected into
  closed DTOs. No CLI-per-project polling or T3 DB read. Public live probe confirmed
  server 0.1.9/protocol 2 on 3773; unauthenticated shell returned 401.
- **Limits:** read cached server.getConfig through the supported Effect RPC JSON
  WebSocket. T3 collects Claude Agent SDK get_usage five-hour/weekly windows;
  status-line hooks are unnecessary. Codex windows use the same provider snapshot.
  No refresh/login/vault call. Real authenticated window values remain unverified.
- **Stuck:** updatedAt is event-driven, not a heartbeat. Fifteen minutes is the
  configurable default. Aged threads require complete bounded detail with no open
  tool, human request, child wait or streaming/unknown evidence. Silent open tools
  suppress alarms; genuinely hung silent tools remain indistinguishable.
- **Links:** generated t3code://threads/<encoded environment>/<encoded thread>;
  https://app.t3.codes/threads/... fallback. Opaque non-UUID IDs are supported.

Exact frontend contract: **design/api-contract.md**. No custom source setup or pairing was activated.

## Implementation and commits

- 39b34d5 — bounded research findings first.
- 3cd870a — API v2 contract, committed before behavior changes.
- b73079c — lean reader, agents/limits projection, local preferences, atomic
  transition journal, dated cache and isolated test glance; retired HTTP routes.
- f9d8792 — Linux tray/glance wiring, Gio banners and closed desktop/web links;
  source/auth/outcome/restart/delivery regressions.
- The final documentation commit records this handoff, caller audit and contract
  refinements. Its hash is in the parent report/git log.

Reader polls every 20 seconds. A baseline snapshot does not replay old failures.
Each later failed/stuck transition has a persisted generation. Atomic 30-second reservations precede OS submission; a claim is committed only
after the desktop confirms acceptance. Rejected sends are released and retried.
Confirmed claims survive restart, and reservations prevent concurrent submissions.
A crash after OS acceptance but before the claim may repeat a send; GTK reuses the
stable event ID, and no exactly-once desktop guarantee is claimed.
An unavailable notification bus leaves the glance usable. GTK click actions use a stable string-target action plus a matching prepared user
D-Bus service, so they survive tray/notifier restarts; OS delivery is best effort.

Settings persist owner-only in the shared runtime data directory. Only preference
writes and notification claims are served; there are no T3 control routes. Existing
mutual proof auth, Linux peer UID checks, native 401/show/12-minute recovery,
shared resolver and idempotent installers remain. The T3 transport additionally
checks the connected Linux server-side socket UID before sending its opaque paired
credential. Same-UID processes and root remain trusted.

Python floor stays **3.11+**: shared imported JSON/contract modules still use
`datetime.UTC` and typing.NotRequired. No new Python package dependency. The local
journal alone permits up to 160 JSON nesting levels for bounded parent trees;
request/policy ingress retains its existing 24-level default.

## Retired and retained

The routes of the earlier dashboard are removed from the served app (404);
/overview aliases /glance. Its modules and web assets were deleted before the
first public release. The strict JSON parser now lives in jsonio.py and the host
metrics in machine.py.

## Verified

- `python3 -B -m unittest discover -s tests -v`: **164 passed, 0 failed**.
- `node --test tests/overview.test.cjs`: **19 passed, 0 failed**.
- `python3 -B -m unittest -v test_widgets_ingress test_launcher`:
  **27 passed, 0 failed** in the preceding batch (not rerun for this review; shared
  JSON default and launcher regressions).
- Changed-module compilation, Node syntax, installer shell syntax and
  `git diff --check` pass. The live runtime is untouched; tests use synthetic
  metadata, temporary data directories and disposable loopback servers.
- Real Linux HTTP checks exercise same-user socket ownership, mutual proofs,
  sessions and denied requests. Mocked proc tables retain foreign-UID denial tests.
  A synthetic WebSocket server verifies the only emitted RPC is server.getConfig.
- Source outcomes, parent grouping, ended expiry, human waits, silent tools,
  unknown liveness, limits states, cache dates, durable generations/claims across
  restart, concurrent claims, OS failure and Gio click dispatch have regressions.

## Deferred acceptance and Mac work

No live read-scoped pairing, authenticated T3 feed/quota readback, OS banner or
operated GTK/WebKit desktop journey was claimed. These need owner-approved local
activation and actual desktop acceptance before release. A source-version mismatch
or missing quota evidence must remain an honest unavailable/unsupported outcome.
More than 32 aged threads per poll can leave liveness unknown; no false alarm is
manufactured. A slow source/desktop can exceed the target notification latency.

**Mac is deferred by owner priority; Swift sources are unchanged this phase.**
No swift/swiftc is available here; no Mac verification claim. Later Mac work:

1. Consume API v2, rename legacy navigation and allow generated opaque thread IDs
   under the strict desktop/web policy. Keep native session recovery.
2. Add local Settings UI for the two preferences; no agent controls.
3. Add UserNotifications authorization, periodic pending-event polling, atomic
   reservations and confirmed-send claims; open validated desktop thread links on click.
4. Operate LaunchAgent supervision, loopback proofs, visibility/session expiry,
   notification delivery/click and actual macOS host/provider quotas on a real Mac.

No new product decision is required. Pairing/access selection and installation
remain explicit owner approval steps for the parent; do not activate them implicitly.

## Owner settings addendum (12 Nov)

Contract-first commit **73e20e5** replaces the early development preference names
with **endedExpiryHours** (default 24, clamped 1..168) and **stuckMinutes**
(default 15, clamped 5..120). GET /api/settings returns both effective `settings`
and factory `defaults`; owner-authenticated, same-origin JSON POST replaces both
fields and echoes normalized values. Unknown/missing keys, invalid types, boolean,
fractional and nonfinite numbers are refused before any write. PUT remains 405.

Atomic 0600 nagi-settings.json persists per machine in the shared data directory.
Exact legacy preference files are read compatibly without an automatic write;
seconds round up to minutes and new bounds apply. The next authorized save writes
the current field names. Legacy public request keys are refused.

Saving invalidates the current poll throttle. The next feed/background check uses
new grouping/liveness values, and the existing notifier observes those transitions
without restarting. Threshold changes now preserve first transitions for an existing silence; the
run/activity key prevents repeats. This supersedes the early rebaseline behavior.
Ended-expiry changes do not suppress a genuine stuck transition.

New regressions prove write auth/origin/JSON guards, defaults, clamping, rejected
fields/types preserving the last saved values, 0600 storage, restart persistence,
legacy-file compatibility, immediate grouping changes and a running notifier using
the new threshold. The isolated glance form submits minutes/hours and reflects the
server's normalized response. Original web assets and all Swift sources remain
unchanged. No installation, service or live-runtime change occurred.

## Fresh Opus review round 1 — fixes at a405dd2

Contract revision **034044c** documents the reservation/acknowledgement protocol,
recoverable warnings and source bounds. This revision supersedes the original
claim-before-send design. The review probes were read and rerun unchanged; their
skew/delayed-failure, repeated-stuck, bad-file, odd-row and recursion cases now pass.

1. **Banners:** stable local.nagi.notifications plus an idempotently prepared
   matching user .desktop entry. GTK AddNotification / freedesktop Notify replies
   are observed; errors keep events pending. Reserve/claim/release have owner auth
   and persisted leases. Fixture tests simulate GNOME InvalidApp rejection and
   prove send-before-claim ordering; no actual desktop send or installation ran.
2. **Liveness:** use T3's execution-item set including subagent/file_change/compaction;
   any unfinished running/waiting item is unknown and cannot emit a stuck alert.
3. **Odd rows:** normalize/cap display text, placeholder empty titles, remove bidi
   and line-separator controls; isolate orphan/malformed rows and detach invalid
   parent cycles. Healthy rows still transition. Shell requests omitOlderSettled=1;
   the ended group filters server-retained rows and is not complete historical paging.
4. **Recursion:** strict size/depth decoding for HTTP and WS; contain RecursionError;
   the refresh loop survives arbitrary ordinary exceptions. Total WS deadline
   covers partial frames and upgrade headers via a socket-shutdown timer.
5. **Delayed failures:** undecided missing completion evidence does not consume the
   transition; source skew up to five seconds is accepted. One event when evidence arrives.
6. **Repeated stuck:** persistent run/activity silence key prevents threshold changes
   and restarts from repeating an alert; real activity permits a later new silence.
7. **Local recovery:** invalid settings use defaults with settings_invalid; damaged
   journal resets with journal_reset. Authenticated valid saves repair owner-owned
   regular files to 0600. Unsafe foreign/link files are not overwritten. Vanished
   conditions prune seven days after last sighting.
8. **Other fixes:** network I/O is outside the shared state lock; obsolete polls
   discard their result after preferences change. Reject dot/dotdot/empty deep-link
   segments. Twenty-second polls read the local five-minute config cache, and failed
   config attempts are rate-limited too. The inspected server's empty getConfig
   request schema cannot accept deferNetworkDiscovery; cache refill can still run
   server discovery. No unsupported flag or upstream mutation is used.

Round-one verification: **145 Python / 18 Node tests passed**, no failures.
The new test_review_round1.py directly covers each item, including real trickled
upgrade-header timeout, lock responsiveness and config-cache call counts. Existing
same-user HTTP / mocked foreign-UID auth tests remain green. No Swift source changed;
Mac stays deferred. No push, deployment, install, service or live-policy change.

## Final Opus review round 2 — no third review

Contract-first commit **2043ab3** and implementation **22778c9** address the final
findings. Required suites now pass **164 Python / 19 Node**, zero failures.
The supplied probe1.py, probe2.py and probe3.py were rerun unchanged on the committed
implementation; all exited zero with the corrected output. This is direct regression
verification, not a further delegated review. No subagents or extra review round ran.

1. **Limits:** key by T3 window ID; Claude five_hour/seven_day and Codex
   primary/secondary remain headlines. Model-scoped Claude windows are optional
   secondaryWindows with labels. Unknown/invalid/duplicate extras warn and skip.
   Providers and accounts fail independently; one bad Claude snapshot cannot hide
   Codex. Tests cover scope duplicates, malformed accounts, warnings and dated cache.
2. **Long threads:** coverage concerns the current run, not all prior turns. Its
   first user-message/item proves the start; retained run metadata alone does not.
   Otherwise read at most three history pages, 2000 items, 4 MiB, eight seconds.
   Snapshot-sequence mismatch, opaque/deferred evidence or budget exhaustion stays
   unknown. Tests include >10-turn histories with covered stuck and active runs,
   paging, cursor escaping, budgets and stale run metadata.
3. **Threshold edits:** remove rebaselining. Lowering 30 to 15 after 20 minutes
   emits the first event, including after an intervening failed poll; the same
   silence never repeats after more settings changes or restart.
4. **Omissions/Ended:** count skipped rows and report rows_omitted, including an
   otherwise empty partial snapshot (ok + warning, never quiet). Failed rows lacking
   latestRunCompletedAt appear in Ended with updatedAt and endedAtSource=updatedAt.
5. **Clock steps:** future events stay in the journal, hidden/unclaimable until
   time catches up, and then reappear; normal poll throttling also tolerates a
   backwards step. Forward expiry still prunes past 24 hours.
6. **Clicks:** one app.open-thread string-target action is registered before the
   application claims its bus name. Serialized banner targets work after restart.
   The installer prepares matching local.nagi.notifications.service under the
   user's dbus-1/services directory, idempotently. D-Bus starts the headless notifier
   and registers the action without a tray or reader prerequisite. GTK uses this
   activation path; freedesktop fallback actions remain tied to the sending process.
7. **Destroy:** widget destroy calls the guarded stop_notifier helper; a missing
   notifier is harmless. A regression invokes the actual nested destroy callback
   with None and a valid timer, without launching GTK.
8. **HTTP deadlines:** the shared deadline guard covers connect, peer verification,
   headers and body for HTTP and WS. Regressions trickle real loopback headers and
   bodies, and prove a connect phase can exhaust the budget before credentials send.

Legacy cache compatibility preserves pending/claimed transitions: old agent display
caches get the new optional-display defaults; old quota rows lacking window IDs
are declined rather than inventing IDs or discarding the journal. Installed Gio's
string-target API was inspected without registering an application or sending a
notification. New placeholder rendering tests show omission warnings and keep
model-scoped limits separate from account headlines.

**Verification limits remain:** no live read-scoped pairing/quota readback, actual
GTK banner/action/activation, installed user D-Bus service or Mac operation was
performed. Install tests use temporary homes only; activation tests use mocked GI.
Mac Swift sources remain unchanged. No install, push, service/account/exposure
change, live-runtime write or outside policy change occurred. The known desktop
acceptance/claim crash boundary remains documented; confirmed claims stay deduped,
while an uncertain accepted-but-unclaimed send can retry after lease expiry.

## Code review (PR #2), 13 Nov — truth-state fixes

Additive DTO and contract changes, each with a regression test that failed first:

- **Per-account limits.** Every installed, enabled account keeps its own line with
  `status`, `checkedAt` and `reason`. A failed probe falls back to that account's own
  unexpired cache (dated), else an empty unavailable line; the provider stays ok and warns
  `account_unavailable`. Labels number accounts in this computer's order, so they stay
  stable whichever account fails. The journal validator accepts the three fields, so the
  per-account cache survives restarts; a whole-provider last_known marks every retained
  account last_known.
- **Cyclic lineage** raises CyclicLineage before any parent is detached: agents become
  last_known or unavailable with reason `cyclic_lineage`, limits from the same read stand,
  and transition conditions are left untouched.
- **Native tray:** `empty` and its tooltip need a fresh ok account with an unexpired window;
  retained quota adds `limits as of HH:mm`. The shared case table covers the stale cases.
- **Panel:** per-account dated lines, windows filtered against now on every render, and no
  `Nothing ran` when threads were omitted.
- **Window shell:** GTK input shape limits clicks to the visible panel
  (`widget.apply_input_shape`), recomputed on every size change; it degrades to a fully
  clickable window when cairo's GI bridge is missing.

## Project icons (owner request, 13 Nov)

- `project_icons.py` validates T3's projectIcon to T3's own schema (monogram, emoji,
  lucide; legacy lucide monograms; unknown kinds ignored) and mints opaque 32-hex keys.
- The reader's single RPC path admits only `server.getConfig` and `assets.createUrl` for
  `project-favicon` resources (orchestration:read); anything else raises before a socket
  opens. Favicon bytes come from T3's signed same-origin `/api/assets/` path without the
  bearer token: at most 256 KB, typed and magic-byte checked.
- `GET /api/project-icon/<key>` serves them owner-authenticated, no-store, nosniff, with a
  sandbox CSP; misses are cached for the 30-minute bucket, T3 outages for a minute. The
  journal accepts the projects' `icon` field. Transport is origin-generic.
