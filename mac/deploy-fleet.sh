#!/usr/bin/env bash
# Deploy the full stayturgid stack (Termux + AutoJs6) to one or more phones.
#
# Usage:
#   ./mac/deploy-fleet.sh           # s24 and p7a
#   ./mac/deploy-fleet.sh s24         # one host
#   ./mac/deploy-fleet.sh s24 p7a     # explicit list
#
# Requires: SSH to Termux, adb (USB or Tailscale), ansible-playbook.
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$#" -eq 0 ]; then
  HOSTS=(s24 p7a)
else
  HOSTS=("$@")
fi

restart_boot_loop() {
  local host="$1"
  echo "Restarting Termux boot loop on $host..."
  ssh -o BatchMode=yes -o ConnectTimeout=15 "$host" 'bash -s' <<'REMOTE'
export PATH=/data/data/com.termux/files/usr/bin:$PATH
pkill -f '\.termux/boot/start-adb\.sh' 2>/dev/null || true
sleep 2
nohup "$HOME/.termux/boot/start-adb.sh" >/dev/null 2>&1 &
sleep 1
pgrep -f 'start-adb\.sh' >/dev/null && echo "boot loop running" || echo "WARN: boot loop may not have started"
REMOTE
}

# Explicit || on every step: when called in an `if !` condition, set -e is
# suspended inside the function, so unchecked failures would be swallowed.
deploy_host() {
  local host="$1" rc=0
  echo ""
  echo "========== $host =========="
  echo "--- Termux (Ansible) ---"
  "$ROOT/ansible/mac/deploy-termux.sh" "$host" || rc=1
  restart_boot_loop "$host" || rc=1
  echo "--- AutoJs6 ---"
  "$ROOT/autojs6/mac/deploy.sh" "$host" || rc=1
  "$ROOT/autojs6/mac/start-watchdog.sh" "$host" || rc=1
  return "$rc"
}

FAIL=0
for host in "${HOSTS[@]}"; do
  # One unreachable phone shouldn't skip the rest of the fleet.
  if ! deploy_host "$host"; then
    echo "ERROR: deploy failed for $host — continuing with remaining hosts" >&2
    FAIL=1
  fi
done

echo ""
if [ "$FAIL" -ne 0 ]; then
  echo "Fleet deploy finished WITH FAILURES. Run ./mac/fleet-health.sh to verify."
  exit 1
fi
echo "Fleet deploy complete. Run ./mac/fleet-health.sh to verify."
