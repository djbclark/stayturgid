#!/data/data/com.termux/files/usr/bin/bash
# Compatibility entry point — the self-heal logic is in stayturgid_repair.py.
# Kept as a bash script so AutoJs6's Termux RUN_COMMAND (which execs this path),
# the boot loop, and repair-bridge.sh all keep working unchanged. Exports a full
# PATH/HOME first so `python3` resolves under RUN_COMMAND's minimal environment.
export HOME="${HOME:-/data/data/com.termux/files/home}"
export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
[ -f "$HOME/.stayturgid/env" ] && . "$HOME/.stayturgid/env"
exec python3 "$HOME/.stayturgid/bin/stayturgid_repair.py" "$@"
