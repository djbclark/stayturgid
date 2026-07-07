#!/usr/bin/env bash
# Deploy F-Droid repo config (fdroidcl + Neo Store intents + Shizuku grant).
# Side project — does not run as part of ./mac/deploy-fleet.sh.
#
# Usage:
#   ./mac/deploy-fdroid.sh           # whole fleet
#   ./mac/deploy-fdroid.sh s24       # one host
#   CHECK=1 ./mac/deploy-fdroid.sh   # dry run
#
# Prerequisite: Neo Store on device (Obtainium catalog). Mac: brew install fdroidcl
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ERROR: ansible-playbook not found (brew install ansible)" >&2
  exit 1
fi
if ! command -v fdroidcl >/dev/null 2>&1; then
  echo "ERROR: fdroidcl not found (brew install fdroidcl)" >&2
  exit 1
fi

LIMIT=()
if [ "$#" -gt 0 ]; then
  LIMIT=(--limit "$(IFS=,; echo "$*")")
fi
EXTRA=()
[ "${CHECK:-0}" = "1" ] && EXTRA=(--check --diff)

cd "$ROOT"
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  ansible-playbook ansible/playbooks/fdroid.yml ${LIMIT[@]+"${LIMIT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"}

echo ""
echo "Fdroid deploy complete. Install an app: ANDROID_SERIAL=<target> fdroidcl install <appid>"
