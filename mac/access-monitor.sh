#!/bin/bash
# Dead-man's switch: alerts when a device is unreachable on ALL access paths.
#
# Runs every 5 minutes via launchd (installed by ansible/playbooks/mac.yml).
# For each device it checks every known address for (a) an ADB connection and
# (b) an open SSH port. Only when every path fails for CONSECUTIVE_LIMIT
# consecutive runs does it fire a macOS notification — one per outage, not one
# per run. Recovery resets the counter and notifies once.
#
# Device list comes from ~/.config/stayturgid/devices.conf (generated from the
# Ansible inventory) — no device facts live in this script.

ADB=/opt/homebrew/bin/adb
CONF="${STAYTURGID_DEVICES_CONF:-$HOME/.config/stayturgid/devices.conf}"
STATE_DIR=$HOME/.config/stayturgid/access-monitor
LOG=$HOME/Library/Logs/stayturgid-access-monitor.log
CONSECUTIVE_LIMIT=2   # 2 runs x 5 min = alert after ~10 min of total outage

mkdir -p "$STATE_DIR"
[ -x "$ADB" ] || exit 1
[ -f "$CONF" ] || exit 0   # nothing to monitor until mac.yml generates the conf

# Trim log
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 1000 ]; then
    tail -n 1000 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

ts() { date '+%Y-%m-%d %H:%M:%S'; }

while read -r NAME _ TS_IP LAN_IP; do
    case "$NAME" in \#*|"") continue ;; esac
    ADB_ADDRS="${TS_IP}:5555"
    [ "$LAN_IP" != "-" ] && ADB_ADDRS="${LAN_IP}:5555 ${ADB_ADDRS}"
    STATE_FILE=$STATE_DIR/$NAME
    FAILS=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
    OK=""

    # ADB: connected already, or connectable right now?
    for addr in $ADB_ADDRS; do
        if "$ADB" devices 2>/dev/null | grep -qF "${addr}"$'\t'"device"; then
            OK="adb:$addr"; break
        fi
        if "$ADB" connect "$addr" 2>/dev/null | grep -qF "connected to"; then
            OK="adb:$addr"; break
        fi
    done

    # SSH: TCP probe of port 8022 on the Tailscale address
    if [ -z "$OK" ] && nc -z -G 5 "$TS_IP" 8022 2>/dev/null; then
        OK="ssh:$TS_IP"
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
done < "$CONF"
