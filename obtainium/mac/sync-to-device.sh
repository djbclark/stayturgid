#!/usr/bin/env bash
# Push stayturgid Obtainium configs to a phone and open Obtainium import.
# Usage:
#   ./sync-to-device.sh <p7a|s24|serial> [all|autojs6]
#
# Re-importing merges/updates existing entries (does not remove other apps).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OBTAINIUM_PKG="dev.imranr.obtainium"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: sync-to-device.sh <p7a|s24|serial> [all|autojs6]}")"
WHICH="${2:-all}"

if ! adb -s "$SERIAL" shell pm path "$OBTAINIUM_PKG" 2>/dev/null | grep -q .; then
  echo "ERROR: Obtainium ($OBTAINIUM_PKG) not installed on $SERIAL" >&2
  echo "Install from https://github.com/ImranR98/Obtainium/releases" >&2
  exit 1
fi

case "$WHICH" in
  all)     JSON="$ROOT/stayturgid-apps.json"; DEST="stayturgid-obtainium-apps.json" ;;
  autojs6) JSON="$ROOT/autojs6-only.json";   DEST="stayturgid-obtainium-autojs6.json" ;;
  *) echo "second arg must be all or autojs6" >&2; exit 1 ;;
esac

REMOTE="/sdcard/Download/$DEST"
echo "Pushing $JSON → $SERIAL:$REMOTE"
adb -s "$SERIAL" push "$JSON" "$REMOTE"

# Open Obtainium import UI with the JSON file (user confirms import on device).
# Fallback: Obtainium → Import/Export → Obtainium Import → pick file in Download/.
adb -s "$SERIAL" shell am start \
  -a android.intent.action.VIEW \
  -d "file://${REMOTE}" \
  -t application/json \
  -n "${OBTAINIUM_PKG}/.MainActivity" 2>/dev/null || \
adb -s "$SERIAL" shell am start \
  -a android.intent.action.VIEW \
  -d "content://com.android.externalstorage.documents/document/primary%3ADownload%2F${DEST}" \
  -t application/json \
  -n "${OBTAINIUM_PKG}/.MainActivity" 2>/dev/null || \
adb -s "$SERIAL" shell monkey -p "$OBTAINIUM_PKG" -c android.intent.category.LAUNCHER 1

echo ""
echo "On device: Obtainium should open — confirm Obtainium Import for $DEST"
echo "If import did not auto-start: Obtainium → Import/Export → Obtainium Import → Download/$DEST"
