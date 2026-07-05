#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot script — runs on every boot after first unlock
# Deploy to: ~/.termux/boot/start-adb.sh on device

# Ensure Termux binaries are on PATH (needed when run from runit context)
export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
export HOME=/data/data/com.termux/files/home
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR=/data/data/com.termux/files/usr/tmp
export LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib

# Hold a wakelock so Doze can't freeze Termux (and with it sshd + the
# self-heal loop below). Requires Termux:API app; no-op if missing.
termux-wake-lock 2>/dev/null || true

# Start SSH server so the device is reachable via ADB port-forward
# (or directly via the Tailscale IP on port 8022 when Tailscale is up)
sshd

# Wait for WiFi/network to settle
sleep 30

# Belt-and-suspenders: attempt to open ADB TCP port.
# Shizuku TCP mode (the primary mechanism) usually beats this to it.
adb connect 127.0.0.1:5555 || true
adb tcpip 5555 || true

# Keep sshd alive — Tasker watchdog checks its status and notifies on failure,
# but this loop is the self-healing mechanism (runs as Termux user, right UID).
# Also fires a low-battery alarm: if the device is discharging below the
# threshold, the whole remote-access stack dies with the battery, so warn
# loudly and repeatedly (Tasker can't reliably read charging state; Termux:API can).
BATT_THRESHOLD=30
BATT_ALARMED=0
while true; do
    # Full Termux-side self-heal (sshd + privileged checks/repairs via
    # Shizuku's localhost:5555 shell, logged). Falls back to a bare sshd
    # restart if the repair script isn't deployed yet.
    if [ -x "$HOME/stayturgid-repair.sh" ]; then
        "$HOME/stayturgid-repair.sh" >/dev/null 2>&1
    else
        pgrep sshd > /dev/null 2>&1 || sshd
    fi

    batt=$(termux-battery-status 2>/dev/null)
    if [ -n "$batt" ]; then
        pct=$(echo "$batt" | grep -o '"percentage": *[0-9]*' | grep -o '[0-9]*')
        status=$(echo "$batt" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4)
        if [ -n "$pct" ] && [ "$pct" -le "$BATT_THRESHOLD" ] && [ "$status" != "CHARGING" ] && [ "$status" != "FULL" ]; then
            if [ "$BATT_ALARMED" -eq 0 ]; then
                termux-notification --id stayturgid-batt --priority max \
                    --title "⚠ stayturgid: battery ${pct}% & NOT charging" \
                    --content "Remote access dies when this device powers off. Plug in a charger." 2>/dev/null
                termux-toast "stayturgid: battery ${pct}%, not charging — plug in!" 2>/dev/null
                BATT_ALARMED=1
            fi
        else
            [ "$BATT_ALARMED" -eq 1 ] && termux-notification-remove stayturgid-batt 2>/dev/null
            BATT_ALARMED=0
        fi
    fi

    # AutoJs6 mode: ensure main.js is running (boot-launcher no-ops if already up).
    if grep -q '^autojs6$' /sdcard/stayturgid_automation_mode.txt 2>/dev/null \
        && [ -f /sdcard/Scripts/stayturgid/scripts/boot-launcher.js ]; then
        am start -a android.intent.action.VIEW \
            -d 'file:///sdcard/Scripts/stayturgid/scripts/boot-launcher.js' \
            -t 'text/javascript' \
            -n 'org.autojs.autojs6/org.autojs.autojs.external.open.RunIntentActivity' \
            >/dev/null 2>&1 || true
    fi

    sleep 300
done &
