#!/data/data/com.termux/files/usr/bin/sh
# FROZEN INTERFACE: never rename or move this file. The Tasker project
# (device/tasker/StayTurgid_SSHD_Recover.prj.xml) was imported by hand on every
# phone and its RUN_COMMAND_PATH names this exact path. Deploys never delete,
# so a renamed copy would leave old phones running this stale file and new
# phones failing; tests/python/test_tasker_frozen_paths.py pins the name.
#
# Dispatcher for the keyguard-proof recovery path. Tasker's SSHD_RECOVER
# profile is the only caller, so the marker's line 1 (a bare epoch: the Mac's
# fleet_health parser reads line 1 only and calls anything else "missing")
# proves the Tasker path reached Termux. The .result file then says whether
# the recoveries worked. New recoveries are new executables in recover.d/,
# never new Tasker profiles: Tasker cannot be changed without a human.
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export PATH="$PREFIX/bin:$PATH"
export SVDIR="$PREFIX/var/service"
STATE="$HOME/.stayturgid/state"
mkdir -p "$STATE" 2>/dev/null
date +%s >"$STATE/tasker-sshd-recover.ts"

TASKER_DIR="$HOME/.termux/tasker"
RESULT="$STATE/tasker-sshd-recover.result"
LAST_RUN="$STATE/tasker-sshd-recover.last-run"
LOCK="$HOME/.stayturgid/run/tasker-sshd-recover.lock"
LOG="$HOME/.stayturgid/logs/tasker-recover.log"
# Any app can send the broadcast, and the agent, firerpa_heal and the Mac can
# all fire a recovery within seconds of each other.
MIN_INTERVAL_SEC="${STAYTURGID_RECOVER_MIN_INTERVAL_SEC:-30}"
STEP_TIMEOUT_SEC="${STAYTURGID_RECOVER_STEP_TIMEOUT_SEC:-60}"
# Must outlast a full run (every step at its timeout) or a slow run loses its lock.
LOCK_STALE_SEC=900
mkdir -p "$HOME/.stayturgid/run" "$HOME/.stayturgid/logs" 2>/dev/null

log() { echo "$(date -Iseconds) $*" >>"$LOG"; }

if [ -r "$TASKER_DIR/recover-lock.sh" ]; then
  # shellcheck source=SCRIPTDIR/recover-lock.sh
  . "$TASKER_DIR/recover-lock.sh"
else
  # Recovering unlocked beats not recovering.
  log "recover-lock.sh missing; running unlocked"
  recover_lock_take() { :; }
  # The EXIT trap calls it.
  # shellcheck disable=SC2329
  recover_lock_release() { :; }
fi

if ! recover_lock_take "$LOCK" "$LOCK_STALE_SEC"; then
  log "skipped: another run holds $LOCK"
  exit 0
fi
trap 'recover_lock_release "$LOCK"' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

lines=$(wc -l <"$LOG" 2>/dev/null)
if [ "${lines:-0}" -gt 2000 ]; then
  tail -n 1000 "$LOG" >"$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"
fi

now=$(date +%s)
last=$(cat "$LAST_RUN" 2>/dev/null)
case "$last" in "" | *[!0-9]*) last=0 ;; esac
if [ $((now - last)) -lt "$MIN_INTERVAL_SEC" ]; then
  log "skipped: last run $((now - last))s ago (min ${MIN_INTERVAL_SEC}s)"
  exit 0
fi
echo "$now" >"$LAST_RUN"

# Boot takes this wake lock (start_adb.py); after a GID-kill nothing else
# restores it, and without it Android may freeze or kill the restarted sshd.
if command -v termux-wake-lock >/dev/null 2>&1; then
  timeout 5 termux-wake-lock >/dev/null 2>&1 || log "termux-wake-lock rc=$?"
fi

overall=0
steps=""
for f in "$TASKER_DIR/recover.d"/*; do
  [ -f "$f" ] && [ -x "$f" ] || continue
  name=${f##*/}
  timeout "$STEP_TIMEOUT_SEC" "$f" </dev/null >>"$LOG" 2>&1
  rc=$?
  [ "$rc" = 0 ] || overall=1
  steps="${steps}step.$name=$rc
"
  log "recover.d/$name rc=$rc"
done
if [ -z "$steps" ]; then
  # A deploy that lost recover.d must read as a failure, not a quiet success.
  overall=1
  log "no executable recover.d steps in $TASKER_DIR/recover.d"
fi

# tty tells the Mac whether Termux honoured RUN_COMMAND_BACKGROUND: a
# foreground run gets a pty (and opened a session over the lock screen).
{
  echo "end=$(date +%s)"
  echo "exit=$overall"
  printf '%s' "$steps"
  echo "sv_sshd=$(sv status sshd 2>&1 | head -n 1)"
  echo "tty=$(tty 2>&1)"
} >"$RESULT.tmp" && mv -f "$RESULT.tmp" "$RESULT"
log "done exit=$overall"
exit "$overall"
