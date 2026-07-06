#!/usr/bin/env bash
# Grant Shizuku API access to AutoJs6 (stayturgid watchdog).
#
# Does not revoke or configure Tasker — other apps may still use Shizuku.
#
# Usage: ./grant-shizuku.sh <p7a|s24|serial>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

ALIAS="${1:?usage: grant-shizuku.sh <p7a|s24|serial>}"
TARGET="$(resolve_adb "$ALIAS")"

AUTOJS_PKG="org.autojs.autojs6"
SHIZUKU_PERM="moe.shizuku.manager.permission.API_V23"
SHIZUKU_JSON="/data/local/tmp/shizuku/shizuku.json"
FLAG_ALLOW=2

ssh_host=""
case "$ALIAS" in
  p7a|s24) ssh_host="$ALIAS" ;;
esac

sh_shell() {
  local cmd="$1"
  if [[ -n "$ssh_host" ]]; then
    ssh -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR "$ssh_host" \
      "adb -s localhost:5555 shell $(printf '%q' "$cmd")"
    return $?
  fi
  adb -s "$TARGET" shell "$cmd"
}

uid_for() {
  local pkg="$1"
  sh_shell "pm list packages -U $pkg" 2>/dev/null \
    | sed -n 's/.*uid:\([0-9]*\).*/\1/p' | head -1
}

AUTOJS_UID="$(uid_for "$AUTOJS_PKG")"
if [[ -z "$AUTOJS_UID" ]]; then
  echo "ERROR: could not resolve AutoJs6 uid" >&2
  exit 1
fi

sh_shell "pm grant $AUTOJS_PKG $SHIZUKU_PERM" 2>/dev/null || true

CURRENT="$(sh_shell "cat $SHIZUKU_JSON" 2>/dev/null | tr -d '\r' || true)"
TMP_JSON="$(mktemp)"
printf '%s' "$CURRENT" > "$TMP_JSON"
PATCH_JSON="$(python3 - "$TMP_JSON" "$AUTOJS_UID" "$AUTOJS_PKG" <<'PY'
import json, sys
path, allow_uid, pkg = sys.argv[1:4]
allow_uid = int(allow_uid)
try:
    raw = open(path).read().strip()
    data = json.loads(raw) if raw else {"version": 2, "packages": []}
except (OSError, json.JSONDecodeError):
    data = {"version": 2, "packages": []}
pkgs = [e for e in data.get("packages", []) if e.get("uid") != allow_uid]
pkgs.append({"uid": allow_uid, "flags": 2, "packages": [pkg]})
data["packages"] = pkgs
print(json.dumps(data, separators=(",", ":")))
PY
)"
rm -f "$TMP_JSON"

TMP="$(mktemp)"
printf '%s' "$PATCH_JSON" > "$TMP"
adb -s "$TARGET" push "$TMP" /sdcard/Download/shizuku.json >/dev/null
rm -f "$TMP"

sh_shell "cp /sdcard/Download/shizuku.json $SHIZUKU_JSON && chmod 666 $SHIZUKU_JSON"
echo "Shizuku: allowed AutoJs6 (uid=$AUTOJS_UID) on $TARGET"
