#!/bin/bash
# Build VibeBoard.app -- a signed .app bundle.
#
# Notifications (UNUserNotificationCenter) require the process to run inside a
# bundle with a CFBundleIdentifier, signed (ad-hoc is fine locally). Running the
# bare `swift run VibeBoard` executable has no bundle id, so notifications no-op
# there by design -- use this bundle to get them.
#
# After building, this quits any running instance and launches the fresh build.
#
# Usage:
#   ./build-app.sh            # release build -> .build/VibeBoard.app, then launch
#   ./build-app.sh debug      # debug build

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

CONFIG="${1:-release}"
APP="${SCRIPT_DIR}/.build/VibeBoard.app"

echo "Building VibeBoard (${CONFIG})..."
# The SMB volume can transiently fail the compiler index store; disable it for a
# clean, reproducible bundle build.
swift build -c "${CONFIG}" --disable-index-store

BIN="$(swift build -c "${CONFIG}" --disable-index-store --show-bin-path)/VibeBoard"
if [[ ! -x "${BIN}" ]]; then
	echo "error: built executable not found at ${BIN}" >&2
	exit 1
fi

# Quit any running instance BEFORE reassembling the bundle: a running app holds
# its executable busy, so `rm -rf` of the .app would fail (and on this SMB volume
# leaves `.smbdelete` stragglers). Quitting first lets us overwrite cleanly and
# guarantees `open` launches the fresh binary rather than no-op'ing on the
# already-running menubar app.
#
# A plain SIGTERM (pkill's default) is used rather than an AppleScript `quit`:
# scripting another app needs macOS Automation (TCC) permission, and without it
# `osascript … to quit` blocks indefinitely on the approval prompt. SIGTERM needs
# no permission and AppKit exits cleanly on it; SIGKILL is a last-resort fallback.
if pgrep -x VibeBoard >/dev/null 2>&1; then
	echo "Quitting running VibeBoard..."
	pkill -x VibeBoard >/dev/null 2>&1 || true
	# Wait up to ~3s for a graceful exit, then force-kill any straggler so the
	# bundle is free to overwrite.
	for _ in $(seq 1 15); do
		pgrep -x VibeBoard >/dev/null 2>&1 || break
		sleep 0.2
	done
	pkill -9 -x VibeBoard >/dev/null 2>&1 || true
fi

echo "Assembling ${APP} ..."
rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"
cp "${SCRIPT_DIR}/Info.plist" "${APP}/Contents/Info.plist"
cp "${BIN}" "${APP}/Contents/MacOS/VibeBoard"

echo "Code-signing (ad-hoc)..."
codesign --force --sign - \
	--entitlements "${SCRIPT_DIR}/VibeBoard.entitlements" \
	"${APP}"

echo "Built ${APP}"
echo "Launching ${APP} ..."
open "${APP}"
echo "(First launch asks to allow notifications.)"
