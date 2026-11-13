# The local reader

How Nagi's reader works, for contributors. The [README](../README.md) covers install and use; the exact response shapes are in [api-contract.md](api-contract.md) and [sources-api.md](sources-api.md).

## Running it

Python **3.11+**, standard library only. Existing imported contracts use
`datetime.UTC` and `typing.NotRequired`; macOS Xcode Python 3.9 is insufficient.
Use Homebrew Python 3.11+ on a future Mac setup.

Start a disposable reader with its own data directory and free port:

```sh
mkdir -m 700 -p data
python3 -B server.py --port 47841 --data-dir "$PWD/data"
python3 -B owner_auth.py --port 47841 --data-dir "$PWD/data" --path /glance
```

With no T3 policy the glance says **not set up on this computer**. It never invents
agents, quota numbers or zero usage. Read-only setup uses a separately authorized
`t3 pair --scope orchestration:read` credential. See the contract for the exact
owner-only `nagi-t3.json` and credential-file shapes. Pairing/installation is not
performed by starting this reader. No T3 database or provider credential stores are
read. Cached provider quotas come from T3, including Claude's Agent SDK windows. Config snapshots are cached for five minutes so normal
20-second polls do not repeat discovery. This T3 version has no discovery-free
getConfig option; a cache refill may still discover. Quota check dates stay dated.
Source window IDs identify account headlines; model-scoped Claude windows appear
as optional secondary limits. Unexpected windows warn and do not hide the other
provider. Both HTTP and WebSocket reads have total deadlines.

The reader polls every 20 seconds. An owner-only transition journal and dated
metadata cache survive restart. Settings tune the 15-minute inactivity threshold
and 24-hour ended group. Settings use `stuckMinutes` (5–120) and
`endedExpiryHours` (1–168); GET returns current values and defaults, and
owner-authenticated JSON POST clamps integer values and applies them without a
restart. Long open tools, human requests and child waits suppress
stuck alarms; history checks cover the current run, paging within bounded budgets
when its start is outside the initial window; incomplete liveness evidence is unknown. Failed/stuck transitions
produce one durable event each. The Linux tray/glance reserves events, sends through an acknowledged desktop DBus
call, then confirms delivery. Rejected sends remain pending. The prepared Linux
installer writes the stable local.nagi.notifications desktop entry required by
GNOME; it must be installed before banners can be accepted. A matching user D-Bus
service restores the stable open-thread action when an old banner is clicked after
the tray closes or restarts; the action target carries only a validated thread link. A click opens T3
desktop first, with web fallback. A crash after desktop acceptance but before the
durable claim can cause a retry; no exactly-once desktop guarantee is claimed.
Both reader and graphical consumer must run for notifications. Invalid local
settings fall back to defaults with a warning; an authorized settings save repairs
owner-owned regular preference/journal files. Thread conditions expire after seven
days unseen. Backward clock steps hold future notification events until time
catches up. Lowering the stuck threshold may emit a first alert for an existing
silence; later settings changes cannot repeat that same alert. Failed rows without
a completion timestamp use a qualified last-activity time in Ended. Omitted rows
are counted and warned, and never produce a silent quiet outcome.

```sh
python3 -B -m pytest tests -q          # tests/conftest.py isolates HOME and blocks the network
node --test tests/*.test.cjs
# Without pytest: never let the suite see your real sign-ins.
HOME="$(mktemp -d)" CODEX_HOME= python3 -B -m unittest discover -s tests
```

## Local owner boundary

Every API requires an owner proof or unexpired random session. The reader binds
only 127.0.0.1, checks exact Host/Origin/fetch metadata and, on Linux, the connecting
socket UID. Unknown/foreign ownership fails closed. The 0600 install secret never
goes on the wire: native clients verify a server HMAC before sending a one-use
request-bound client HMAC. Browser launch tickets expire after ten seconds; they
redeem into port-isolated sessionStorage tokens, sent only in API headers. There
are no auth cookies. Sessions expire after 15 minutes and on restart. Native
Linux shells reauthenticate on show, while visible every 12 minutes, and on 401.
Public HTML/static assets contain no records. Same-UID software and root remain
trusted. Private source metadata is never logged; raw prompts, transcripts,
credentials and tool output never enter API responses or the journal.

All clients/installers use runtime_paths.py. Default data is
`~/.local/share/nagi/data` on Linux and `~/Library/Application Support/Nagi/data`
on Mac; a private checkout locator preserves an explicitly chosen install path.
Native CLI overrides remain available. Computers never read each other's feeds.

## Reader only

The idempotent scripts write only within the invoking user's directories:

```sh
bash linux/install-reader.sh --data-dir "$HOME/.local/share/nagi/data"
NAGI_PYTHON=/opt/homebrew/bin/python3.11 bash mac/install-reader.sh
```

Linux stages a systemd --user reader unit; Mac stages a per-user LaunchAgent so
the reader survives window closure. No gateway unit is needed.

