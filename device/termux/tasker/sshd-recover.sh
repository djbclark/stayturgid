#!/data/data/com.termux/files/usr/bin/sh
# Fleet sshd recovery entrypoint. Idempotent; safe to fire repeatedly.
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
LOGDIR="$HOME/.stayturgid/logs"
LOG="$LOGDIR/sshd-selfheal.log"
mkdir -p "$LOGDIR" 2>/dev/null

if ! pgrep -x runsvdir >/dev/null 2>&1; then
  setsid runsvdir "$SVDIR" >/dev/null 2>&1 &
  echo "$(date -Iseconds) runsvdir started by sshd-recover" >>"$LOG"
  sleep 2
fi
sv up sshd >>"$LOG" 2>&1
echo "$(date -Iseconds) sv up sshd requested ($(sv status sshd 2>&1))" >>"$LOG"
