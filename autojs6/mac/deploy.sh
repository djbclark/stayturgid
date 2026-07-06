#!/usr/bin/env bash
# Deploy the stayturgid AutoJs6 project to a phone over ADB.
# Usage: ./deploy.sh <serial|p7a|s24> [device-id]
#
# Does NOT install AutoJs6 itself — install from GitHub releases / Obtainium first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_BASE="/sdcard/Scripts/stayturgid"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: deploy.sh <serial|p7a|s24> [p7a|s24]}")"
DEVICE_ID="${2:-}"

echo "Deploying autojs6/ → ${SERIAL}:${TARGET_BASE}"

adb -s "$SERIAL" shell "mkdir -p '${TARGET_BASE}/lib' '${TARGET_BASE}/devices' '${TARGET_BASE}/scripts'"

adb -s "$SERIAL" push "$ROOT/project.json" "${TARGET_BASE}/project.json"
adb -s "$SERIAL" push "$ROOT/main.js" "${TARGET_BASE}/main.js"
adb -s "$SERIAL" push "$ROOT/lib/." "${TARGET_BASE}/lib/"
adb -s "$SERIAL" push "$ROOT/devices/." "${TARGET_BASE}/devices/"
adb -s "$SERIAL" push "$ROOT/scripts/." "${TARGET_BASE}/scripts/"

if [[ -n "$DEVICE_ID" ]]; then
  echo "$DEVICE_ID" | adb -s "$SERIAL" shell "cat > /sdcard/stayturgid_device.txt"
  echo "Wrote device override: $DEVICE_ID"
fi

echo "Done. In AutoJs6: open project ${TARGET_BASE} → run main.js"
echo "Then: ./set-automation-mode.sh ${1} && ./start-watchdog.sh ${1}"
