#!/usr/bin/env bash
# Install AutoJs6, grant Termux bridge perms, deploy project, start repair-bridge.
# Usage: ./setup-autojs6.sh <serial|p7a|s24> [device-id]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DL_DIR="${TMPDIR:-/tmp}/stayturgid-autojs6"
APK_NAME="autojs6-v6.7.0-arm64-v8a-62db1ff8.apk"
AUTOJS_PKG="org.autojs.autojs6"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: setup-autojs6.sh <serial|p7a|s24> [p7a|s24]}")"
DEVICE_ID="${2:-}"

echo "=== stayturgid AutoJs6 setup on ${SERIAL} ==="

# 1. Download APK if needed
mkdir -p "$DL_DIR"
if [[ ! -f "$DL_DIR/$APK_NAME" ]]; then
  echo "Downloading AutoJs6 v6.7.0..."
  gh release download v6.7.0 --repo SuperMonster003/AutoJs6 -p "$APK_NAME" -D "$DL_DIR"
fi

# 2. Install AutoJs6
if adb -s "$SERIAL" shell pm path "$AUTOJS_PKG" 2>/dev/null | grep -q .; then
  echo "AutoJs6 already installed"
else
  echo "Installing AutoJs6..."
  adb -s "$SERIAL" install -r "$DL_DIR/$APK_NAME"
fi

# 3. Grant Termux RUN_COMMAND (fails harmlessly if manifest lacks permission)
echo "Granting Termux RUN_COMMAND to AutoJs6..."
if adb -s "$SERIAL" shell pm grant "$AUTOJS_PKG" com.termux.permission.RUN_COMMAND 2>&1; then
  echo "RUN_COMMAND granted"
else
  echo "WARN: RUN_COMMAND grant failed — use repair-bridge.sh fallback (deployed below)"
fi

# 4. Battery whitelist AutoJs6
adb -s "$SERIAL" shell dumpsys deviceidle whitelist +"$AUTOJS_PKG" 2>/dev/null || true

# 4b. Storage access — without this AutoJs6 toasts 'No "storage r/w" permission'
# and silently refuses to run /sdcard/Scripts/stayturgid/main.js.
adb -s "$SERIAL" shell appops set "$AUTOJS_PKG" MANAGE_EXTERNAL_STORAGE allow 2>/dev/null || true
adb -s "$SERIAL" shell pm grant "$AUTOJS_PKG" android.permission.READ_EXTERNAL_STORAGE 2>/dev/null || true
adb -s "$SERIAL" shell pm grant "$AUTOJS_PKG" android.permission.WRITE_EXTERNAL_STORAGE 2>/dev/null || true

# 5. Deploy stayturgid repair + bridge to Termux via SSH alias when possible
case "$1" in
  p7a) SSH_HOST=p7a ;;
  s24) SSH_HOST=s24 ;;
  *)   SSH_HOST="" ;;
esac

if [[ -n "$SSH_HOST" ]] && ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_HOST" true 2>/dev/null; then
  echo "Deploying Termux scripts via SSH ($SSH_HOST)..."
  scp -q "$ROOT/../termux/stayturgid-repair.sh" "$SSH_HOST:~/stayturgid-repair.sh" 2>/dev/null || \
    scp -q "$ROOT/../termux/stayturgid-repair.sh" "$SSH_HOST:stayturgid-repair.sh"
scp -q "$ROOT/../termux/repair-bridge.sh" "$SSH_HOST:~/repair-bridge.sh"
  scp -q "$ROOT/../termux/boot/start-repair-bridge.sh" "$SSH_HOST:~/.termux/boot/start-repair-bridge.sh" 2>/dev/null || true
  scp -q "$ROOT/../termux/boot/start-autojs6-watchdog.sh" "$SSH_HOST:~/.termux/boot/start-autojs6-watchdog.sh" 2>/dev/null || true
  ssh "$SSH_HOST" 'chmod +x ~/stayturgid-repair.sh ~/repair-bridge.sh ~/.termux/boot/start-repair-bridge.sh ~/.termux/boot/start-autojs6-watchdog.sh 2>/dev/null; pgrep -f repair-bridge.sh >/dev/null || nohup ~/repair-bridge.sh >> ~/.repair-bridge.log 2>&1 &'
  echo "repair-bridge.sh started (or already running)"
else
  echo "SSH unavailable — push repair-bridge via adb to /sdcard for manual Termux deploy"
  adb -s "$SERIAL" push "$ROOT/../termux/repair-bridge.sh" /sdcard/Download/repair-bridge.sh
fi

# 6. Deploy AutoJs6 project
"$SCRIPT_DIR/deploy.sh" "$1" "$DEVICE_ID"

# 7. Mark device for AutoJs6 stack (legacy marker file; optional)
adb -s "$SERIAL" shell "echo autojs6 > /sdcard/stayturgid_automation_mode.txt"

# 8. Register AutoJs6 in Obtainium for GitHub release updates
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -x "$SCRIPT_DIR/../../obtainium/mac/sync-to-device.sh" ]]; then
  echo "Registering AutoJs6 in Obtainium..."
  "$SCRIPT_DIR/../../obtainium/mac/sync-to-device.sh" "$1" autojs6 || true
fi

cat <<EOF

=== Setup complete ===

On device:
  1. Open AutoJs6 → enable Accessibility service
  2. Settings → Apps → AutoJs6 → Permissions → Additional →
     "Run commands in Termux environment" (if shown)
  3. ./set-automation-mode.sh $1
  4. ./start-watchdog.sh $1   # or run main.js in AutoJs6

Logs:
  adb -s $SERIAL shell tail -f /sdcard/stayturgid_watchdog.log
  ssh $SSH_HOST 'tail -f ~/.repair-bridge.log'  # if SSH worked

EOF
