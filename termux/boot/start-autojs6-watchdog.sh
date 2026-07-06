#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot — launch AutoJs6 watchdog via boot-launcher.js (starts main.js if not running).
# Deploy to ~/.termux/boot/start-autojs6-watchdog.sh

export PATH=/data/data/com.termux/files/usr/bin:$PATH
export HOME=/data/data/com.termux/files/home

BOOT_SCRIPT=/sdcard/Scripts/stayturgid/scripts/boot-launcher.js
AUTOJS_PKG=org.autojs.autojs6
AUTOJS_RUN=org.autojs.autojs.external.open.RunIntentActivity

if [[ ! -f "$BOOT_SCRIPT" ]]; then
    exit 0
fi

# Let Wi-Fi, Shizuku, and unlock settle (Termux:Boot already slept 30s in start-adb.sh)
sleep 45

am start -a android.intent.action.VIEW \
    -d "file://${BOOT_SCRIPT}" \
    -t "text/javascript" \
    -n "${AUTOJS_PKG}/${AUTOJS_RUN}" >/dev/null 2>&1 || true
