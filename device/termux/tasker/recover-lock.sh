# shellcheck shell=sh
# Sourced, never run: the mkdir lock shared by sshd-recover-tasker.sh,
# sshd-recover.sh and boot/00-start-services.sh. Four callers can fire at once
# (Tasker broadcast, native agent, firerpa_heal, Termux:Boot), and mkdir is
# the one atomic create-if-absent that needs nothing beyond a POSIX sh.
#
# The lock directory holds "owner" = "<pid> <epoch>". A lock is stale once its
# owner is dead or it is older than the caller's limit (a reused pid must not
# hold it forever), so a run killed by timeout or the low-memory killer never
# wedges the next one.

# recover_lock_take DIR STALE_SEC [WAIT_SEC]: exit 0 once DIR is ours. Waits up
# to WAIT_SEC (default 0) for a live holder before giving up.
recover_lock_take() {
  _rl_dir=$1 _rl_stale=$2 _rl_wait=${3:-0} _rl_broke=0
  while :; do
    if mkdir "$_rl_dir" 2>/dev/null; then
      echo "$$ $(date +%s)" >"$_rl_dir/owner"
      return 0
    fi
    # Break a stale lock once per call: if rm cannot remove it, waiting is
    # still bounded instead of spinning.
    if [ "$_rl_broke" = 0 ] && _recover_lock_stale "$_rl_dir" "$_rl_stale"; then
      _rl_broke=1
      rm -rf "$_rl_dir"
      continue
    fi
    [ "$_rl_wait" -gt 0 ] || return 1
    _rl_wait=$((_rl_wait - 1))
    sleep 1
  done
}

_recover_lock_stale() {
  _rl_owner=$(cat "$1/owner" 2>/dev/null)
  if [ -z "$_rl_owner" ]; then
    # The taker writes owner right after its mkdir; don't break it mid-write.
    sleep 1
    _rl_owner=$(cat "$1/owner" 2>/dev/null)
    [ -n "$_rl_owner" ] || return 0
  fi
  _rl_pid=${_rl_owner%% *}
  _rl_since=${_rl_owner#* }
  case "$_rl_pid" in "" | *[!0-9]*) return 0 ;; esac
  case "$_rl_since" in "" | *[!0-9]*) return 0 ;; esac
  kill -0 "$_rl_pid" 2>/dev/null || return 0
  [ $(($(date +%s) - _rl_since)) -gt "$2" ]
}

# recover_lock_release DIR: only removes a lock this process still owns, so a
# run that was judged stale cannot delete its successor's lock.
recover_lock_release() {
  case "$(cat "$1/owner" 2>/dev/null)" in
    "$$ "*) rm -rf "$1" ;;
  esac
}
