#!/data/data/com.termux/files/usr/bin/bash
export HOME="${HOME:-/data/data/com.termux/files/home}"
STG="$HOME/.stayturgid"
mkdir -p "$STG/logs" "$STG/run" 2>/dev/null || true
nohup python3 "$STG/bin/bridges.py" --mode autojs6 >>"$STG/logs/autojs6-bridge.log" 2>&1 &
