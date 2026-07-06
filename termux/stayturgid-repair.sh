#!/data/data/com.termux/files/usr/bin/bash
# stayturgid-repair.sh — Termux-side self-heal for the remote-access stack.
# Invoked by the AutoJs6 watchdog (RUN_COMMAND / repair-bridge) and by the boot
# self-heal loop. Uses Shizuku's shell-privileged adbd on localhost:5555 for
# privileged checks/repairs (Termux's own app uid can't see shell-owned procs or all
# sockets, so detection goes through that shell). No UI automation / no auth token.
#
# Exit 0 = healthy after repair; 1 = a subsystem still down, needs a higher tier
# (AutoJs6 UI repair or reboot). Prints one STATUS line for the caller.

export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export HOME="${HOME:-/data/data/com.termux/files/home}"
# Termux adb daemon writes logs under TMPDIR; without this, localhost:5555 checks fail.
export TMPDIR="${TMPDIR:-${PREFIX}/tmp}"
mkdir -p "$TMPDIR" 2>/dev/null
LOCKFILE="${PREFIX}/tmp/stayturgid-repair.lock"
LOG="$HOME/.stayturgid-repair.log"           # Termux-writable primary log
SDLOG=/sdcard/stayturgid_watchdog.log        # shared log (best effort; needs storage perm)
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { local m; m="$(ts) [repair] $*"; echo "$m" >> "$LOG" 2>/dev/null; echo "$m" >> "$SDLOG" 2>/dev/null; }

# Keep logs bounded: the AutoJs6 watchdog re-reads SDLOG in full each cycle.
trim_log() {
    local f="$1" n
    [ -f "$f" ] || return 0
    n=$(wc -l < "$f" 2>/dev/null) || return 0
    if [ "${n:-0}" -gt 1000 ]; then
        tail -n 500 "$f" > "${f}.tmp" 2>/dev/null && mv "${f}.tmp" "$f"
    fi
}

sshd_listening() {
    ss -tln 2>/dev/null | grep -q ':8022 ' || \
        netstat -tln 2>/dev/null | grep -q ':8022 '
}

sshd_up() {
    pgrep -x sshd >/dev/null 2>&1 || pgrep -f '[s]shd' >/dev/null 2>&1 || sshd_listening
}

exec 9>"$LOCKFILE"
if ! flock -n 9; then
    # Another invocation holds the lock. Read-only probe; STATUS here is
    # advisory only (exit 0 regardless) — the lock holder does the real repair
    # and reports authoritatively.
    SSHD=unknown; PORT=unknown; SHIZUKU=unknown; SH=""
    if sshd_up; then
        SSHD=up
    elif sshd_listening; then
        SSHD=up
    fi
    if adb connect localhost:5555 >/dev/null 2>&1 && \
       [ "$(adb -s localhost:5555 shell id -u 2>/dev/null | tr -d '\r')" = "2000" ]; then
        SH="adb -s localhost:5555 shell"; PORT=open
        $SH "pgrep -f shizuku_server" >/dev/null 2>&1 && SHIZUKU=up || SHIZUKU=down
    else
        PORT=CLOSED_NO_SHELL
    fi
    STATUS="STATUS port=$PORT shizuku=$SHIZUKU sshd=$SSHD shell=$([ -n "$SH" ] && echo yes || echo no)"
    log "$STATUS rc=0 (skipped-duplicate)"
    echo "$STATUS"
    exit 0
fi

trim_log "$LOG"
trim_log "$SDLOG"

rc=0

# --- 1. sshd (same uid as this script; also accept :8022 listen to avoid pgrep races) ---
if sshd_up; then
    SSHD=up
else
    if ! sshd_listening; then
        sshd 2>/dev/null
    fi
    sleep 2
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
    log "5555 CLOSED / no privileged shell — escalate to AutoJs6 UI repair or reboot"
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
