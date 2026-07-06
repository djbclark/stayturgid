#!/data/data/com.termux/files/usr/bin/bash
# Compatibility shim — the presence/consent tool is agent-agnostic and lives
# in agent-presence.sh (any AI passes its own name: 3rd arg or STAYTURGID_AGENT).
# Existing callers of claude-presence.sh keep working through this shim.
exec "$(dirname "$0")/agent-presence.sh" "$@"
