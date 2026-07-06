#!/data/data/com.termux/files/usr/bin/bash
# Optional: notify when GitHub version.json is newer than the last seen version.
# Deploy to ~/check-repo-version.sh; run from cron or manually after git pull on Mac.
#
# stayturgid no longer uses Tasker for auto-update — use Ansible deploy or pull termux scripts via SSH.
set -euo pipefail

export PATH=/data/data/com.termux/files/usr/bin:$PATH

URL="https://raw.githubusercontent.com/djbclark/stayturgid/master/version.json"
STAMP="$HOME/.stayturgid_repo_version"
CHANNEL="stayturgid"

json="$(curl -fsSL "$URL")" || exit 0
remote="$(printf '%s' "$json" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[ -n "$remote" ] || exit 0

local=""
[ -f "$STAMP" ] && local="$(cat "$STAMP")"

if [ "$remote" = "$local" ]; then
  exit 0
fi

changelog="$(printf '%s' "$json" | sed -n 's/.*"changelog"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
termux-notification \
  --id stayturgid-update \
  --title "stayturgid $remote on GitHub" \
  --content "${changelog:-Run ansible/mac/deploy-termux.sh from your Mac}" \
  --priority high \
  --button "OK" 2>/dev/null || true

echo "$remote" > "$STAMP"
