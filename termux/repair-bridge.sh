#!/data/data/com.termux/files/usr/bin/bash
# Fast repair bridge for AutoJs6 when RUN_COMMAND from AutoJs6 is unavailable or
# slow. AutoJs6 writes <sd>/run/repair_now; this loop runs the repair within ~2s.
# Deployed to ~/.stayturgid/bin/repair-bridge.sh; started at boot.
#
# Safe alongside the 5-min boot loop — idempotent repair script.

_stg_bin=/data/data/com.termux/files/usr/bin
[ -d "$_stg_bin" ] && PATH="$_stg_bin:$PATH"
export PATH
export HOME="${HOME:-/data/data/com.termux/files/home}"
[ -f "$HOME/.stayturgid/env" ] && . "$HOME/.stayturgid/env"

# Single-root layout; every dir is created on demand so a user-deleted
# stayturgid dir self-heals rather than erroring.
STG="$HOME/.stayturgid"
SD="${STAYTURGID_SD:-/sdcard/stayturgid}"
TRIGGER="$SD/run/repair_now"
TRIGGER_SDCARD="/sdcard/stayturgid/run/repair_now"
REPAIR="$STG/bin/stayturgid-repair.sh"
LOG="$STG/logs/bridge.log"
PIDFILE="$STG/run/bridge.pid"

mkdir -p "$STG/logs" "$STG/run" "$SD/run" 2>/dev/null

# Pidfile lets starters check liveness without pgrep -f (whose pattern would
# match the caller's own cmdline on Linux/Termux procps).
echo $$ > "$PIDFILE"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

while true; do
    if [[ -f "$TRIGGER" || -f "$TRIGGER_SDCARD" ]]; then
        rm -f "$TRIGGER" "$TRIGGER_SDCARD"
        mkdir -p "$STG/logs" 2>/dev/null   # self-heal if the dir was deleted
        echo "$(ts) [bridge] trigger seen" >> "$LOG"
        if [[ -x "$REPAIR" ]]; then
            "$REPAIR" >> "$LOG" 2>&1
        else
            echo "$(ts) [bridge] missing $REPAIR" >> "$LOG"
        fi
    fi
    sleep 2
done
