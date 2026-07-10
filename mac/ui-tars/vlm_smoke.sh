#!/usr/bin/env bash
# Quick stop/start/health QA for UI-TARS launchd agent (no vision inference).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ui_tars_env.sh
source "${SCRIPT_DIR}/ui_tars_env.sh"

PLIST="$(ui_tars_service_plist)"
LABEL="$(ui_tars_service_label)"
DOMAIN="gui/$(id -u)"

fail() {
  echo "vlm-smoke: FAIL — $*" >&2
  exit 1
}

[[ -f "$PLIST" ]] || fail "plist missing — run make vlm-service-install"

echo "==> stop"
launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
sleep +2
ui_tars_healthy && fail "still healthy after bootout"

echo "==> start"
launchctl bootstrap "$DOMAIN" "$PLIST"
for _ in $(seq 1 120); do
  ui_tars_healthy && break
  sleep 1
done
ui_tars_healthy || fail "not healthy after bootstrap — see $(ui_tars_log_file)"

echo "==> launchctl"
launchctl print "$DOMAIN/$LABEL" 2>&1 | grep -E 'state = running|program =' | head -3

echo "==> client"
python3 "${SCRIPT_DIR}/../vlm_check.py"

echo "vlm-smoke: OK"
