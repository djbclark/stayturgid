#!/usr/bin/env bash
# Push stayturgid Obtainium configs to a phone and import via deep link.
# Usage:
#   ./sync-to-device.sh <s24|p7a|hd8|serial> [all|autojs6] [--no-import]
#
# Re-importing merges/updates existing entries (does not remove other apps).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OBTAINIUM_PKG="dev.imranr.obtainium"
IMPORT_SCRIPT="$(cd "$(dirname "$0")" && pwd)/import_catalog.py"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: sync-to-device.sh <p7a|s24|serial> [all|autojs6] [--no-import]}")"
WHICH="${2:-all}"
NO_IMPORT=false
for arg in "$@"; do
  [[ "$arg" == "--no-import" ]] && NO_IMPORT=true
done
[[ "${2:-}" == "--no-import" ]] && WHICH="all"
[[ "${3:-}" == "--no-import" ]] && NO_IMPORT=true

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

if [[ "$NO_IMPORT" == true ]]; then
  echo "Skipped import (--no-import). JSON at Download/$DEST"
  exit 0
fi

if [[ ! -f "$IMPORT_SCRIPT" ]]; then
  echo "WARN: $IMPORT_SCRIPT missing — JSON pushed only." >&2
  exit 0
fi

echo "Importing catalog into Obtainium on $SERIAL..."
python3 "$IMPORT_SCRIPT" "$SERIAL" "$WHICH"
