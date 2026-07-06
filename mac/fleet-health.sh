#!/usr/bin/env bash
# Quick health check for stayturgid fleet (SSH + optional ADB).
#
# Usage:
#   ./mac/fleet-health.sh           # s24 p7a
#   ./mac/fleet-health.sh s24
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../shared/mac/resolve-adb.sh
source "$ROOT/shared/mac/resolve-adb.sh"

if [ "$#" -eq 0 ]; then
  HOSTS=(s24 p7a)
else
  HOSTS=("$@")
fi

FAIL=0

check_host() {
  local host="$1"
  echo ""
  echo "=== $host ==="

  if ! ssh -o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR "$host" 'bash -s' <<'REMOTE'
export PATH=/data/data/com.termux/files/usr/bin:$PATH
set -e
echo -n "sshd: "; pgrep sshd >/dev/null && echo ok || echo MISSING
echo -n "boot loop: "; pgrep -f 'start-adb\.sh' >/dev/null && echo ok || echo MISSING
echo -n "battery alarm: "; [ -x ~/stayturgid-battery-alarm.sh ] && grep -q 'tier_blinks' ~/stayturgid-battery-alarm.sh && echo ok || echo STALE
echo -n "repair: "; ~/stayturgid-repair.sh 2>/dev/null | tail -1
batt=$(termux-battery-status 2>/dev/null || true)
if [ -n "$batt" ]; then
  pct=$(echo "$batt" | grep -o '"percentage": *[0-9]*' | grep -o '[0-9]*')
  status=$(echo "$batt" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4)
  echo "battery: ${pct}% status=${status}"
else
  echo "battery: termux-api unavailable"
fi
REMOTE
  then
    echo "SSH check FAILED"
    FAIL=1
    return
  fi

  if serial="$(resolve_adb "$host" 2>/dev/null)"; then
    # Tailscale ip:port serials need an explicit connect first.
    case "$serial" in
      *:*) adb connect "$serial" >/dev/null 2>&1 || true ;;
    esac
    echo -n "adb: $serial "
    local wd_line
    wd_line="$(adb -s "$serial" shell 'grep autojs6 /sdcard/stayturgid_watchdog.log 2>/dev/null | tail -1' 2>/dev/null || true)"
    if [ -n "$wd_line" ]; then
      echo "$wd_line"
    elif adb -s "$serial" shell true >/dev/null 2>&1; then
      echo "(connected; no autojs6 watchdog log lines)"
    else
      echo "(adb not connected)"
    fi
  else
    echo "adb: unreachable (SSH-only check ran)"
  fi
}

for host in "${HOSTS[@]}"; do
  check_host "$host" || true
done

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "fleet-health: all SSH checks passed"
else
  echo "fleet-health: one or more hosts failed"
  exit 1
fi
