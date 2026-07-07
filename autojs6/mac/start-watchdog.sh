#!/usr/bin/env bash
# Launch stayturgid AutoJs6 watchdog (main.js) on a phone.
# Usage: ./start-watchdog.sh <p7a|s24|serial>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: start-watchdog.sh <p7a|s24|serial>}")"
MAIN="/sdcard/stayturgid/autojs6/main.js"
PKG="org.autojs.autojs6"

echo "Starting main.js on $SERIAL..."
adb -s "$SERIAL" shell am start -a android.intent.action.VIEW \
  -d "file://${MAIN}" \
  -t "text/javascript" \
  -n "${PKG}/org.autojs.autojs.external.open.RunIntentActivity"

sleep 3
adb -s "$SERIAL" shell "grep 'autojs6' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -3" || true
echo "Check AutoJs6 → Task tab → Running task should show main.js"
