#!/data/data/com.termux/files/usr/bin/bash
# stayturgid-repair.sh — Termux-side self-heal for the remote-access stack.
# Invoked by the Tasker watchdog (via Termux:Tasker) and by the boot self-heal
# loop. Uses Shizuku's shell-privileged adbd on localhost:5555 for privileged
# checks/repairs (Termux's own app uid can't see shell-owned procs or all
# sockets, so detection goes through that shell). No AutoInput / no auth token.
#
# Exit 0 = healthy after repair; 1 = a subsystem still down, needs a higher tier
# (Tasker+AutoInput or reboot). Prints one STATUS line for the caller.

export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
# Termux adb daemon writes logs under TMPDIR; without this, localhost:5555 checks fail.
export TMPDIR="${TMPDIR:-${PREFIX:-/data/data/com.termux/files/usr}/tmp}"
mkdir -p "$TMPDIR" 2>/dev/null
LOG="$HOME/.stayturgid-repair.log"           # Termux-writable primary log
SDLOG=/sdcard/stayturgid_watchdog.log        # shared log (best effort; needs storage perm)
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { local m="$(ts) [repair] $*"; echo "$m" >> "$LOG" 2>/dev/null; echo "$m" >> "$SDLOG" 2>/dev/null; }

rc=0

sshd_listening() {
    ss -tln 2>/dev/null | grep -q ':8022 ' || \
        netstat -tln 2>/dev/null | grep -q ':8022 '
}

sshd_up() {
    pgrep -x sshd >/dev/null 2>&1 || sshd_listening
}

# --- 1. sshd (same uid as this script; also accept :8022 listen to avoid pgrep races) ---
if sshd_up; then
    SSHD=up
else
    sshd 2>/dev/null; sleep 1   # sshd daemonizes and may return non-zero even on success
    if sshd_up; then
        SSHD=restarted; log "sshd was down -> restarted"
    else
        SSHD=FAILED; rc=1; log "sshd restart FAILED"
    fi
fi

# --- 2. privileged shell via Shizuku's adbd on localhost:5555 ---
# A successful connect + shell uid 2000 is the authoritative "5555 is open" test
# from Termux (unprivileged ss/pgrep can't be trusted here).
SH=""
if adb connect localhost:5555 >/dev/null 2>&1 && \
   [ "$(adb -s localhost:5555 shell id -u 2>/dev/null | tr -d '\r')" = "2000" ]; then
    SH="adb -s localhost:5555 shell"
    PORT=open
    $SH "setprop service.adb.tcp.port 5555" >/dev/null 2>&1   # keep 5555 sticky across adbd restarts
else
    PORT=CLOSED_NO_SHELL; rc=1
    log "5555 CLOSED / no privileged shell — escalate to Tasker+AutoInput or reboot"
fi

# --- 3. shizuku (check via privileged shell; Termux uid can't see shell procs) ---
if [ -n "$SH" ]; then
    $SH "pgrep -f shizuku_server" >/dev/null 2>&1 && SHIZUKU=up || SHIZUKU=down
else
    SHIZUKU=unknown
fi

STATUS="STATUS port=$PORT shizuku=$SHIZUKU sshd=$SSHD shell=$([ -n "$SH" ] && echo yes || echo no)"
log "$STATUS rc=$rc"
echo "$STATUS"
exit $rc
