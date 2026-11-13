#!/usr/bin/env bash
# Install Nagi on this computer, then open it. Linux or macOS. Safe to run again.
#
#   ./install.sh               install (or update) and open Nagi
#   ./install.sh --no-launch   install without opening Nagi
#
# Everything goes into your home folder. Nagi never needs sudo; if your Linux desktop is
# missing a system library, this script tells you which one and asks before using sudo.
# An existing Nagi data folder, its owner key and any saved connection are always kept.
# Connecting T3 Code happens afterwards, inside Nagi.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
ROOT="$PWD"
PORT="${NAGI_PORT:-47831}"
LAUNCH=1
for arg in "$@"; do
    case "$arg" in
        --no-launch) LAUNCH=0 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) printf 'Unknown option: %s (try ./install.sh --help)\n' "$arg" >&2; exit 2 ;;
    esac
done

ok()   { printf '  \342\234\223 %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
stop() { printf '\n  \342\234\227 %s\n' "$1" >&2; shift; for line in "$@"; do printf '    %s\n' "$line" >&2; done; exit 1; }

# The reader answers this version's sources API: a private route says 401 (owner proof
# needed). An older reader that is still running answers 404, and nothing answers at all
# while it starts.
api_ready() {
    local py="$1"
    for _ in $(seq 1 50); do
        "$py" - "$PORT" <<'PY' 2>/dev/null && return 0
import sys, urllib.request, urllib.error
port = int(sys.argv[1])
try:
    urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/api/sources/v1/catalog'), timeout=1)
except urllib.error.HTTPError as error:
    sys.exit(0 if error.code == 401 else 1)
except Exception:
    sys.exit(1)
sys.exit(1)
PY
        sleep 0.2
    done
    return 1
}

[[ "$(id -u)" != 0 ]] || stop 'Run this as yourself, not as root.' 'Nagi installs into your home folder.'
[[ "$PORT" =~ ^[1-9][0-9]{3,4}$ ]] && (( PORT >= 1024 && PORT <= 65535 )) || stop 'NAGI_PORT must be a port between 1024 and 65535.'

install_linux() {
    printf 'Installing Nagi on this Linux computer\n'
    local py="${NAGI_PYTHON:-python3}"
    command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null \
        || stop 'Nagi needs Python 3.11 or newer.' 'Install it with your package manager, then run ./install.sh again.'
    ok "Python $("$py" -c 'import platform; print(platform.python_version())')"

    # The tray and panel use GTK 3, WebKitGTK 4.1 and Ayatana AppIndicator from the system.
    local probe="import gi; gi.require_version('Gtk','3.0'); gi.require_version('WebKit2','4.1'); gi.require_version('AyatanaAppIndicator3','0.1'); from gi.repository import Gtk, WebKit2, AyatanaAppIndicator3"
    if ! "$py" -c "$probe" >/dev/null 2>&1; then
        local packages='gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-ayatanaappindicator3-0.1 python3-gi python3-gi-cairo'
        printf '\n  Nagi'"'"'s tray needs a few desktop libraries that are not installed yet:\n    %s\n' "$packages"
        if command -v apt-get >/dev/null 2>&1 && [[ -t 0 ]]; then
            printf '  Installing system libraries needs your password (sudo). Install them now? [y/N] '
            read -r answer
            if [[ "$answer" == [yY]* ]]; then
                # shellcheck disable=SC2086
                sudo apt-get install -y $packages || stop 'The libraries could not be installed.' "Install them yourself: sudo apt-get install $packages"
            else
                stop 'Nagi needs those libraries for its tray.' "Install them, then run ./install.sh again: sudo apt-get install $packages"
            fi
        else
            stop 'Nagi needs those libraries for its tray.' 'Install them with your package manager, then run ./install.sh again.'
        fi
        "$py" -c "$probe" >/dev/null 2>&1 || stop 'The desktop libraries still could not be loaded.' 'Log out and back in, then run ./install.sh again.'
    fi
    ok 'Desktop libraries'

    # Prepares (never overwrites) the data folder, its owner key, the reader service and the notifier.
    "$py" -B install_reader.py --port "$PORT" --python "$(command -v "$py")" >/dev/null \
        || stop 'Nagi could not prepare its reader.' 'Check that your home folder is yours and not full, then run ./install.sh again.'
    ok 'Reader prepared in your home folder'

    command -v systemctl >/dev/null 2>&1 || stop 'This computer has no systemd user session.' 'Start the reader yourself: python3 -B server.py'
    # enable --now leaves an already-running (older) reader alone, so restart it explicitly.
    local before after
    before="$(systemctl --user show -p MainPID --value nagi-reader.service 2>/dev/null || true)"
    systemctl --user daemon-reload >/dev/null 2>&1 \
        && systemctl --user enable nagi-reader.service >/dev/null 2>&1 \
        && systemctl --user restart nagi-reader.service >/dev/null 2>&1 \
        || stop 'The reader service did not start.' 'See what happened with: systemctl --user status nagi-reader.service'
    # Done only when a new reader process is up and answers this version's sources API.
    api_ready "$py" \
        && systemctl --user is-active --quiet nagi-reader.service \
        && after="$(systemctl --user show -p MainPID --value nagi-reader.service 2>/dev/null)" \
        && [[ "$after" =~ ^[1-9][0-9]*$ && "$after" != "$before" ]] \
        || stop 'The reader is not answering with this version yet.' \
            'Restart it with: systemctl --user restart nagi-reader.service' \
            'If an older Nagi reader was started by hand, quit it first.' \
            'If that does not help, see: systemctl --user status nagi-reader.service'
    ok 'Reader running this version'

    # The tray starts with your desktop. An existing autostart entry is kept as it is.
    local autostart="$HOME/.config/autostart/local.nagi.tray.desktop"
    if [[ ! -e "$autostart" ]]; then
        mkdir -p "$(dirname "$autostart")"
        local exec_line
        exec_line="$(printf '%q ' "$(command -v "$py")" -B "$ROOT/linux/tray.py" --port "$PORT")"
        printf '[Desktop Entry]\nType=Application\nName=Nagi\nComment=What your agents are doing, at a glance\nExec=%s\nTerminal=false\nX-GNOME-Autostart-enabled=true\n' "${exec_line% }" > "$autostart"
    fi
    ok 'Nagi starts with your desktop'

    if (( LAUNCH )); then
        # A running tray keeps its single instance; a second start simply exits.
        setsid -f "$py" -B "$ROOT/linux/tray.py" --port "$PORT" >/dev/null 2>&1 < /dev/null || true
        ok 'Nagi is open: look for 凪 in the top bar'
    fi
}

install_mac() {
    printf 'Installing Nagi on this Mac\n'
    local args=(--port "$PORT")
    (( LAUNCH )) || args+=(--no-launch)
    # Builds Nagi.app, starts the reader and launches at login; connecting happens inside Nagi.
    # setup-mac.sh restarts the reader (launchd bootout, then bootstrap) before Nagi opens.
    mac/setup-mac.sh "${args[@]}" || stop 'The Mac setup stopped.' 'Read the message above, fix it, then run ./install.sh again.'
    local py="${NAGI_PYTHON:-python3}"
    api_ready "$py" || stop 'The reader is not answering with this version yet.' \
        'Restart it with: launchctl kickstart -k gui/$(id -u)/local.nagi.reader' \
        'Then run ./install.sh again.'
    ok 'Nagi installed and its reader is running this version'
    (( LAUNCH )) && ok 'Nagi is open: look for 凪 in the menu bar'
    return 0
}

case "$(uname -s)" in
    Linux) install_linux ;;
    Darwin) install_mac ;;
    *) stop 'This computer is not supported yet.' 'Nagi runs on Linux and macOS.' ;;
esac

printf '\nDone. In Nagi, choose the agent apps to watch; it walks you through connecting them.\n'
