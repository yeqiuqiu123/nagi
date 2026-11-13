#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ "$(uname -s)" != Linux ]]; then echo 'Install on Linux with Python 3.11+.' >&2; exit 1; fi
"${NAGI_PYTHON:-python3}" -B install_reader.py "$@"
