#!/data/data/com.termux/files/usr/bin/bash
export HOME="${HOME:-/data/data/com.termux/files/home}"
STG="$HOME/.stayturgid"
mkdir -p "$STG/logs" "$STG/run" 2>/dev/null || true
PROC_ROOT="${PROC_ROOT:-/proc}"
pid="$(cat "$STG/run/bridge.pid" 2>/dev/null || true)"
if [ -n "$pid" ] && [ -d "$PROC_ROOT/$pid" ] && grep -q "bridges" "$PROC_ROOT/$pid/cmdline" 2>/dev/null; then
  exit 0
fi
nohup python3 "$STG/bin/stayturgid_bridges.py" --mode repair >>"$STG/logs/repair-bridge.log" 2>&1 &
