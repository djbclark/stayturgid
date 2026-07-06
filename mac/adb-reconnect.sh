#!/bin/bash
# Reconnects wireless ADB if the device has dropped.
# Runs every 60 seconds via launchd (installed by ansible/playbooks/mac.yml);
# exits silently when already connected. Failure alerting belongs to
# access-monitor.sh (debounced) — this script never notifies on failure.
#
# Usage: adb-reconnect.sh <alias>                       (conf-driven, preferred)
#        adb-reconnect.sh <serial> <ip:port> [ts:port]  (legacy positional)
#
# Device facts come from ~/.config/stayturgid/devices.conf (generated from the
# Ansible inventory). Connection candidates, tried in order:
#   1. last known-good address (cached per serial)
#   2. current LAN IP discovered over USB (handles DHCP changes)
#   3. mDNS _adb-tls-connect endpoint (ephemeral port — never cached)
#   4. the device's Tailscale address (stable fallback of last resort)

ADB=/opt/homebrew/bin/adb
[ -x "$ADB" ] || exit 1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../shared/mac/resolve-adb.sh
source "$SCRIPT_DIR/../shared/mac/resolve-adb.sh"

if row="$(_device_row "${1:-}")"; then
    read -r DEVICE_SERIAL TS_IP LAN_IP <<< "$row"
    [ "$DEVICE_SERIAL" = "-" ] && DEVICE_SERIAL="$1"
    DEFAULT_IP=""
    [ "$LAN_IP" != "-" ] && DEFAULT_IP="${LAN_IP}:5555"
    TAILSCALE_IP="${TS_IP}:5555"
else
    DEVICE_SERIAL=${1:?usage: adb-reconnect.sh <alias> | <serial> <ip:port> [ts:port]}
    DEFAULT_IP=${2:?legacy mode needs <ip:port>}
    TAILSCALE_IP=${3:-}
fi

DEVICE_FILE=$HOME/.config/stayturgid/device_ip_${DEVICE_SERIAL}
LOG=$HOME/Library/Logs/stayturgid-adb-reconnect.log
MAX_LINES=1000

# Trim log to last MAX_LINES lines when it grows large
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt "$MAX_LINES" ]; then
    tail -n "$MAX_LINES" "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

# Load last known IP (fall back to LAN/Tailscale on first run)
CACHED=$(cat "$DEVICE_FILE" 2>/dev/null || echo "${DEFAULT_IP:-$TAILSCALE_IP}")

# Exit silently if already connected and healthy (any candidate address)
for addr in "$CACHED" "$TAILSCALE_IP"; do
    [ -n "$addr" ] || continue
    "$ADB" devices 2>/dev/null | grep -qF "${addr}"$'\t'"device" && exit 0
done

# Not connected — try USB to discover the current LAN IP in case DHCP changed it
CURRENT_IP=$("$ADB" -s "$DEVICE_SERIAL" shell \
    "ip addr show wlan0 2>/dev/null | grep 'inet '" 2>/dev/null \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)

# mDNS: if Wireless Debugging is on, the device advertises a TLS endpoint.
# Works after reboot with no USB and no port 5555, if this host is paired.
MDNS_ADDR=$("$ADB" mdns services 2>/dev/null \
    | grep -F "adb-${DEVICE_SERIAL}" | grep -F '_adb-tls-connect' \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+' | head -1)

CANDIDATES="$CACHED"
[ -n "$CURRENT_IP" ] && CANDIDATES="${CURRENT_IP}:5555 $CANDIDATES"
[ -n "$MDNS_ADDR" ] && CANDIDATES="$CANDIDATES $MDNS_ADDR"
[ -n "$TAILSCALE_IP" ] && CANDIDATES="$CANDIDATES $TAILSCALE_IP"

for DEVICE in $CANDIDATES; do
    echo "$(date '+%Y-%m-%d %H:%M:%S')  [${DEVICE_SERIAL}] trying ${DEVICE}" >> "$LOG"
    result=$("$ADB" connect "$DEVICE" 2>&1)
    echo "$(date '+%Y-%m-%d %H:%M:%S')  [${DEVICE_SERIAL}] ${result}" >> "$LOG"
    if echo "$result" | grep -qF "connected to"; then
        # Don't cache the mDNS endpoint — its port is ephemeral (changes each
        # boot) and would poison the "last known-good" slot.
        if [ "$DEVICE" != "$CACHED" ] && [ "$DEVICE" != "$MDNS_ADDR" ]; then
            mkdir -p "$(dirname "$DEVICE_FILE")"
            echo "$DEVICE" > "$DEVICE_FILE"
        fi
        osascript -e "display notification \"Reconnected ${DEVICE}\" with title \"stayturgid\""
        exit 0
    fi
done

# No notification on failure: access-monitor.sh owns outage alerting.
echo "$(date '+%Y-%m-%d %H:%M:%S')  [${DEVICE_SERIAL}] unreachable on all candidates" >> "$LOG"
exit 1
