#!/usr/bin/env bash
# Open Obtainium on a phone and drive the bulk "Install/update apps" flow.
# Usage: ./apply-updates.sh <p7a|s24|serial>
#
# Requires: unlocked screen, Obtainium in foreground. Confirms package-installer
# dialogs (taps android:id/button2 — observed as the positive action on Samsung
# One UI; unverified on Pixel, where button1 may be the positive action).
#
# For stayturgid catalog apps blocked by Play Protect, prefer adb install with
# verifier disabled (see HACKING.md) or enable Shizuku installer in Obtainium settings.
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: apply-updates.sh <p7a|s24|serial>}")"
OBTAINIUM_PKG="dev.imranr.obtainium"
BULK_X=476
BULK_Y=2017
CONTINUE_X=727
CONTINUE_Y=1433

adb -s "$SERIAL" shell am start -n "${OBTAINIUM_PKG}/.MainActivity"
sleep 3
adb -s "$SERIAL" shell input tap "$BULK_X" "$BULK_Y"
sleep 2
adb -s "$SERIAL" shell input tap "$CONTINUE_X" "$CONTINUE_Y"
echo "Tapped bulk update + Continue — handling installer dialogs for ~90s..."

for _ in $(seq 1 18); do
  sleep 5
  adb -s "$SERIAL" shell uiautomator dump /sdcard/obtainium_apply.xml 2>/dev/null || true
  XML="$(adb -s "$SERIAL" shell cat /sdcard/obtainium_apply.xml 2>/dev/null || true)"
  if echo "$XML" | grep -q 'package="com.google.android.packageinstaller"'; then
    B=$(echo "$XML" | tr '>' '\n' | grep 'resource-id="android:id/button2"' | head -1 \
      | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p')
    read -r x1 y1 x2 y2 <<< "$B"
    if [[ -n "$x1" ]]; then
      adb -s "$SERIAL" shell input tap $(( (x1+x2)/2 )) $(( (y1+y2)/2 ))
      echo "  confirmed package installer (button2)"
    fi
  fi
  if echo "$XML" | grep -q 'package="com.android.vending"'; then
    echo "  WARN: Play Protect dialog — dismiss manually or disable verifier (HACKING.md)"
    adb -s "$SERIAL" shell input tap 540 1629
  fi
done
echo "Done. Re-check Obtainium app list for any remaining Update badges."
