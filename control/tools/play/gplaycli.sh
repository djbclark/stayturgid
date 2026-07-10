#!/usr/bin/env bash
# Back-compat shim — prefer control/tools/play/gplaycli.py directly.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
exec python3 "$ROOT/control/tools/play/gplaycli.py" "$@"
