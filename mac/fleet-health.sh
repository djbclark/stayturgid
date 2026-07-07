#!/usr/bin/env bash
# Fleet health = the TAP device tier plus the on-device self-heal.
# Thin wrapper kept for muscle memory; the implementation lives in
# tests/device_tier.py (single verification path).
#
# Usage:
#   ./mac/fleet-health.sh           # every device in devices.conf
#   ./mac/fleet-health.sh s24
set -euo pipefail
exec bash "$(cd "$(dirname "$0")/.." && pwd)/tests/run.sh" device --heal "$@"
