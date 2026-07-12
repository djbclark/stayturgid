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
# Remove a stale runsv down file that silently blocks sshd startup.
rm -f /data/data/com.termux/files/usr/var/service/sshd/down 2>/dev/null || true
sshd

# ── FIRERPA failsafe daemon (optional) ──────────────────────────────────────
# Start the FIRERPA server on port 65000 if the binary exists.
# Provides gRPC backup control channel independent of Termux sshd + Shizuku.
FIRERPA_DIR=/data/local/tmp/firerpa/server
FIRERPA_PID_FILE="$STG/run/firerpa.pid"
FIRERPA_ENABLED="${STAYTURGID_FIRERPA_ENABLED:-1}"

if [ "$FIRERPA_ENABLED" = "1" ] && [ -x "$FIRERPA_DIR/bin/python3.9" ]; then
    if [ ! -f "$FIRERPA_PID_FILE" ] || ! kill -0 "$(cat "$FIRERPA_PID_FILE" 2>/dev/null)" 2>/dev/null; then
        (cd "$FIRERPA_DIR" && PATH="$FIRERPA_DIR/bin:$PATH" \
         LD_LIBRARY_PATH="$FIRERPA_DIR/lib" \
         nohup "$FIRERPA_DIR/bin/python3.9" -u -m lamda --launch --port=65000 \
         > "$STG/logs/firerpa.log" 2>&1 &)
        echo "$!" > "$FIRERPA_PID_FILE"
        echo "[$(date +%H:%M:%S)] FIRERPA started (pid $(cat $FIRERPA_PID_FILE))" >> "$STG/logs/boot.log"
    fi
fi

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
    if [ -x "$BIN/stayturgid_repair.py" ]; then
        "$BIN/stayturgid_repair.py" >/dev/null 2>&1
    else
        pgrep sshd > /dev/null 2>&1 || sshd
    fi

    # Ensure Termux:API is healthy before calling any scripts that use it.
    # When KeepAliveService dies (Android memory pressure) or the socket
    # gets stuck, CLI calls produce "Error in ResultReturner" notifications
    # that stack up in the shade.  Force-stop clears them and a fresh
    # start restores normal operation.  Cost is ~4 s (force-stop + restart
    # + one battery-status probe); skipped when API is already responsive.
    if command -v termux-battery-status >/dev/null 2>&1; then
        # Wrap in timeout — Termux:API can hang on some Android versions.
        if ! timeout 8 termux-battery-status >/dev/null 2>&1; then
            adb -s localhost:5555 shell am force-stop com.termux.api 2>/dev/null || true
            sleep 2
            termux-api-start >/dev/null 2>&1 || true
            sleep 2
        else
            # API is responsive — just ensure KeepAliveService is bound.
            termux-api-start >/dev/null 2>&1 || true
        fi
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

    # Termux-primary repair (above) owns self-heal. Observe AutoJs6 liveness
    # without launching RunIntentActivity (YouTube PiP / foreground steal).
    if [ -x "$BIN/stayturgid_autojs6_guard.py" ]; then
        python3 "$BIN/stayturgid_autojs6_guard.py" check >/dev/null 2>&1 || true
    fi

    # Fire OS: no Termux→localhost:5555 — ask fleet peers (or Mac) to start
    # Shizuku + Handsets (rate-limited inside the script).
    if [ "${STAYTURGID_NO_LOCAL_ADB:-0}" = "1" ] \
        && [ "${STAYTURGID_PEER_BOOTSTRAP:-1}" != "0" ] \
        && [ -x "$BIN/stayturgid_peer_keepalive.py" ]; then
        python3 "$BIN/stayturgid_peer_keepalive.py" >/dev/null 2>&1 || true
    fi

    # CFEngine standalone self-heal: runs every 5-min cycle alongside
    # stayturgid_repair.py.  Reports drift and auto-repairs sshd, mirror,
    # and Mac PATH leaks.  Zero Mac dependency.
    CFENGINE_CF="$STG/cfengine/stayturgid.cf"
    if [ -x "$PREFIX/bin/cf-agent" ] && [ -f "$CFENGINE_CF" ]; then
        "$PREFIX/bin/cf-agent" -Kf "$CFENGINE_CF" >> "$STG/logs/repair-cfengine.log" 2>&1 || true
    fi

    # FIRERPA monitor: restart the failsafe daemon if it died.
    if [ "$FIRERPA_ENABLED" = "1" ] && [ -f "$FIRERPA_PID_FILE" ]; then
        _firerpa_pid="$(cat "$FIRERPA_PID_FILE" 2>/dev/null || true)"
        if [ -z "$_firerpa_pid" ] || ! kill -0 "$_firerpa_pid" 2>/dev/null; then
            (cd "$FIRERPA_DIR" && PATH="$FIRERPA_DIR/bin:$PATH" \
             LD_LIBRARY_PATH="$FIRERPA_DIR/lib" \
             nohup "$FIRERPA_DIR/bin/python3.9" -u -m lamda --launch --port=65000 \
             > "$STG/logs/firerpa.log" 2>&1 &)
            echo "$!" > "$FIRERPA_PID_FILE"
            echo "[$(date +%H:%M:%S)] FIRERPA restarted (old pid $_firerpa_pid dead)" >> "$STG/logs/boot.log"
        fi
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
