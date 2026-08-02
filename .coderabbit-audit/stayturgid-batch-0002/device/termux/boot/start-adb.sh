#!/data/data/com.termux/files/usr/bin/bash
export HOME="${HOME:-/data/data/com.termux/files/home}"
export PREFIX=/data/data/com.termux/files/usr
export PATH="$PREFIX/bin:$PATH"
exec "$PREFIX/bin/python3" "$HOME/.stayturgid/bin/start_adb.py"
