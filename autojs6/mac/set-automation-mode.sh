#!/usr/bin/env bash
# Write stayturgid automation marker and sync Shizuku grants for AutoJs6.
# Usage: ./set-automation-mode.sh <serial|p7a|s24>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: set-automation-mode.sh <serial|p7a|s24>}")"

echo "autojs6" | adb -s "$SERIAL" shell "cat > /sdcard/stayturgid_automation_mode.txt"
echo "Wrote automation mode autojs6 on ${SERIAL}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -x "$SCRIPT_DIR/grant_shizuku.py" ]]; then
  echo "Syncing Shizuku authorized apps for AutoJs6..."
  "$SCRIPT_DIR/grant_shizuku.py" "$1" || echo "WARN: Shizuku grant sync failed (is Shizuku up?)" >&2
fi

cat <<'EOF'

Next steps on device:
  1. Enable AutoJs6 accessibility service
  2. In AutoJs6: open /sdcard/Scripts/stayturgid → run main.js
  3. Optional: AutoJs6 timed task every 20 min + run on boot for main.js

EOF
