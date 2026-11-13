#!/usr/bin/env bash
# Build mac/dist/Nagi.app: a locally signed menu-bar app (LSUIElement, no Dock icon).
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$(uname -s)" != Darwin ]]; then echo 'Build on a Mac with Xcode or the Command Line Tools.' >&2; exit 1; fi
if [[ "$#" -gt 2 ]]; then echo 'Usage: ./build-app.sh [http://127.0.0.1:47831/glance] [runtime-data-dir]' >&2; exit 2; fi
GLANCE_URL="${1:-http://127.0.0.1:47831/glance}"
NAGI_RUNTIME_DIR="${2:-$("${NAGI_PYTHON:-python3}" -B ../runtime_paths.py)}"
# Exact IPv4 loopback origin, no userinfo, query, fragment or extra path.
if [[ ! "$GLANCE_URL" =~ ^http://127\.0\.0\.1:([1-9][0-9]{3,4})/glance$ ]] || (( BASH_REMATCH[1] < 1024 || BASH_REMATCH[1] > 65535 )); then
    echo 'Use this computer’s loopback Nagi address, e.g. http://127.0.0.1:47831/glance.' >&2; exit 2
fi
case "$NAGI_RUNTIME_DIR" in "$HOME"/*) ;; *) echo 'Use a runtime directory inside your home.' >&2; exit 2 ;; esac
# One source build; no downloaded packages, signing identity or account access.
swift build -c release --product Nagi
bin_dir="$(swift build -c release --show-bin-path)"
mkdir -p dist
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/nagi-build.XXXXXX")"
app="$build_dir/Nagi.app"
plist="$app/Contents/Info.plist"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$bin_dir/Nagi" "$app/Contents/MacOS/Nagi"
/usr/bin/plutil -create xml1 "$plist"
/usr/bin/plutil -insert CFBundleExecutable -string Nagi "$plist"
/usr/bin/plutil -insert CFBundleIdentifier -string local.nagi.app "$plist"
/usr/bin/plutil -insert CFBundleName -string Nagi "$plist"
/usr/bin/plutil -insert CFBundleDisplayName -string Nagi "$plist"
/usr/bin/plutil -insert CFBundleVersion -string 9 "$plist"
/usr/bin/plutil -insert CFBundleShortVersionString -string 0.9.0 "$plist"
/usr/bin/plutil -insert CFBundlePackageType -string APPL "$plist"
/usr/bin/plutil -insert LSUIElement -bool YES "$plist"
/usr/bin/plutil -insert LSMinimumSystemVersion -string 14.0 "$plist"
/usr/bin/plutil -insert NSHighResolutionCapable -bool YES "$plist"
/usr/bin/plutil -insert NagiGlanceURL -string "$GLANCE_URL" "$plist"
/usr/bin/plutil -insert NagiDataDirectory -string "$NAGI_RUNTIME_DIR" "$plist"
/usr/bin/plutil -insert NSAppTransportSecurity -json '{"NSAllowsLocalNetworking":true}' "$plist"
# Remove only Finder/resource-fork build metadata; keep quarantine and security attributes.
while IFS= read -r -d '' entry; do
    while IFS= read -r attr; do
        case "$attr" in
            com.apple.FinderInfo|com.apple.ResourceFork) /usr/bin/xattr -d "$attr" "$entry" ;;
        esac
    done < <(/usr/bin/xattr "$entry")
done < <(/usr/bin/find "$app" -print0)
# Local ad-hoc integrity signing only. Never disable Gatekeeper or use an account.
/usr/bin/codesign --force --sign - --identifier local.nagi.app "$app"
/usr/bin/codesign --verify --strict "$app"
rm -rf dist/Nagi.previous.app
if [[ -e dist/Nagi.app ]]; then mv dist/Nagi.app dist/Nagi.previous.app; fi
mv "$app" dist/Nagi.app
rmdir "$build_dir"
printf '%s\n' 'Built mac/dist/Nagi.app (locally signed, not notarized).'
