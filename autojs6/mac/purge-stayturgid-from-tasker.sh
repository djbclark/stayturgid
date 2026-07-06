#!/usr/bin/env bash
# Remove stayturgid files from Tasker storage on a device.
# Does NOT uninstall Tasker, AutoInput, or Termux:Tasker — only deletes stayturgid exports.
#
# Usage: ./purge-stayturgid-from-tasker.sh <p7a|s24|serial>
#
# In-memory Tasker project tabs may still show "stayturgid" until you delete the project
# once in Tasker UI (long-press project tab → Delete → Keep Contents).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: purge-stayturgid-from-tasker.sh <p7a|s24|serial>}")"

echo "Purging stayturgid Tasker artifacts on ${SERIAL}..."

adb -s "$SERIAL" shell 'rm -f \
  /sdcard/Tasker/projects/stayturgid.prj.xml \
  /sdcard/Tasker/Updates/stayturgid_update_check.tsk.xml \
  /sdcard/Tasker/Updates/stayturgid*.tsk.xml \
  /sdcard/Tasker/Updates/ADB_Core_Watchdog.tsk.xml \
  /sdcard/Tasker/Updates/Daily_Update_Check.prf.xml \
  /sdcard/Tasker/Updates/wd_v3.tsk.xml \
  /sdcard/Tasker/Updates/test_trigger.tsk.xml \
  2>/dev/null; echo done'

case "$1" in
  p7a|s24)
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$1" true 2>/dev/null; then
      ssh -o BatchMode=yes "$1" 'rm -f ~/.termux/tasker/stayturgid-repair 2>/dev/null; echo termux tasker wrapper removed'
    fi
    ;;
esac

echo "Done. If Tasker still shows a stayturgid project tab, delete it manually in the Tasker app."
