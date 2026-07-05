#!/usr/bin/env bash
# Set stayturgid automation mode on a device (tasker | autojs6).
# Usage: ./set-automation-mode.sh <serial|p7a|s24> <tasker|autojs6>
set -euo pipefail

# shellcheck source=../../mac/resolve-adb.sh
source "$(cd "$(dirname "$0")/../.." && pwd)/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: set-automation-mode.sh <serial|p7a|s24> <tasker|autojs6>}")"
MODE="${2:?usage: set-automation-mode.sh <serial|p7a|s24> <tasker|autojs6>}"

case "$MODE" in
  tasker|autojs6) ;;
  *) echo "mode must be tasker or autojs6" >&2; exit 1 ;;
esac

echo "$MODE" | adb -s "$SERIAL" shell "cat > /sdcard/stayturgid_automation_mode.txt"
echo "Wrote automation mode '${MODE}' on ${SERIAL}"

if [[ "$MODE" == "autojs6" ]]; then
  cat <<'EOF'

Next steps on device:
  1. Stop stayturgid Tasker profiles (ADB_Boot_Restore, ADB_Interval_Check)
  2. Disable Tasker + AutoInput accessibility services
  3. Enable AutoJs6 accessibility service
  4. In AutoJs6: open /sdcard/Scripts/stayturgid → run main.js
  5. Optional: AutoJs6 → Timed task every 20 min + run on boot for main.js

EOF
else
  cat <<'EOF'

Next steps on device:
  1. Stop the stayturgid AutoJs6 main.js script
  2. Disable AutoJs6 accessibility service
  3. Re-enable Tasker + AutoInput accessibility
  4. Re-enable stayturgid Tasker profiles

EOF
fi
