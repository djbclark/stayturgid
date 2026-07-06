#!/data/data/com.termux/files/usr/bin/bash
# Fast repair bridge for AutoJs6 when RUN_COMMAND from AutoJs6 is unavailable or slow.
# AutoJs6 writes /sdcard/stayturgid_repair_now; this loop runs stayturgid-repair.sh within ~2s.
# Deploy to ~/repair-bridge.sh, chmod +x, start from Termux (or add to boot):
#   nohup ~/repair-bridge.sh >> ~/.repair-bridge.log 2>&1 &
#
# Safe alongside the 5-min boot loop — idempotent repair script.

export PATH=/data/data/com.termux/files/usr/bin:$PATH
TRIGGER=/sdcard/stayturgid_repair_now
REPAIR="$HOME/stayturgid-repair.sh"
LOG="$HOME/.repair-bridge.log"
PIDFILE="$HOME/.repair-bridge.pid"

# Pidfile lets starters check liveness without pgrep -f (whose pattern would
# match the caller's own cmdline on Linux/Termux procps).
echo $$ > "$PIDFILE"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

while true; do
    if [[ -f "$TRIGGER" ]]; then
        rm -f "$TRIGGER"
        echo "$(ts) [bridge] trigger seen" >> "$LOG"
        if [[ -x "$REPAIR" ]]; then
            "$REPAIR" >> "$LOG" 2>&1
        else
            echo "$(ts) [bridge] missing $REPAIR" >> "$LOG"
        fi
    fi
    sleep 2
done
