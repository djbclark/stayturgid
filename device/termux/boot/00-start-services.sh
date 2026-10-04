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
if ! pgrep -x runsvdir >/dev/null 2>&1; then
  setsid "$PREFIX/bin/runsvdir" "$PREFIX/var/service" >/dev/null 2>&1 &
fi
# Give runsv a moment to claim the service dirs (and sshd its port) before
# the later boot scripts run their own checks.
sleep 3
