#!/data/data/com.termux/files/usr/bin/bash
# Optional Termux:Boot companion for AutoJs6 mode — fast repair trigger listener.
# Deploy to ~/.termux/boot/start-repair-bridge.sh when using autojs6/ stack.
# Coexists with start-adb.sh; does not replace it.

_stg_bin=/data/data/com.termux/files/usr/bin
[ -d "$_stg_bin" ] && PATH="$_stg_bin:$PATH"
export PATH
export HOME="${HOME:-/data/data/com.termux/files/home}"

STG="$HOME/.stayturgid"
BRIDGE="$STG/bin/repair-bridge.sh"
mkdir -p "$STG/logs" "$STG/run" 2>/dev/null   # self-heal

# Liveness via pidfile, not pgrep -f: on Termux (procps) a pgrep -f pattern
# containing "repair-bridge.sh" matches THIS script's own cmdline, so the
# old guard always self-matched and the bridge never started at boot.
bridge_running() {
    local pid root="${PROC_ROOT:-/proc}"
    pid="$(cat "$STG/run/bridge.pid" 2>/dev/null)" || return 1
    [ -n "$pid" ] && [ -d "$root/$pid" ] && \
        grep -q "repair-bridge" "$root/$pid/cmdline" 2>/dev/null
}

if [[ -x "$BRIDGE" ]] && ! bridge_running; then
    nohup "$BRIDGE" >> "$STG/logs/bridge.log" 2>&1 &
    disown
fi
