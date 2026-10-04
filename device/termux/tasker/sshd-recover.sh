#!/data/data/com.termux/files/usr/bin/sh
# FROZEN INTERFACE: never rename or move this file. Its path is compiled into
# the native agent APK (SshdRecover.kt) and called by control/bin/firerpa_heal.py
# and recover.d/10-sshd; tests/python/test_tasker_frozen_paths.py pins it.
#
# Fleet sshd recovery entrypoint. Idempotent; safe to fire repeatedly. Exits 0
# only once `sv status sshd` shows it running.
#
# Callable from anything that can execute under Termux's UID without a GUI
# session: the Termux RUN_COMMAND intent (Tasker task / Termux:Tasker plugin
# action — com.termux.permission.RUN_COMMAND holders only), Termux:Widget,
# or any Termux shell. This is the recovery path that still works when a
# permission-change GID-kill has taken down every Termux process and the
# keyguard prevents a Termux GUI session from spawning (observed on t2e and
# p7a, 2026-10-03): Android delivers the intent to RunCommandService in the
# background, no unlock needed.
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export PATH="$PREFIX/bin:$PATH"
export SVDIR="$PREFIX/var/service"
# For the services' svlogd (see boot/00-start-services.sh), not for this script.
export LOGDIR="$PREFIX/var/log"
LOG="$HOME/.stayturgid/logs/sshd-selfheal.log"
LOCK="$HOME/.stayturgid/run/runsvdir-start.lock"
mkdir -p "$HOME/.stayturgid/logs" "$HOME/.stayturgid/run" 2>/dev/null

if [ -r "$HOME/.termux/tasker/recover-lock.sh" ]; then
  # shellcheck source=SCRIPTDIR/recover-lock.sh
  . "$HOME/.termux/tasker/recover-lock.sh"
else
  recover_lock_take() { return 1; }
  recover_lock_release() { :; }
fi

# The check-then-start below is the race that left two supervisors running:
# every caller holds the same lock across it. A holder still busy after 10s
# is wedged, and a rare duplicate supervisor beats no sshd.
if ! recover_lock_take "$LOCK" 60 10; then
  echo "$(date -Iseconds) runsvdir lock unavailable; checking unlocked" >>"$LOG"
fi
# pgrep -f, not -x: a runsvdir started by absolute path shows a truncated path
# as its process name here, so -x misses it and a second supervisor gets
# started (seen on all three phones, 2026-10-04).
if ! pgrep -f "[r]unsvdir $SVDIR" >/dev/null 2>&1; then
  setsid runsvdir "$SVDIR" >/dev/null 2>&1 &
  echo "$(date -Iseconds) runsvdir started by sshd-recover" >>"$LOG"
  # Hold the lock until the new supervisor is visible to the next caller's pgrep.
  n=0
  while [ "$n" -lt 5 ] && ! pgrep -f "[r]unsvdir $SVDIR" >/dev/null 2>&1; do
    sleep 1
    n=$((n + 1))
  done
fi
recover_lock_release "$LOCK"

# `sv up` fails until runsv has created sshd/supervise, so retry it inside the
# bounded wait rather than trusting the first attempt.
st=$(sv status sshd 2>&1)
n=0
while [ "$n" -lt 10 ]; do
  case "$st" in run:*) break ;; esac
  sv up sshd >>"$LOG" 2>&1
  sleep 1
  st=$(sv status sshd 2>&1)
  n=$((n + 1))
done
case "$st" in
  run:*)
    echo "$(date -Iseconds) sshd up ($st)" >>"$LOG"
    exit 0
    ;;
esac
echo "$(date -Iseconds) sshd still not running after recovery ($st)" >>"$LOG"
exit 1
