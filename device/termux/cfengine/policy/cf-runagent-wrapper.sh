#!/data/data/com.termux/files/usr/bin/bash
# CFEngine cf-runagent wrapper — sets Termux environment before invoking
# cf-agent.  cf-serverd's cfruncommand runs this script, which ensures
# PATH + LD_LIBRARY_PATH are correct for the Termux prefix.

export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH"
export HOME="/data/data/com.termux/files/home"
export PREFIX="/data/data/com.termux/files/usr"
export TMPDIR="/data/data/com.termux/files/usr/tmp"
export LD_LIBRARY_PATH="/data/data/com.termux/files/usr/lib"
export LC_ALL="C"
# Carries ADB_LOCAL_TRANSPORT_MAX_PORT: the policy's adb call can start
# Termux's adb server.
# shellcheck source=/dev/null
[ -r "$HOME/.stayturgid/env" ] && . "$HOME/.stayturgid/env"

exec "$PREFIX/bin/cf-agent" -f "$HOME/.stayturgid/cfengine/stayturgid.cf" "$@"
