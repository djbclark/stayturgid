#!/data/data/com.termux/files/usr/bin/sh
# Tasker's SSHD_RECOVER profile points RUN_COMMAND_PATH here, not at
# sshd-recover.sh, so a run that really came through Tasker leaves a marker no
# other caller does (firerpa_heal.py runs sshd-recover.sh directly via
# run-as). fleet_health reads the marker's age as proof that the keyguard-proof
# recovery path still works on this phone; fleet_health_monitor nags until it does.
export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export PATH="$PREFIX/bin:$PATH"
STATE="$HOME/.stayturgid/state"
mkdir -p "$STATE" 2>/dev/null
date +%s >"$STATE/tasker-sshd-recover.ts"
exec "$(dirname "$0")/sshd-recover.sh"
