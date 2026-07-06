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

# Keep sshd alive — the AutoJs6 watchdog checks its status and notifies on failure,
# but this loop is the self-healing mechanism (runs as Termux user, right UID).
# Low-battery tiers (30/25/20/…%) handled by ~/stayturgid-battery-alarm.sh each loop.
while true; do
    # Full Termux-side self-heal (sshd + privileged checks/repairs via
    # Shizuku's localhost:5555 shell, logged). Falls back to a bare sshd
    # restart if the repair script isn't deployed yet.
    if [ -x "$HOME/stayturgid-repair.sh" ]; then
        "$HOME/stayturgid-repair.sh" >/dev/null 2>&1
    else
        pgrep sshd > /dev/null 2>&1 || sshd
    fi

    if [ -x "$HOME/stayturgid-battery-alarm.sh" ]; then
        "$HOME/stayturgid-battery-alarm.sh" >/dev/null 2>&1 || true
    fi

    # Daily GitHub version check (notify only; deploy from Mac).
    VERSION_CHECK_STAMP="$HOME/.stayturgid_last_version_check"
    now=$(date +%s)
    last=0
    [ -f "$VERSION_CHECK_STAMP" ] && last=$(cat "$VERSION_CHECK_STAMP" 2>/dev/null || echo 0)
    if [ "$((now - last))" -ge 86400 ] && [ -x "$HOME/check-repo-version.sh" ]; then
        "$HOME/check-repo-version.sh" >/dev/null 2>&1 || true
        echo "$now" > "$VERSION_CHECK_STAMP"
    fi

    # Ensure AutoJs6 watchdog is running (boot-launcher no-ops if main.js already up).
    if [ -f /sdcard/Scripts/stayturgid/scripts/boot-launcher.js ]; then
        am start -a android.intent.action.VIEW \
            -d 'file:///sdcard/Scripts/stayturgid/scripts/boot-launcher.js' \
            -t 'text/javascript' \
            -n 'org.autojs.autojs6/org.autojs.autojs.external.open.RunIntentActivity' \
            >/dev/null 2>&1 || true
    fi

    sleep 300
done &
