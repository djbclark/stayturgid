#!/data/data/com.termux/files/usr/bin/bash
# Fast AutoJs6 restart bridge — guard writes <sd>/run/start_autojs6_now;
# this loop runs boot-launcher.js via am start within ~2s (rate-limited).
# Deployed to ~/.stayturgid/bin/autojs6-bridge.sh; started at boot.
#
# Keeps RunIntentActivity out of the 5-min repair loop (see start-adb.sh).

_stg_bin=/data/data/com.termux/files/usr/bin
[ -d "$_stg_bin" ] && PATH="$_stg_bin:$PATH"
export PATH
export HOME="${HOME:-/data/data/com.termux/files/home}"
[ -f "$HOME/.stayturgid/env" ] && . "$HOME/.stayturgid/env"

STG="$HOME/.stayturgid"
SD="${STAYTURGID_SD:-/sdcard/stayturgid}"
TRIGGER="$SD/run/start_autojs6_now"
TRIGGER_SDCARD="/sdcard/stayturgid/run/start_autojs6_now"
LOG="$STG/logs/autojs6-bridge.log"
PIDFILE="$STG/run/autojs6-bridge.pid"
COOLDOWN_STAMP="$STG/state/last_autojs6_bridge_start"
COOLDOWN_SEC=1800

if [[ -f /sdcard/stayturgid/autojs6/scripts/boot-launcher.js ]]; then
    BOOT_SCRIPT=/sdcard/stayturgid/autojs6/scripts/boot-launcher.js
else
    BOOT_SCRIPT="${SD}/autojs6/scripts/boot-launcher.js"
fi
AUTOJS_PKG=org.autojs.autojs6
AUTOJS_RUN=org.autojs.autojs.external.open.RunIntentActivity

mkdir -p "$STG/logs" "$STG/run" "$STG/state" "$SD/run" 2>/dev/null

echo $$ > "$PIDFILE"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

cooldown_ok() {
    local now last=0
    now=$(date +%s)
    if [[ -f "$COOLDOWN_STAMP" ]]; then
        last="$(cat "$COOLDOWN_STAMP" 2>/dev/null || echo 0)"
    fi
    last="${last:-0}"
    [[ "$((now - last))" -ge "$COOLDOWN_SEC" ]]
}

start_boot_launcher() {
    if [[ ! -f "$BOOT_SCRIPT" ]]; then
        echo "$(ts) [autojs6-bridge] missing $BOOT_SCRIPT" >> "$LOG"
        return 1
    fi
    am start -a android.intent.action.VIEW \
        -d "file://${BOOT_SCRIPT}" \
        -t "text/javascript" \
        -n "${AUTOJS_PKG}/${AUTOJS_RUN}" >> "$LOG" 2>&1
    echo "$(date +%s)" > "$COOLDOWN_STAMP"
    echo "$(ts) [autojs6-bridge] am start boot-launcher.js" >> "$LOG"
}

while true; do
    if [[ -f "$TRIGGER" || -f "$TRIGGER_SDCARD" ]]; then
        rm -f "$TRIGGER" "$TRIGGER_SDCARD"
        echo "$(ts) [autojs6-bridge] trigger seen" >> "$LOG"
        if cooldown_ok; then
            start_boot_launcher
        else
            echo "$(ts) [autojs6-bridge] skipped (cooldown)" >> "$LOG"
        fi
    fi
    sleep 2
done
