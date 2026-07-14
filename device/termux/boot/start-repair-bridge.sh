#!/data/data/com.termux/files/usr/bin/bash
export HOME="${HOME:-/data/data/com.termux/files/home}"
STG="$HOME/.stayturgid"
mkdir -p "$STG/logs" "$STG/run" 2>/dev/null || true
nohup python3 "$STG/bin/bridges.py" --mode repair >>"$STG/logs/repair-bridge.log" 2>&1 &
