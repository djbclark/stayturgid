#!/usr/bin/env bash
# Thin wrapper — logic lives in deploy_fleet.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/mac/deploy_fleet.py" "$@"
