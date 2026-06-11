#!/bin/bash
# Build VibeBoard.app -- a signed .app bundle.
#
# Notifications (UNUserNotificationCenter) require the process to run inside a
# bundle with a CFBundleIdentifier, signed (ad-hoc is fine locally). Running the
# bare `swift run VibeBoard` executable has no bundle id, so notifications no-op
# there by design -- use this bundle to get them.
#
# Usage:
#   ./build-app.sh            # release build -> .build/VibeBoard.app
#   ./build-app.sh && open .build/VibeBoard.app

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

echo "Assembling ${APP} ..."
rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"
cp "${SCRIPT_DIR}/Info.plist" "${APP}/Contents/Info.plist"
cp "${BIN}" "${APP}/Contents/MacOS/VibeBoard"

echo "Code-signing (ad-hoc)..."
codesign --force --sign - \
	--entitlements "${SCRIPT_DIR}/VibeBoard.entitlements" \
	"${APP}"

echo ""
echo "Built ${APP}"
echo "Run it with:  open \"${APP}\""
echo "(First launch asks to allow notifications.)"
