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

adb -s "$SERIAL" shell "mkdir -p '${TARGET_BASE}/lib' '${TARGET_BASE}/scripts'"

adb -s "$SERIAL" push "$ROOT/project.json" "${TARGET_BASE}/project.json"
adb -s "$SERIAL" push "$ROOT/main.js" "${TARGET_BASE}/main.js"
adb -s "$SERIAL" push "$ROOT/lib/." "${TARGET_BASE}/lib/"
adb -s "$SERIAL" push "$ROOT/scripts/." "${TARGET_BASE}/scripts/"

# The device profile (/sdcard/stayturgid_device.json) is rendered by the
# Ansible fleet deploy from inventory taxonomy — this adb path deploys code
# only; without the JSON the watchdog runs with generic defaults.
if [[ -n "$DEVICE_ID" ]]; then
  echo "NOTE: device-id arg is deprecated; profile comes from Ansible inventory (ignored: $DEVICE_ID)"
fi

echo "Done. In AutoJs6: open project ${TARGET_BASE} → run main.js"
echo "Then: ./set-automation-mode.sh ${1} && ./start-watchdog.sh ${1}"
