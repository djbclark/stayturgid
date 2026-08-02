#!/usr/bin/env bash
# Test orchestrator. Tiers:
#   code    (a) syntax/lint under local interpreters — no device, no network
#   unit    (b) sandboxed unit tests — no device
#   local   = code + unit
#   device  (c) read-only device verification (SSH; add --ansible-check for dry run)
#   all     = code + unit + device
#
# Usage: tests/run.sh [code|unit|local|device|all] [device args...]
set -u
cd "$(dirname "$0")/.." || exit 2

tier="${1:-local}"
shift 2>/dev/null || true
fail=0

run_part() {
  echo "### $1"
  case "$2" in
    *.py) python3 "tests/$2" "${@:3}" || fail=1 ;;
    *) bash "tests/$2" "${@:3}" || fail=1 ;;
  esac
  echo ""
}

case "$tier" in
  code) run_part "tier a: code checks" test-code.sh ;;
  unit) run_part "tier b: unit tests" test-unit.sh ;;
  local)
    run_part "tier a: code checks" test-code.sh
    run_part "tier b: unit tests" test-unit.sh
    ;;
  device) run_part "tier c: device (read-only)" device_tier.py "$@" ;;
  all)
    run_part "tier a: code checks" test-code.sh
    run_part "tier b: unit tests" test-unit.sh
    run_part "tier c: device (read-only)" device_tier.py "$@"
    ;;
  *)
    echo "usage: tests/run.sh [code|unit|local|device|all] [--ansible-check] [host...]" >&2
    exit 2
    ;;
esac

if [ "$fail" -eq 0 ]; then
  echo "RESULT: PASS ($tier)"
else
  echo "RESULT: FAIL ($tier)" >&2
fi
exit "$fail"
