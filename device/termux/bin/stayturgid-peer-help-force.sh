#!/data/data/com.termux/files/usr/bin/bash
# Restricted SSH ForceCommand wrapper for peer help (helpers: s24/p7a).
# authorized_keys: command="…/stayturgid-peer-help-force.sh",restrict …
set -euo pipefail
export PATH="${PREFIX:-/data/data/com.termux/files/usr}/bin:$PATH"
HOME="${HOME:-/data/data/com.termux/files/home}"
HELP="$HOME/.stayturgid/bin/stayturgid_peer_help.py"
# SSH_ORIGINAL_COMMAND should look like:
#   stayturgid_peer_help.py handsets-start --target IP:5555 --port 9008
# or the same without the script name.
raw="${SSH_ORIGINAL_COMMAND:-}"
if [ -z "$raw" ]; then
  echo "denied: empty command" >&2
  exit 1
fi
# shellcheck disable=SC2086
set -- $raw
# Drop leading interpreter / script path tokens
while [ $# -gt 0 ]; do
  case "$1" in
    python3|python|*/stayturgid_peer_help.py|stayturgid_peer_help.py)
      shift
      ;;
    *)
      break
      ;;
  esac
done
verb="${1:-}"
case "$verb" in
  handsets-start|shizuku-start|ping|status) ;;
  *)
    echo "denied: verb=$verb" >&2
    exit 1
    ;;
esac
exec python3 "$HELP" "$@"
