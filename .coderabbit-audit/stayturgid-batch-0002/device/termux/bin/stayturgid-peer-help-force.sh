#!/data/data/com.termux/files/usr/bin/bash
export HOME="${HOME:-/data/data/com.termux/files/home}"
exec python3 "$HOME/.stayturgid/bin/stayturgid_peer_help.py" "$SSH_ORIGINAL_COMMAND"
