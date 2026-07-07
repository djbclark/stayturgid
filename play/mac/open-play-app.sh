#!/usr/bin/env bash
# Open an app's Play/Aurora details page on device (manual install fallback).
# Usage: ./open-play-app.sh <p7a|s24|hd8|serial> <package.id>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

SERIAL="$(resolve_adb "${1:?usage: open-play-app.sh <host|serial> <package>}")"
PKG="${2:?usage: open-play-app.sh <host|serial> <package>}"
AURORA="${AURORA_PKG:-com.aurora.store}"

adb -s "$SERIAL" shell am start -a android.intent.action.VIEW \
  -d "market://details?id=${PKG}" \
  -n "${AURORA}/.MainActivity" 2>/dev/null || \
adb -s "$SERIAL" shell am start -a android.intent.action.VIEW \
  -d "market://details?id=${PKG}"

echo "Opened market://details?id=${PKG} on $SERIAL (confirm in Aurora Store)"
