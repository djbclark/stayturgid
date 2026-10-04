#!/data/data/com.termux/files/usr/bin/sh
# Start runit supervision first at boot (Termux:Boot runs this directory in
# name order) so sshd and any other enabled $PREFIX/var/service entries are
# already supervised before start-adb.sh's startup_sshd() pgrep-checks sshd.
# Without this ordering, startup_sshd() starts a bare sshd at boot and the
# first login shell's runsvdir then flaps against it for port 8022 forever.
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
# termux-services' per-service log/run scripts write to $LOGDIR/sv/<service>.
# Only a login shell's profile.d exports it; without it svlogd dies on
# "/sv/sshd", the log service stays down and sshd's output pipe has no reader.
export SVDIR="$PREFIX/var/service" LOGDIR="$PREFIX/var/log"
# Same lock as tasker/sshd-recover.sh: the native agent can fire a recovery
# while this runs, and both do check-then-start on runsvdir.
LOCK="$HOME/.stayturgid/run/runsvdir-start.lock"
locked=0
if [ -r "$HOME/.termux/tasker/recover-lock.sh" ]; then
  # shellcheck source=SCRIPTDIR/../tasker/recover-lock.sh
  . "$HOME/.termux/tasker/recover-lock.sh"
  mkdir -p "$HOME/.stayturgid/run" 2>/dev/null
  recover_lock_take "$LOCK" 60 10 && locked=1
fi
# pgrep -f, not -x: a runsvdir started by absolute path shows a truncated path
# as its process name here, so -x misses it and a second supervisor gets
# started (seen on all three phones, 2026-10-04).
if ! pgrep -f "[r]unsvdir $SVDIR" >/dev/null 2>&1; then
  setsid "$PREFIX/bin/runsvdir" "$SVDIR" >/dev/null 2>&1 &
fi
# Give runsv a moment to claim the service dirs (and sshd its port) before
# the later boot scripts run their own checks.
sleep 3
if [ "$locked" = 1 ]; then
  recover_lock_release "$LOCK"
fi
