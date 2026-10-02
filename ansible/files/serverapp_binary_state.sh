#!/usr/bin/env bash
# Report whether a launchd-managed Homebrew serverapp is running the binary
# that is currently linked, or a stale one left behind by a `brew upgrade`.
#
# Usage: serverapp_binary_state.sh <uid> <label> <binary-path>
# Prints exactly one of:
#   current  - running the linked binary, or not running at all (bootstrap's job)
#   stale    - running a different binary than the one linked now
#   unknown  - could not determine; caller should not act on this
#
# Why compare the held-open executable rather than mtimes or versions: a
# poured bottle keeps its build-time mtime, which can predate the running
# process (vector 0.58.0 was built 2026-08-26, installed 2026-10-02), so an
# mtime comparison silently misses real upgrades. Formula-version strings
# aren't comparable either, since not every serverapp reports its version
# over HTTP the same way. The executable a process holds open is the only
# uniform ground truth.
set -uo pipefail

uid="${1:-}"
label="${2:-}"
bin="${3:-}"
[ -n "$uid" ] && [ -n "$label" ] && [ -n "$bin" ] || {
  echo unknown
  exit 0
}

want="$(readlink -f "$bin" 2>/dev/null || true)"
[ -n "$want" ] || {
  echo unknown
  exit 0
}

pid="$(launchctl print "gui/${uid}/${label}" 2>/dev/null |
  awk '/^[[:space:]]*pid = /{print $3; exit}')"
# Not loaded or not running: there is no stale process to replace, and the
# bootstrap task already covers bringing it up.
[ -n "${pid:-}" ] || {
  echo current
  exit 0
}

have="$(lsof -p "$pid" -a -d txt -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
# lsof can come back empty (permissions, process exiting mid-probe). Report
# unknown rather than guessing, so a probe failure never triggers a restart.
[ -n "$have" ] || {
  echo unknown
  exit 0
}

if [ "$have" = "$want" ]; then
  echo current
else
  echo stale
fi
