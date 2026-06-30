#!/bin/bash
# Reconnects wireless ADB if the device has dropped.
# Intended to run every 60 seconds via launchd — exits silently when already connected.

ADB=/opt/homebrew/bin/adb
DEVICE=192.168.68.59:5555
LOG=$HOME/Library/Logs/stayturgid-adb-reconnect.log
MAX_LINES=1000

[ -x "$ADB" ] || exit 1

# Trim log to last MAX_LINES lines when it grows large
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt "$MAX_LINES" ]; then
    tail -n "$MAX_LINES" "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# Exit silently if already connected and healthy
"$ADB" devices 2>/dev/null | grep -qF "${DEVICE}"$'\t'"device" && exit 0

# Attempt reconnect, log, and notify
echo "$(date '+%Y-%m-%d %H:%M:%S')  reconnecting ${DEVICE}" >> "$LOG"
result=$("$ADB" connect "$DEVICE" 2>&1)
echo "$(date '+%Y-%m-%d %H:%M:%S')  ${result}" >> "$LOG"

if echo "$result" | grep -qF "connected to"; then
    osascript -e "display notification \"Reconnected ${DEVICE}\" with title \"stayturgid\""
else
    osascript -e "display notification \"Failed: ${result}\" with title \"stayturgid\""
fi
