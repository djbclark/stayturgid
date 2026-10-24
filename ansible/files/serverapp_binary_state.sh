#!/usr/bin/env bash
export PATH="/opt/homebrew/bin:$PATH"
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

want="$(greadlink -f "$bin" 2>/dev/null || true)"
[ -n "$want" ] || {
  echo unknown
  exit 0
}

pid="$(launchctl print "gui/${uid}/${label}" 2>/dev/null |
  gawk '/^[[:space:]]*pid = /{print $3; exit}')"
# Not loaded or not running: there is no stale process to replace, and the
# bootstrap task already covers bringing it up.
[ -n "${pid:-}" ] || {
  echo current
  exit 0
}

# First txt entry = the executable: its inode (i) and path (n) as held open.
held="$(lsof -p "$pid" -a -d txt -Fin 2>/dev/null | gsed -n '/^ftxt/,/^n/p' | ghead -3)"
have="$(printf '%s\n' "$held" | gsed -n 's/^n//p' | ghead -1)"
have_ino="$(printf '%s\n' "$held" | gsed -n 's/^i//p' | ghead -1)"
# lsof can come back empty (permissions, process exiting mid-probe). Report
# unknown rather than guessing, so a probe failure never triggers a restart.
[ -n "$have" ] && [ -n "$have_ino" ] || {
  echo unknown
  exit 0
}
want_ino="$(gstat -L -c %i "$want" 2>/dev/null || true)"

# Path alone misses a binary replaced in place (the tarball serverapps install
# over the same path: openobserve ran a replaced 1.0.4 inode after 1.1.2 was
# installed, 2026-10-24), so the inode must match too.
if [ "$have" = "$want" ] && [ "$have_ino" = "$want_ino" ]; then
  echo current
else
  echo stale
fi
