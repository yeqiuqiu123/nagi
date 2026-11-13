#!/bin/bash
# Prepare the per-user reader LaunchAgent (local.nagi.reader); setup-mac.sh starts it.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ "$(uname -s)" != Darwin ]]; then echo 'Install on a Mac with Python 3.11+.' >&2; exit 1; fi
# The reader needs Python 3.11+; macOS's own python3 is 3.9. Prefer an explicit choice.
python=''
for candidate in "${NAGI_PYTHON:-}" /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
                 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 "$(command -v python3 || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then python="$candidate"; break; fi
done
if [[ -z "$python" ]]; then echo 'Install Python 3.11+ first, e.g. `brew install python@3.13`.' >&2; exit 1; fi
"$python" -B install_reader.py --python "$python" "$@"
