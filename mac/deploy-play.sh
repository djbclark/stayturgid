#!/usr/bin/env bash
# Deploy Aurora Store Shizuku grant (play_store side project).
# Does not run as part of ./mac/deploy-fleet.sh.
#
# Usage:
#   ./mac/deploy-play.sh           # whole fleet
#   ./mac/deploy-play.sh p7a       # one host
#   CHECK=1 ./mac/deploy-play.sh   # dry run
#
# Installs Aurora Store if missing, grants Shizuku, and completes first-run setup.
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AURORA_PKG="com.aurora.store"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ERROR: ansible-playbook not found (brew install ansible)" >&2
  exit 1
fi
if ! command -v apkeep >/dev/null 2>&1; then
  echo "WARNING: apkeep not found (brew install apkeep) — Aurora/Play app downloads will fail" >&2
  echo "         Shizuku grant still runs; use apk_path or GPLAY_* creds for google-play." >&2
fi

LIMIT=()
if [ "$#" -gt 0 ]; then
  LIMIT=(--limit "$(IFS=,; echo "$*")")
fi
EXTRA=()
[ "${CHECK:-0}" = "1" ] && EXTRA=(--check --diff)

cd "$ROOT"

HOSTS=("$@")
if [ "${#HOSTS[@]}" -eq 0 ]; then
  mapfile -t HOSTS < <(
    ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
      ansible-inventory -i "$ROOT/ansible/inventory/hosts.yml" --list \
      | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)["stayturgid"]["hosts"]))'
  )
fi

if [ "${CHECK:-0}" != "1" ] && command -v apkeep >/dev/null 2>&1; then
  # shellcheck source=../shared/mac/resolve-adb.sh
  source "$ROOT/shared/mac/resolve-adb.sh"
  TMP_APK_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_APK_DIR"' EXIT
  AURORA_APK="$TMP_APK_DIR/$AURORA_PKG.apk"

  aurora_installed() {
    local serial="$1"
    adb -s "$serial" shell pm path "$AURORA_PKG" 2>/dev/null | grep -q .
  }

  for host in "${HOSTS[@]}"; do
    serial="$(resolve_adb "$host")"
    adb connect "$serial" >/dev/null 2>&1 || true
    adb -s "$serial" wait-for-device
    if aurora_installed "$serial" || { sleep 2; aurora_installed "$serial"; }; then
      echo "Aurora Store already installed on $host ($serial)."
      continue
    fi
    if [ ! -f "$AURORA_APK" ]; then
      echo "Downloading Aurora Store via apkeep..."
      apkeep -a "$AURORA_PKG" -d f-droid "$TMP_APK_DIR"
    fi
    echo "Installing Aurora Store on $host ($serial)..."
    if ! adb -s "$serial" install -r "$AURORA_APK"; then
      if aurora_installed "$serial"; then
        echo "Aurora Store is already present on $host; continuing after install retry failed."
      else
        echo "ERROR: failed to install Aurora Store on $host ($serial)" >&2
        exit 1
      fi
    fi
  done
fi

ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  ansible-playbook ansible/playbooks/play_store.yml ${LIMIT[@]+"${LIMIT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"}

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
