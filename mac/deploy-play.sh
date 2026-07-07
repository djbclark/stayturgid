#!/usr/bin/env bash
# Deploy Aurora Store Shizuku grant (play_store side project).
# Does not run as part of ./mac/deploy-fleet.sh.
#
# Usage:
#   ./mac/deploy-play.sh           # whole fleet
#   ./mac/deploy-play.sh p7a       # one host
#   CHECK=1 ./mac/deploy-play.sh   # dry run
#
# Prerequisite: Aurora Store on device (Obtainium catalog).
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ERROR: ansible-playbook not found (brew install ansible)" >&2
  exit 1
fi
if ! command -v apkeep >/dev/null 2>&1; then
  echo "WARNING: apkeep not found (brew install apkeep) — Play app downloads will fail" >&2
  echo "         Shizuku grant still runs; use apk_path or GPLAY_* creds for google-play." >&2
fi

LIMIT=()
if [ "$#" -gt 0 ]; then
  LIMIT=(--limit "$(IFS=,; echo "$*")")
fi
EXTRA=()
[ "${CHECK:-0}" = "1" ] && EXTRA=(--check --diff)

cd "$ROOT"
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  ansible-playbook ansible/playbooks/play_store.yml ${LIMIT[@]+"${LIMIT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"}

echo ""
echo "Play deploy complete. Enable Shizuku installer + auto-updates in Aurora settings."
