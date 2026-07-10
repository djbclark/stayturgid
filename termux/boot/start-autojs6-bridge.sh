#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot — start the AutoJs6 restart bridge (trigger-file listener).
# Deploy to ~/.termux/boot/start-autojs6-bridge.sh when using autojs6/ stack.

_stg_bin=/data/data/com.termux/files/usr/bin
[ -d "$_stg_bin" ] && PATH="$_stg_bin:$PATH"
export PATH
export HOME="${HOME:-/data/data/com.termux/files/home}"

STG="$HOME/.stayturgid"
BRIDGE="$STG/bin/autojs6-bridge.sh"
mkdir -p "$STG/logs" "$STG/run" 2>/dev/null

bridge_running() {
    local pid root="${PROC_ROOT:-/proc}"
    pid="$(cat "$STG/run/autojs6-bridge.pid" 2>/dev/null)" || return 1
    [ -n "$pid" ] && [ -d "$root/$pid" ] && \
        grep -q "autojs6-bridge" "$root/$pid/cmdline" 2>/dev/null
}

if [[ -x "$BRIDGE" ]] && ! bridge_running; then
    nohup "$BRIDGE" >> "$STG/logs/autojs6-bridge.log" 2>&1 &
    disown
fi
