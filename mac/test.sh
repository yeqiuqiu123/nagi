#!/usr/bin/env bash
# `swift test` for NagiCore. With only the Command Line Tools, Swift Testing sits
# outside SwiftPM's default search paths, so point every target (including the
# generated test runner) at it. With Xcode selected this is plain `swift test`.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
developer="$(xcode-select -p 2>/dev/null || true)"
frameworks="$developer/Library/Developer/Frameworks"
libraries="$developer/Library/Developer/usr/lib"
if [[ "$developer" == */CommandLineTools && -d "$frameworks/Testing.framework" ]]; then
    exec swift test -Xswiftc -F -Xswiftc "$frameworks" \
        -Xlinker -F -Xlinker "$frameworks" \
        -Xlinker -rpath -Xlinker "$frameworks" -Xlinker -rpath -Xlinker "$libraries" "$@"
fi
exec swift test "$@"
