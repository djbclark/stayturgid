#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot — launch AutoJs6 watchdog via boot-launcher.js (starts main.js if not running).
# Deploy to ~/.termux/boot/start-autojs6-watchdog.sh

_stg_bin=/data/data/com.termux/files/usr/bin
[ -d "$_stg_bin" ] && PATH="$_stg_bin:$PATH"
export PATH
export HOME="${HOME:-/data/data/com.termux/files/home}"
[ -f "$HOME/.stayturgid/env" ] && . "$HOME/.stayturgid/env"

if [[ -f /sdcard/stayturgid/autojs6/scripts/boot-launcher.js ]]; then
    BOOT_SCRIPT=/sdcard/stayturgid/autojs6/scripts/boot-launcher.js
else
    BOOT_SCRIPT="${STAYTURGID_SD:-/sdcard/stayturgid}/autojs6/scripts/boot-launcher.js"
fi
AUTOJS_PKG=org.autojs.autojs6
AUTOJS_RUN=org.autojs.autojs.external.open.RunIntentActivity

if [[ ! -f "$BOOT_SCRIPT" ]]; then
    echo "[$(date -Iseconds)] start-autojs6-watchdog: $BOOT_SCRIPT missing — deploy required" >> "$STG/logs/watchdog.log" 2>&1 || true
    exit 0
fi

# Let Wi-Fi, Shizuku, and unlock settle (Termux:Boot already slept 30s in start-adb.sh)
sleep 45

am start -a android.intent.action.VIEW \
    -d "file://${BOOT_SCRIPT}" \
    -t "text/javascript" \
    -n "${AUTOJS_PKG}/${AUTOJS_RUN}" >/dev/null 2>&1 || true
