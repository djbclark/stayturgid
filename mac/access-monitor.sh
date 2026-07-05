#!/bin/bash
# Dead-man's switch: alerts when a device is unreachable on ALL access paths.
#
# Runs every 5 minutes via launchd. For each device it checks every known
# address for (a) an ADB connection and (b) an open SSH port. Only when
# every path fails for CONSECUTIVE_LIMIT consecutive runs does it fire a
# macOS notification — one per outage, not one per run. Recovery resets
# the counter and notifies once.
#
# Device list lives in the DEVICES array below: "name|adb_addrs|ssh_addrs"
# (comma-separated addresses; ssh check is a plain TCP probe of port 8022).

ADB=/opt/homebrew/bin/adb
STATE_DIR=$HOME/.config/stayturgid/access-monitor
LOG=$HOME/Library/Logs/stayturgid-access-monitor.log
CONSECUTIVE_LIMIT=2   # 2 runs x 5 min = alert after ~10 min of total outage

DEVICES=(
    "S24|192.168.68.55:5555,100.123.218.30:5555|100.123.218.30"
    "Pixel7a|192.168.68.57:5555,100.65.230.108:5555|100.65.230.108"
)

mkdir -p "$STATE_DIR"
[ -x "$ADB" ] || exit 1

# Trim log
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 1000 ]; then
    tail -n 1000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

ts() { date '+%Y-%m-%d %H:%M:%S'; }

for entry in "${DEVICES[@]}"; do
    IFS='|' read -r NAME ADB_ADDRS SSH_ADDRS <<< "$entry"
    STATE_FILE=$STATE_DIR/$NAME
    FAILS=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
    OK=""

    # ADB: connected already, or connectable right now?
    for addr in ${ADB_ADDRS//,/ }; do
        if "$ADB" devices 2>/dev/null | grep -qF "${addr}"$'\t'"device"; then
            OK="adb:$addr"; break
        fi
        if "$ADB" connect "$addr" 2>/dev/null | grep -qF "connected to"; then
            OK="adb:$addr"; break
        fi
    done

    # SSH: TCP probe of port 8022
    if [ -z "$OK" ]; then
        for host in ${SSH_ADDRS//,/ }; do
            if nc -z -G 5 "$host" 8022 2>/dev/null; then
                OK="ssh:$host"; break
            fi
        done
    fi

    if [ -n "$OK" ]; then
        if [ "$FAILS" -ge "$CONSECUTIVE_LIMIT" ]; then
            echo "$(ts)  $NAME RECOVERED via $OK" >> "$LOG"
            osascript -e "display notification \"$NAME reachable again ($OK)\" with title \"stayturgid access\"" 2>/dev/null
        fi
        echo 0 > "$STATE_FILE"
    else
        FAILS=$((FAILS + 1))
        echo "$FAILS" > "$STATE_FILE"
        echo "$(ts)  $NAME unreachable on all paths (consecutive: $FAILS)" >> "$LOG"
        if [ "$FAILS" -eq "$CONSECUTIVE_LIMIT" ]; then
            osascript -e "display notification \"$NAME unreachable on ALL paths (ADB + SSH) for ~10 min\" with title \"stayturgid access LOST\" sound name \"Basso\"" 2>/dev/null
        fi
    fi
done
