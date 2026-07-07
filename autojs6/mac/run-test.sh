#!/usr/bin/env bash
# Run a single AutoJs6 test script on a phone.
# Usage: ./run-test.sh <p7a|s24|serial> <script.js>
#
# Examples:
#   ./run-test.sh s24 test-watchdog-once.js
#   ./run-test.sh s24 test-tailscale-probe-once.js
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: run-test.sh <p7a|s24|serial> <script.js>}")"
SCRIPT="${2:?usage: run-test.sh <p7a|s24|serial> <script.js>}"
PKG="org.autojs.autojs6"
BASE="/sdcard/stayturgid/autojs6/scripts"

echo "Running $SCRIPT on $SERIAL..."
adb -s "$SERIAL" shell am start -a android.intent.action.VIEW \
  -d "file://${BASE}/${SCRIPT}" \
  -t "text/javascript" \
  -n "${PKG}/org.autojs.autojs.external.open.RunIntentActivity"
sleep 3
echo "Tail of watchdog log:"
adb -s "$SERIAL" shell "tail -8 /sdcard/stayturgid/logs/watchdog.log 2>/dev/null" || true
