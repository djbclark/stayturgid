#!/usr/bin/env bash
# Re-run Play / Aurora Store roles from the fleet playbook (play tag) + UI setup.
# Full stack: ./mac/deploy-fleet.sh (includes this after Obtainium import).
#
# Usage:
#   ./mac/deploy-play.sh           # whole fleet
#   ./mac/deploy-play.sh s24       # one host
#   CHECK=1 ./mac/deploy-play.sh   # dry run
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ERROR: ansible-playbook not found (brew install ansible)" >&2
  exit 1
fi
if ! command -v apkeep >/dev/null 2>&1; then
  echo "WARNING: apkeep not found (brew install apkeep) — set stayturgid_install_aurora_store or install Aurora manually" >&2
fi

LIMIT=()
if [ "$#" -gt 0 ]; then
  LIMIT=(--limit "$(IFS=,; echo "$*")")
fi
EXTRA=()
[ "${CHECK:-0}" = "1" ] && EXTRA=(--check --diff)

HOSTS=("$@")
if [ "${#HOSTS[@]}" -eq 0 ]; then
  mapfile -t HOSTS < <(
    ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
      ansible-inventory -i "$ROOT/ansible/inventory/hosts.yml" --list \
      | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)["stayturgid"]["hosts"]))'
  )
fi

cd "$ROOT"
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  ansible-playbook ansible/playbooks/fleet.yml --tags play \
    ${LIMIT[@]+"${LIMIT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"}

if [ "${CHECK:-0}" != "1" ]; then
  for host in "${HOSTS[@]}"; do
    if ! "$ROOT/play/mac/configure_aurora.py" "$host"; then
      echo "Retrying Aurora configuration on $host..."
      sleep 3
      "$ROOT/play/mac/configure_aurora.py" "$host"
    fi
  done
fi

echo ""
echo "Play deploy complete. Aurora Store is installed, granted Shizuku, using Shizuku installer, and set for automatic installs."
