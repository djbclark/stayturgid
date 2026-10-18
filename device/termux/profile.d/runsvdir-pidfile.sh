# shellcheck shell=sh
# Sourced by $PREFIX/etc/profile in every login shell, before termux-services'
# start-services.sh (profile.d/*.sh runs in name order; "runsvdir-" < "start-").
#
# start-services.sh runs `service-daemon start`, and that trusts only
# $PREFIX/var/run/service-daemon.pid (start-stop-daemon -p ... -x runsvdir). Our
# boot and recovery scripts start runsvdir directly and never write that file, so
# each new Termux session started another runsvdir (t2e had 8, 2026-10-17).
# Point the pidfile at the running runsvdir; with none running, leave it alone
# and service-daemon starts one as before. Deployed by termux_userland.
_stayturgid_rsv=$(pgrep -o -f "[r]unsvdir $PREFIX/var/service\$" 2>/dev/null) &&
  mkdir -p "$PREFIX/var/run" &&
  echo "$_stayturgid_rsv" >"$PREFIX/var/run/service-daemon.pid"
unset _stayturgid_rsv
