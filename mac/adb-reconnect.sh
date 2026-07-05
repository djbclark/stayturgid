#!/bin/bash
# Reconnects wireless ADB if the device has dropped.
# Intended to run every 60 seconds via launchd — exits silently when already connected.
#
# Usage: adb-reconnect.sh [DEVICE_SERIAL] [DEFAULT_IP:PORT] [TAILSCALE_IP:PORT]
#   No args = Pixel 7a defaults (backwards compatible with the original plist).
#
# Connection candidates, tried in order until one succeeds:
#   1. last known-good address (cached in DEVICE_FILE)
#   2. current LAN IP discovered over USB (handles DHCP changes)
#   3. the device's Tailscale address (stable; works off-LAN and across
#      DHCP changes — this is the fallback of last resort and also the
#      repair path when the LAN address is unreachable)

ADB=/opt/homebrew/bin/adb
DEVICE_SERIAL=${1:-35261JEHN12374}
DEFAULT_IP=${2:-192.168.68.62:5555}
TAILSCALE_IP=${3:-}
DEVICE_FILE=$HOME/.config/stayturgid/device_ip_${DEVICE_SERIAL}
LOG=$HOME/Library/Logs/stayturgid-adb-reconnect.log
MAX_LINES=1000

[ -x "$ADB" ] || exit 1

# Trim log to last MAX_LINES lines when it grows large
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt "$MAX_LINES" ]; then
    tail -n "$MAX_LINES" "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# Load last known IP (fall back to default on first run)
CACHED=$(cat "$DEVICE_FILE" 2>/dev/null || echo "$DEFAULT_IP")

# Exit silently if already connected and healthy (any candidate address)
for addr in "$CACHED" "$TAILSCALE_IP"; do
    [ -n "$addr" ] || continue
    "$ADB" devices 2>/dev/null | grep -qF "${addr}"$'\t'"device" && exit 0
done

# Not connected — try USB to discover the current LAN IP in case DHCP changed it
CURRENT_IP=$("$ADB" -s "$DEVICE_SERIAL" shell \
    "ip addr show wlan0 2>/dev/null | grep 'inet '" 2>/dev/null \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)

CANDIDATES="$CACHED"
[ -n "$CURRENT_IP" ] && CANDIDATES="${CURRENT_IP}:5555 $CANDIDATES"
[ -n "$TAILSCALE_IP" ] && CANDIDATES="$CANDIDATES $TAILSCALE_IP"

for DEVICE in $CANDIDATES; do
    echo "$(date '+%Y-%m-%d %H:%M:%S')  [${DEVICE_SERIAL}] trying ${DEVICE}" >> "$LOG"
    result=$("$ADB" connect "$DEVICE" 2>&1)
    echo "$(date '+%Y-%m-%d %H:%M:%S')  [${DEVICE_SERIAL}] ${result}" >> "$LOG"
    if echo "$result" | grep -qF "connected to"; then
        if [ "$DEVICE" != "$CACHED" ]; then
            mkdir -p "$(dirname "$DEVICE_FILE")"
            echo "$DEVICE" > "$DEVICE_FILE"
        fi
        osascript -e "display notification \"Reconnected ${DEVICE}\" with title \"stayturgid\""
        exit 0
    fi
done

osascript -e "display notification \"Failed: ${DEVICE_SERIAL} unreachable on all addresses\" with title \"stayturgid\""
exit 1
