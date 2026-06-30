#!/bin/bash
# Reconnects wireless ADB if the device has dropped.
# Intended to run every 60 seconds via launchd — exits silently when already connected.
#
# IP discovery: if the known IP fails, attempts to find the current device IP
# via USB (serial DEVICE_SERIAL). This handles DHCP changes across reboots.
# The discovered IP is cached to DEVICE_FILE for subsequent runs.

ADB=/opt/homebrew/bin/adb
DEVICE_SERIAL=35261JEHN12374
DEVICE_FILE=$HOME/.config/stayturgid/device_ip
DEFAULT_IP=192.168.68.62:5555
LOG=$HOME/Library/Logs/stayturgid-adb-reconnect.log
MAX_LINES=1000

[ -x "$ADB" ] || exit 1

# Trim log to last MAX_LINES lines when it grows large
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt "$MAX_LINES" ]; then
    tail -n "$MAX_LINES" "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# Load last known IP (fall back to default on first run)
DEVICE=$(cat "$DEVICE_FILE" 2>/dev/null || echo "$DEFAULT_IP")

# Exit silently if already connected and healthy
"$ADB" devices 2>/dev/null | grep -qF "${DEVICE}"$'\t'"device" && exit 0

# Not connected — try USB to discover the current IP in case DHCP changed it
CURRENT_IP=$("$ADB" -s "$DEVICE_SERIAL" shell \
    "ip addr show wlan0 2>/dev/null | grep 'inet '" 2>/dev/null \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)

if [ -n "$CURRENT_IP" ] && [ "${CURRENT_IP}:5555" != "$DEVICE" ]; then
    DEVICE="${CURRENT_IP}:5555"
    mkdir -p "$(dirname "$DEVICE_FILE")"
    echo "$DEVICE" > "$DEVICE_FILE"
    echo "$(date '+%Y-%m-%d %H:%M:%S')  IP changed → ${DEVICE}" >> "$LOG"
fi

# Attempt reconnect, log, and notify
echo "$(date '+%Y-%m-%d %H:%M:%S')  reconnecting ${DEVICE}" >> "$LOG"
result=$("$ADB" connect "$DEVICE" 2>&1)
echo "$(date '+%Y-%m-%d %H:%M:%S')  ${result}" >> "$LOG"

if echo "$result" | grep -qF "connected to"; then
    osascript -e "display notification \"Reconnected ${DEVICE}\" with title \"stayturgid\""
else
    osascript -e "display notification \"Failed: ${result}\" with title \"stayturgid\""
fi
