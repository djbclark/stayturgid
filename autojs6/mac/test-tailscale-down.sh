#!/usr/bin/env bash
# Live Tailscale-down test on S24 — use USB serial (Tailscale SSH may blip).
# Usage: ./test-tailscale-down.sh [s24|RFCX219CHKA]
#
# 1. Mac: force-stop Tailscale + wait for coord ping to fail
# 2. AutoJs6: probe, run watchdog cycle (notify + relaunch path), wait for recovery
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

ALIAS="${1:-s24}"
if adb devices 2>/dev/null | grep -qF $'RFCX219CHKA\tdevice'; then
  SERIAL="RFCX219CHKA"
else
  SERIAL="$(resolve_adb "$ALIAS")"
fi

PKG="org.autojs.autojs6"
SCRIPT="/sdcard/stayturgid/autojs6/scripts/test-tailscale-down-once.js"
TS_PKG="com.tailscale.ipn"

echo "=== Phase 1: baseline (USB $SERIAL) ==="
adb -s "$SERIAL" shell input keyevent KEYCODE_WAKEUP 2>/dev/null || true
adb -s "$SERIAL" shell "ping -c1 -W2 100.100.100.100 >/dev/null && echo baseline_ping=ok || echo baseline_ping=fail"

echo "=== Phase 2: force-stop Tailscale + wait for tunnel blip ==="
adb -s "$SERIAL" shell "am force-stop $TS_PKG"
for i in $(seq 1 15); do
  sleep 1
  if ! adb -s "$SERIAL" shell "ping -c1 -W2 100.100.100.100" >/dev/null 2>&1; then
    echo "coord ping failed after ${i}s"
    break
  fi
done

echo "=== Phase 3: AutoJs6 probe + watchdog + relaunch ==="
adb -s "$SERIAL" shell am start -a android.intent.action.VIEW \
  -d "file://${SCRIPT}" \
  -t "text/javascript" \
  -n "${PKG}/org.autojs.autojs.external.open.RunIntentActivity"

echo "Waiting up to 60s for recovery..."
for _ in $(seq 1 12); do
  sleep 5
  if adb -s "$SERIAL" shell "grep tailscale-down-test /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1" \
      | grep -q "after-relaunch"; then
    break
  fi
done

echo "--- tailscale-down-test log lines ---"
adb -s "$SERIAL" shell "grep -E 'tailscale-down-test|tailscale tun=' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -10"

PROBE_DOWN="$(adb -s "$SERIAL" shell "grep 'tailscale-down-test probe' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1" || true)"
RECOVERED="$(adb -s "$SERIAL" shell "grep 'after-relaunch' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1" || true)"

if echo "$PROBE_DOWN" | grep -q "up=false"; then
  echo "PASS: probe detected Tailscale down"
else
  echo "WARN: probe did not report up=false — $PROBE_DOWN" >&2
fi

if echo "$RECOVERED" | grep -qE 'after-relaunch.*up=true'; then
  echo "PASS: Tailscale recovered after relaunch"
  exit 0
fi

echo "FAIL: recovery not confirmed — $RECOVERED" >&2
exit 1
