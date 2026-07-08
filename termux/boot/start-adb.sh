#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot script — runs on every boot after first unlock
# Deploy to: ~/.termux/boot/start-adb.sh on device

# Ensure Termux binaries are on PATH (needed when run from runit context).
for _stg_bin in /data/data/com.termux/files/usr/bin /data/data/com.termux/files/usr/sbin; do
    [ -d "$_stg_bin" ] && PATH="$_stg_bin:$PATH"
done
export PATH
export HOME="${HOME:-/data/data/com.termux/files/home}"
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR=/data/data/com.termux/files/usr/tmp
export LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib

# Single-root layout. BIN holds the deployed scripts; STG/SD hold private and
# shared-storage state. mkdir -p so a user-deleted stayturgid dir self-heals.
STG="$HOME/.stayturgid"
BIN="$STG/bin"
[ -f "$STG/env" ] && . "$STG/env"
SD="${STAYTURGID_SD:-/sdcard/stayturgid}"
mkdir -p "$STG/logs" "$STG/run" "$STG/state" "$SD/logs" "$SD/run" "$SD/state" 2>/dev/null

# Hold a wakelock so Doze can't freeze Termux (and with it sshd + the
# self-heal loop below). Requires Termux:API app; no-op if missing.
termux-wake-lock 2>/dev/null || true

# Start SSH server so the device is reachable via ADB port-forward
# (or directly via the Tailscale IP on port 8022 when Tailscale is up)
sshd

# Keep sshd alive — the AutoJs6 watchdog checks its status and notifies on failure,
# but this loop is the self-healing mechanism (runs as Termux user, right UID).
# Low-battery tiers (30/25/20/…%) handled by ~/stayturgid_battery_alarm.py each loop.
# Runtime scripts are migrating shell -> Python (~/stayturgid_*.py); this loop
# invokes whichever form is deployed.
#
# The whole thing (WiFi-settle + TCP-port open + self-heal loop) runs in ONE
# backgrounded subshell so the pidfile is written IMMEDIATELY — a redeploy's
# restart handler verifies the pid without waiting out the 30s settle.
BOOTLOOP_PID_FILE="$STG/run/bootloop.pid"
(
    # Wait for WiFi/network to settle, then belt-and-suspenders open ADB TCP
    # (Shizuku TCP mode, the primary mechanism, usually beats this to it).
    sleep 30
    adb connect 127.0.0.1:5555 || true
    adb tcpip 5555 || true

    while true; do
    mkdir -p "$STG/state" "$SD/run" 2>/dev/null   # self-heal each cycle
    # Full Termux-side self-heal (sshd + privileged checks/repairs via
    # Shizuku's localhost:5555 shell, logged). Falls back to a bare sshd
    # restart if the repair script isn't deployed yet.
    if [ -x "$BIN/stayturgid-repair.sh" ]; then
        "$BIN/stayturgid-repair.sh" >/dev/null 2>&1
    else
        pgrep sshd > /dev/null 2>&1 || sshd
    fi

    if [ -x "$BIN/stayturgid_battery_alarm.py" ]; then
        python3 "$BIN/stayturgid_battery_alarm.py" >/dev/null 2>&1 || true
    fi

    # Screen held awake? Keep a restore-lock notification up (reappears each
    # cycle while the state persists; dismiss+ignore = deliberate keep-awake).
    if [ -x "$BIN/stayturgid_screen_awake_guard.py" ]; then
        python3 "$BIN/stayturgid_screen_awake_guard.py" check >/dev/null 2>&1 || true
    fi

    # Active screen-control lease: keep inversion + presence notification alive.
    if [ -x "$BIN/stayturgid_agent_presence.py" ]; then
        python3 "$BIN/stayturgid_agent_presence.py" guard >/dev/null 2>&1 || true
    fi

    # Daily GitHub version check (notify only; deploy from Mac).
    VERSION_CHECK_STAMP="$STG/state/last_version_check"
    now=$(date +%s)
    last=0
    if [ -f "$VERSION_CHECK_STAMP" ]; then
        last="$(cat "$VERSION_CHECK_STAMP" 2>/dev/null || true)"
    fi
    last="${last:-0}"
    if [ "$((now - last))" -ge 86400 ] && [ -x "$BIN/stayturgid_check_repo_version.py" ]; then
        python3 "$BIN/stayturgid_check_repo_version.py" >/dev/null 2>&1 || true
        echo "$now" > "$VERSION_CHECK_STAMP"
    fi

    # Nudge AutoJs6 only when the watchdog is stale — RunIntentActivity steals
    # foreground (YouTube etc. drop to PiP). Rate-limit to once per stale window
    # so a failed recovery does not PiP every 5 min.
    AUTOJS_NUDGE_STAMP="$STG/state/last_autojs_nudge"
    NUDGE_COOLDOWN_SEC=1500

    autojs_watchdog_stale() {
        local log="$SD/logs/watchdog.log"
        [ -f "$SD/autojs6/scripts/boot-launcher.js" ] || return 1
        [ -f "$log" ] || return 0
        python3 - "$log" <<'PY'
import datetime, sys
path = sys.argv[1]
last = None
with open(path, encoding="utf-8") as fh:
    for line in fh:
        if "[watchdog] cycle start" in line:
            last = line
if not last:
    sys.exit(0)
try:
    t = datetime.datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
    sys.exit(0 if (datetime.datetime.now() - t).total_seconds() >= 25 * 60 else 1)
except ValueError:
    sys.exit(0)
PY
    }

    autojs_nudge_cooled_down() {
        local last_nudge now
        [ ! -f "$AUTOJS_NUDGE_STAMP" ] && return 0
        last_nudge="$(cat "$AUTOJS_NUDGE_STAMP" 2>/dev/null || echo 0)"
        last_nudge="${last_nudge:-0}"
        now=$(date +%s)
        [ "$((now - last_nudge))" -ge "$NUDGE_COOLDOWN_SEC" ]
    }

    if autojs_watchdog_stale && autojs_nudge_cooled_down; then
        adb connect 127.0.0.1:5555 >/dev/null 2>&1 </dev/null || true
        adb -s localhost:5555 shell am force-stop org.autojs.autojs6 \
            >/dev/null 2>&1 </dev/null || true
        adb -s localhost:5555 shell am start \
            -a android.intent.action.VIEW \
            -d "file://$SD/autojs6/scripts/boot-launcher.js" \
            -t 'text/javascript' \
            -n 'org.autojs.autojs6/org.autojs.autojs.external.open.RunIntentActivity' \
            >/dev/null 2>&1 </dev/null || true
        date +%s > "$AUTOJS_NUDGE_STAMP"
    fi

        sleep 300
    done
) &
_bootloop_pid=$!
disown "$_bootloop_pid"
# Record the subshell's pid so a redeploy can restart the loop WITHOUT
# `pkill -f start-adb.sh` — that pattern self-matches any caller whose cmdline
# contains the path (the Ansible handler SIGTERM'd itself this way). Written
# immediately (the 30s settle runs inside the subshell). See the handler.
echo "$_bootloop_pid" > "$BOOTLOOP_PID_FILE"
