#!/usr/bin/env bash
# Deploy the full stayturgid stack to the fleet (Termux, AutoJs6, Obtainium,
# Tailscale, F-Droid/Neo Store, Play/Aurora, optional ensure_apps).
#
# Phases (live deploy only):
#   1. ansible-playbook fleet.yml — core + app-store roles (Neo/Aurora may not be on device yet)
#   2. Obtainium catalog import (Mac adb — unlocked screen)
#   3. ansible-playbook fleet.yml --tags app-stores — on-device repo push + Shizuku grants
#   4. Aurora first-run UI automation (configure_aurora.py)
#
# Usage:
#   ./mac/deploy-fleet.sh             # whole fleet (from inventory)
#   ./mac/deploy-fleet.sh s24         # one host
#   ./mac/deploy-fleet.sh s24 p7a     # explicit list
#
# Dry run: CHECK=1 (maps to ansible --check --diff; skips import + post-steps).
# Partial: ./mac/deploy-fdroid.sh or ./mac/deploy-play.sh (fleet.yml tags).
# adb-only fallback (no SSH): autojs6/mac/deploy.sh + start-watchdog.sh.
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ERROR: ansible-playbook not found (brew install ansible)" >&2
  exit 1
fi

if ! command -v fdroidcl >/dev/null 2>&1; then
  echo "WARNING: fdroidcl not found (brew install fdroidcl) — F-Droid repo sync will fail" >&2
fi
if ! command -v apkeep >/dev/null 2>&1; then
  echo "WARNING: apkeep not found (brew install apkeep) — Aurora auto-install will fail" >&2
fi

ansible-galaxy collection install -r "$ROOT/ansible/requirements.yml" -p "$ROOT/.ansible/collections" >/dev/null

LIMIT=()
if [ "$#" -gt 0 ]; then
  LIMIT=(--limit "$(IFS=,; echo "$*")")
fi
EXTRA=()
[ "${CHECK:-0}" = "1" ] && EXTRA=(--check --diff)

resolve_hosts() {
  HOSTS=("$@")
  if [ "${#HOSTS[@]}" -eq 0 ]; then
    mapfile -t HOSTS < <(
      ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
        ansible-inventory -i "$ROOT/ansible/inventory/hosts.yml" --list \
        | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)["stayturgid"]["hosts"]))'
    )
  fi
}

run_fleet_playbook() {
  local tags="${1:-}"
  cd "$ROOT"
  if [ -n "$tags" ]; then
    ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
      ansible-playbook ansible/playbooks/fleet.yml \
        ${LIMIT[@]+"${LIMIT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"} \
        --tags "$tags"
  else
    ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
      ansible-playbook ansible/playbooks/fleet.yml \
        ${LIMIT[@]+"${LIMIT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"}
  fi
}

resolve_hosts "$@"

rc=0
run_fleet_playbook || rc=$?

if [ "$rc" -eq 0 ] && [ "${CHECK:-0}" != "1" ]; then
  IMPORT="$ROOT/obtainium/mac/import_catalog.py"
  if [ -f "$IMPORT" ]; then
    import_rc=0
    for host in "${HOSTS[@]}"; do
      echo ""
      echo "=== Obtainium catalog import: $host ==="
      if ! python3 "$IMPORT" "$host" all; then
        import_rc=1
        echo "WARN: Obtainium import failed on $host (fleet deploy otherwise ok)" >&2
      fi
    done
    [ "$import_rc" -ne 0 ] && rc=1
  fi

  if [ "$rc" -eq 0 ]; then
    echo ""
    echo "=== App stores (F-Droid + Play) post-import ==="
    run_fleet_playbook app-stores || rc=$?
  fi

  if [ "$rc" -eq 0 ]; then
    CONFIGURE="$ROOT/play/mac/configure_aurora.py"
    if [ -f "$CONFIGURE" ]; then
      for host in "${HOSTS[@]}"; do
        echo ""
        echo "=== Aurora first-run setup: $host ==="
        if ! "$CONFIGURE" "$host"; then
          echo "Retrying Aurora configuration on $host..."
          sleep 3
          "$CONFIGURE" "$host" || rc=1
        fi
      done
    fi
  fi
fi

echo ""
if [ "$rc" -ne 0 ]; then
  echo "Fleet deploy finished with errors (exit $rc). Failed hosts are listed above." >&2
else
  echo "Fleet deploy complete."
fi
echo "Verify: make verify   (or ./mac/fleet-health.sh)"
exit "$rc"
