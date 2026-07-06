#!/usr/bin/env bash
# Resolve stayturgid repo root from any module script depth.
#
# Usage (from a script in e.g. autojs6/mac/foo.sh):
#   source "$(dirname "$0")/../../shared/mac/stayturgid-root.sh"
#   ROOT="$(stayturgid_root "$0")"
#   source "$ROOT/shared/mac/resolve-adb.sh"

stayturgid_root() {
  local script="${1:?usage: stayturgid_root /path/to/calling/script.sh}"
  local dir
  dir="$(cd "$(dirname "$script")" && pwd)"
  while [[ "$dir" != "/" ]]; do
    if [[ -d "$dir/termux" && -d "$dir/shared" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  echo "ERROR: stayturgid repo root not found (walked up from $script)" >&2
  return 1
}
