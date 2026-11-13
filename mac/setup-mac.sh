#!/usr/bin/env bash
# Set up Nagi on this Mac: build and install Nagi.app, start the local reader and
# launch at login. Idempotent and re-runnable. Never prints a token, never uses sudo,
# and never replaces an existing credential or saved source.
#
#   mac/setup-mac.sh                                        # install or update; connect sources in Nagi
#   mac/setup-mac.sh --t3-origin http://100.101.102.103:3773   # (upgrades) keep a tailnet T3 policy
#   mac/setup-mac.sh --t3-local                             # (optional) pair with this Mac's own T3 Code
#
# Usually you run ./install.sh, then add sources in Nagi (right-click 凪 → Sources…).
# Remote token: mint it on the T3 host and pipe it in, e.g.
#   ssh linux-host '<t3 auth session issue … --token-only>' | mac/setup-mac.sh --t3-origin URL --token-stdin
# An existing credential file is always kept.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
MAC_DIR="$PWD"
REPO="$(cd .. && pwd)"
PORT=47831
T3_ORIGIN=''
T3_LOCAL=0
TOKEN_STDIN=0
LAUNCH=1
while [[ $# -gt 0 ]]; do
    case "$1" in
        --t3-origin) T3_ORIGIN="${2:-}"; shift 2 ;;
        --t3-local) T3_LOCAL=1; shift ;;
        --token-stdin) TOKEN_STDIN=1; shift ;;
        --port) PORT="${2:-}"; shift 2 ;;
        --no-launch) LAUNCH=0; shift ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
done
say() { printf '  %s\n' "$*"; }
fail() { printf 'Nagi setup stopped: %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == Darwin ]] || fail 'run this on a Mac.'
[[ "$PORT" =~ ^[1-9][0-9]{3,4}$ ]] && (( PORT >= 1024 && PORT <= 65535 )) || fail 'use a port between 1024 and 65535.'
[[ -n "$T3_ORIGIN" && "$T3_LOCAL" == 1 ]] && fail 'choose either --t3-origin or --t3-local.'
[[ "$(id -u)" != 0 ]] || fail 'run as yourself, not root.'

echo 'Nagi setup'
# 1. Toolchain: Swift from Xcode or the Command Line Tools, Python 3.11+.
if ! /usr/bin/xcrun --find swift >/dev/null 2>&1; then
    fail 'no Swift toolchain. Install the Command Line Tools with `xcode-select --install` (or Xcode from the App Store), then run this again.'
fi
PY=''
for candidate in "${NAGI_PYTHON:-}" /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
                 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 "$(command -v python3 || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then PY="$candidate"; break; fi
done
[[ -n "$PY" ]] || fail 'Nagi’s reader needs Python 3.11 or newer. Install it with `brew install python@3.13`, then run this again.'
say "Swift: $(/usr/bin/xcrun swift --version 2>/dev/null | head -1)"
say "Python: $PY"

NAGI_HOME="$HOME/Library/Application Support/Nagi"
mkdir -p "$NAGI_HOME" && chmod 700 "$NAGI_HOME"
DATA_DIR="$("$PY" -B "$REPO/runtime_paths.py")"
CREDENTIAL="$NAGI_HOME/t3-credential.json"
helper() { "$PY" -B "$MAC_DIR/setup_helper.py" "$@"; }

# 2. Reader LaunchAgent (prepared by the shared installer: owner secret, plist, locator).
NAGI_PYTHON="$PY" "$MAC_DIR/install-reader.sh" --port "$PORT" --data-dir "$DATA_DIR" >/dev/null
say "Reader data: $DATA_DIR"

# 3. T3 source. Remote: one tailnet origin. Local: this Mac's T3 Code, paired read-only.
issue_local_token() {
    local app exe entry
    local args=(auth session issue --scope orchestration:read --label 'Nagi (read-only, this computer)' --ttl 365d --token-only --log-level none)
    for app in /Applications/T3\ Code*.app "$HOME"/Applications/T3\ Code*.app; do
        [[ -d "$app" ]] || continue
        exe="$app/Contents/MacOS/$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$app/Contents/Info.plist" 2>/dev/null || true)"
        entry="$app/Contents/Resources/app.asar.unpacked/apps/server/dist/bin.mjs"
        [[ -f "$entry" ]] || entry="$app/Contents/Resources/app.asar/apps/server/dist/bin.mjs"
        if [[ -x "$exe" && -e "$app/Contents/Resources/app.asar" ]]; then
            ELECTRON_RUN_AS_NODE=1 "$exe" "$entry" "${args[@]}" | helper credential-from-stdin "$CREDENTIAL"
            return
        fi
    done
    if command -v t3 >/dev/null 2>&1; then
        t3 "${args[@]}" | helper credential-from-stdin "$CREDENTIAL"
        return
    fi
    fail 'T3 Code isn’t installed here. Install it, or use --t3-origin for another machine’s T3.'
}
find_local_origin() {
    local port
    for port in ${NAGI_T3_PORT:-} 3773 $(/usr/sbin/lsof -nP -iTCP@127.0.0.1 -sTCP:LISTEN 2>/dev/null \
            | awk 'tolower($1) ~ /^t3/ { n = split($9, a, ":"); print a[n] }' | sort -un); do
        if helper t3-ok "http://127.0.0.1:$port"; then echo "http://127.0.0.1:$port"; return; fi
    done
    fail 'can’t find T3 Code’s server on this Mac. Open T3 Code, then run this again (or set NAGI_T3_PORT).'
}

