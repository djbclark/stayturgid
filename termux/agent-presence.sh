#!/data/data/com.termux/files/usr/bin/bash
# Compatibility entry point — the logic is in stayturgid_agent_presence.py.
# Agents (and the claude-presence.sh alias) call this stable name per the
# documented phone-announcement protocol; this keeps that interface working
# while the implementation is Python.
#   agent-presence.sh on|off|gate|request-screen|stop-requested [label] [agent]
#   agent-presence.sh resume
exec python3 "$HOME/stayturgid_agent_presence.py" "$@"
