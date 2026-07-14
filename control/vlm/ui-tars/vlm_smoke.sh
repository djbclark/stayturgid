#!/usr/bin/env bash
# Quick stop/start/health QA for UI-TARS launchd agent (no vision inference).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Inline env helper (replaces ui_tars_env.sh)
_env() { python3 "${SCRIPT_DIR}/ui_tars_env.py" --get "$1"; }

PLIST="$(_env SERVICE_PLIST)"
LABEL="$(_env SERVICE_LABEL)"
DOMAIN="gui/$(id -u)"

fail() {
  echo "vlm-smoke: FAIL — $*" >&2
  exit 1
}

[[ -f "$PLIST" ]] || fail "plist missing — run just vlm-service-install"

echo "==> stop"
launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
sleep 2
curl -sf -o /dev/null http://127.0.0.1:${PORT}/health && fail "still healthy after bootout"

echo "==> start"
launchctl bootstrap "$DOMAIN" "$PLIST"
for _ in $(seq 1 120); do
  curl -sf -o /dev/null http://127.0.0.1:${PORT}/health && break
  sleep 1
done
curl -sf -o /dev/null http://127.0.0.1:${PORT}/health || fail "not healthy after bootstrap — see $(_env LOG_FILE)"

echo "==> launchctl"
launchctl print "$DOMAIN/$LABEL" 2>&1 | grep -E 'state = running|program =' | head -3

echo "==> client"
python3 "${SCRIPT_DIR}/../vlm_check.py"

echo "vlm-smoke: OK"
