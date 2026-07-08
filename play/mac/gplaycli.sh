#!/usr/bin/env bash
# Back-compat shim — prefer play/mac/gplaycli.py directly.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$ROOT/play/mac/gplaycli.py" "$@"
