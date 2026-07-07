#!/usr/bin/env bash
# Thin wrapper — logic lives in deploy_termux.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$ROOT/ansible/mac/deploy_termux.py" "$@"
