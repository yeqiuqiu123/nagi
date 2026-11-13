#!/usr/bin/env bash
# Remove Nagi from this Mac: stop and remove the app and reader LaunchAgents and
# ~/Applications/Nagi.app. Keeps the data and the read-only T3 credential unless
# --purge is given. Never uses sudo; touches nothing outside your home.
set -euo pipefail
PURGE=0
[[ "${1:-}" == --purge ]] && PURGE=1
[[ "$(uname -s)" == Darwin ]] || { echo 'Run this on a Mac.' >&2; exit 1; }
GUI="gui/$(id -u)"
for label in local.nagi.app local.nagi.reader; do
    /bin/launchctl bootout "$GUI/$label" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/$label.plist"
done
/usr/bin/pkill -x -u "$(id -u)" Nagi 2>/dev/null || true
rm -rf "$HOME/Applications/Nagi.app"
NAGI_HOME="$HOME/Library/Application Support/Nagi"
if [[ "$PURGE" == 1 ]]; then
    rm -rf "$NAGI_HOME"
    echo 'Removed Nagi, its data and its T3 credential file.'
    echo 'Also revoke the session in T3 Code: Settings → Connections → "Nagi (read-only, …)".'
else
    echo "Removed Nagi.app and its LaunchAgents. Data and credential kept in $NAGI_HOME (run with --purge to remove)."
fi
