#!/usr/bin/env bash
# Deploy the full stayturgid stack (Termux + AutoJs6) to the fleet.
# Thin wrapper around ansible/playbooks/fleet.yml — Ansible owns idempotent
# copies, per-host failure isolation, and the boot-loop restart handler.
#
# Usage:
#   ./mac/deploy-fleet.sh             # whole fleet (from inventory)
#   ./mac/deploy-fleet.sh s24         # one host
#   ./mac/deploy-fleet.sh s24 p7a     # explicit list
#
# Dry run: add CHECK=1 (maps to ansible --check --diff).
# adb-only fallback (no SSH): autojs6/mac/deploy.sh + start-watchdog.sh.
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ERROR: ansible-playbook not found (brew install ansible)" >&2
  exit 1
fi

ansible-galaxy collection install -r "$ROOT/ansible/requirements.yml" -p "$ROOT/.ansible/collections" >/dev/null

LIMIT=()
if [ "$#" -gt 0 ]; then
  LIMIT=(--limit "$(IFS=,; echo "$*")")
fi
EXTRA=()
[ "${CHECK:-0}" = "1" ] && EXTRA=(--check --diff)

cd "$ROOT"
rc=0
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  ansible-playbook ansible/playbooks/fleet.yml ${LIMIT[@]+"${LIMIT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"} \
  || rc=$?

# After Ansible renders the on-device catalog, apply it in Obtainium via Mac adb.
if [ "$rc" -eq 0 ] && [ "${CHECK:-0}" != "1" ]; then
  IMPORT="$ROOT/obtainium/mac/import_catalog.py"
  if [ -f "$IMPORT" ]; then
    HOSTS=("$@")
    if [ "${#HOSTS[@]}" -eq 0 ]; then
      mapfile -t HOSTS < <(
        ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
          ansible-inventory -i "$ROOT/ansible/inventory/hosts.yml" --list \
          | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)["stayturgid"]["hosts"]))'
      )
    fi
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
fi

echo ""
if [ "$rc" -ne 0 ]; then
  echo "Fleet deploy finished with errors (exit $rc). Failed hosts are listed above." >&2
else
  echo "Fleet deploy complete."
fi
echo "Verify: make verify   (or ./mac/fleet-health.sh)"
exit "$rc"