if [[ -e "$DATA_DIR/nagi-sources.json" || -L "$DATA_DIR/nagi-sources.json" ]]; then
    say 'Sources are managed in Nagi; leaving legacy policy and credentials alone.'
elif [[ "$T3_LOCAL" == 1 ]]; then
    T3_ORIGIN="$(find_local_origin)"
    if ! helper credential-ok "$CREDENTIAL"; then
        [[ -e "$CREDENTIAL" ]] && fail "the existing credential file isn’t valid; move it aside and run this again."
        issue_local_token || fail 'T3 Code could not issue a read-only session. Nothing was saved.'
    fi
elif [[ -n "$T3_ORIGIN" ]]; then
    kind="$(helper origin-kind "$T3_ORIGIN")" || fail 'use http://127.0.0.1:<port>, http://<Tailscale 100.x address>:<port> or https://<name>.ts.net.'
    if [[ "$TOKEN_STDIN" == 1 ]]; then
        helper credential-from-stdin "$CREDENTIAL" || fail 'the piped token was refused; nothing was saved.'
    fi
    say "T3 source: $T3_ORIGIN ($kind)"
fi
if [[ -n "$T3_ORIGIN" && ! -e "$DATA_DIR/nagi-sources.json" && ! -L "$DATA_DIR/nagi-sources.json" ]]; then
    helper policy "$DATA_DIR" "$T3_ORIGIN" "$CREDENTIAL" || fail 'could not write the T3 policy.'
fi
if [[ -f "$DATA_DIR/nagi-sources.json" ]]; then
    source_state='managed in Nagi (right-click 凪 → Sources…)'
elif [[ -f "$DATA_DIR/nagi-t3.json" ]]; then
    origin="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["origin"])' "$DATA_DIR/nagi-t3.json")"
    if helper credential-ok "$CREDENTIAL"; then token_state='read-only token present'; else token_state='TOKEN MISSING: pipe one in with --token-stdin'; fi
    if helper t3-ok "$origin"; then t3_state='reachable'; else t3_state='NOT reachable right now'; fi
    source_state="T3 at $origin · $t3_state · $token_state"
else
    source_state='none yet: open Nagi and connect your agent apps there'
fi

# NAGI_SKIP_SERVICES=1 (tests, disposable homes): install files only; never touch
# launchd or a running Nagi, which belong to the real installation.
SKIP_SERVICES="${NAGI_SKIP_SERVICES:-0}"

# 4. Build and install Nagi.app (quit the running copy first).
"$MAC_DIR/build-app.sh" "http://127.0.0.1:$PORT/glance" "$DATA_DIR" >/dev/null
APP="$HOME/Applications/Nagi.app"
APP_AGENT="$HOME/Library/LaunchAgents/local.nagi.app.plist"
GUI="gui/$(id -u)"
if [[ "$SKIP_SERVICES" != 1 ]]; then
    /bin/launchctl bootout "$GUI/local.nagi.app" 2>/dev/null || true
    /usr/bin/pkill -x -u "$(id -u)" Nagi 2>/dev/null || true
fi
mkdir -p "$HOME/Applications"
rm -rf "$APP.new" && /usr/bin/ditto "$MAC_DIR/dist/Nagi.app" "$APP.new"
rm -rf "$APP" && mv "$APP.new" "$APP"
say "App: $APP"

# 5. (Re)start the reader so it reads the current policy; wait for it to answer.
bootstrap() {
    local label="$1" plist="$2"
    /bin/launchctl bootout "$GUI/$label" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        /bin/launchctl bootstrap "$GUI" "$plist" 2>/dev/null && return 0
        sleep 1
    done
    return 1
}
if [[ "$SKIP_SERVICES" != 1 ]]; then
    bootstrap local.nagi.reader "$HOME/Library/LaunchAgents/local.nagi.reader.plist" || fail 'launchd would not start the reader.'
    for _ in $(seq 1 20); do
        /usr/bin/curl -fsS --max-time 1 -o /dev/null "http://127.0.0.1:$PORT/glance" 2>/dev/null && break
        sleep 0.5
    done
    /usr/bin/curl -fsS --max-time 2 -o /dev/null "http://127.0.0.1:$PORT/glance" || fail "the reader isn’t answering on 127.0.0.1:$PORT. See: log show --last 5m --predicate 'process == \"Python\"'"
    say "Reader: http://127.0.0.1:$PORT (LaunchAgent local.nagi.reader)"
else
    say 'Reader and app agents: prepared, not started (NAGI_SKIP_SERVICES=1)'
fi

# 6. Launch at login (LaunchAgent; quitting from the menu keeps it quit until next login).
helper app-agent "$APP_AGENT" "$APP"
if [[ "$LAUNCH" == 1 && "$SKIP_SERVICES" != 1 ]]; then
    bootstrap local.nagi.app "$APP_AGENT" || fail 'launchd would not start Nagi.app.'
fi

echo 'Done.'
say "Sources: $source_state"
say 'Menu bar: 凪 · click it for the glance, right-click for Settings…, Sources… and Quit.'
say 'macOS asks once to allow Nagi’s notifications; allow them for failed and stuck banners.'
