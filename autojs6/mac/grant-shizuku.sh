#!/usr/bin/env bash
# Sync Shizuku authorized-app list for stayturgid automation mode.
#
# Shizuku tracks clients in /data/local/tmp/shizuku/shizuku.json (uid + flags).
# The manager UI reads that file — pm grant alone is not always enough.
#
# Usage:
#   ./grant-shizuku.sh <p7a|s24|serial> autojs6   # allow AutoJs6, deny Tasker
#   ./grant-shizuku.sh <p7a|s24|serial> tasker    # allow Tasker, deny AutoJs6
#
# Requires: Shizuku running, privileged shell on localhost:5555 (or USB adb shell).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

ALIAS="${1:?usage: grant-shizuku.sh <p7a|s24|serial> <autojs6|tasker>}"
TARGET="$(resolve_adb "$ALIAS")"
MODE="${2:?usage: grant-shizuku.sh <p7a|s24|serial> <autojs6|tasker>}"

AUTOJS_PKG="org.autojs.autojs6"
TASKER_PKG="net.dinglisch.android.taskerm"
SHIZUKU_PERM="moe.shizuku.manager.permission.API_V23"
SHIZUKU_JSON="/data/local/tmp/shizuku/shizuku.json"
FLAG_ALLOW=2
FLAG_DENY=4

case "$MODE" in
  autojs6|tasker) ;;
  *) echo "mode must be autojs6 or tasker" >&2; exit 1 ;;
esac

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
TASKER_UID="$(uid_for "$TASKER_PKG")"

if [[ -z "$AUTOJS_UID" || -z "$TASKER_UID" ]]; then
  echo "ERROR: could not resolve UIDs (autojs=$AUTOJS_UID tasker=$TASKER_UID)" >&2
  exit 1
fi

if [[ "$MODE" == "autojs6" ]]; then
  ALLOW_UID="$AUTOJS_UID"; ALLOW_PKGS="[\"$AUTOJS_PKG\"]"
  DENY_UID="$TASKER_UID";  DENY_PKGS="[\"$TASKER_PKG\"]"
  sh_shell "pm grant $AUTOJS_PKG $SHIZUKU_PERM" 2>/dev/null || true
  sh_shell "pm revoke $TASKER_PKG $SHIZUKU_PERM" 2>/dev/null || true
else
  ALLOW_UID="$TASKER_UID"; ALLOW_PKGS="[\"$TASKER_PKG\"]"
  DENY_UID="$AUTOJS_UID";  DENY_PKGS="[\"$AUTOJS_PKG\"]"
  sh_shell "pm grant $TASKER_PKG $SHIZUKU_PERM" 2>/dev/null || true
  sh_shell "pm revoke $AUTOJS_PKG $SHIZUKU_PERM" 2>/dev/null || true
fi

CURRENT="$(sh_shell "cat $SHIZUKU_JSON" 2>/dev/null | tr -d '\r' || true)"
if [[ -z "$CURRENT" ]]; then
  echo "WARN: could not read $SHIZUKU_JSON — merging into empty package list only" >&2
fi
TMP_JSON="$(mktemp)"
printf '%s' "$CURRENT" > "$TMP_JSON"
PATCH_JSON="$(python3 - "$TMP_JSON" "$ALLOW_UID" "$ALLOW_PKGS" "$DENY_UID" "$DENY_PKGS" <<'PY'
import json, sys
path, allow_uid, allow_pkgs, deny_uid, deny_pkgs = sys.argv[1:6]
allow_uid, deny_uid = int(allow_uid), int(deny_uid)
allow_pkgs = json.loads(allow_pkgs)
deny_pkgs = json.loads(deny_pkgs)
try:
    raw = open(path).read().strip()
    data = json.loads(raw) if raw else {"version": 2, "packages": []}
except (OSError, json.JSONDecodeError):
    data = {"version": 2, "packages": []}
pkgs = [e for e in data.get("packages", [])
        if e.get("uid") not in (allow_uid, deny_uid)]
pkgs.append({"uid": allow_uid, "flags": 2, "packages": allow_pkgs})
pkgs.append({"uid": deny_uid, "flags": 4, "packages": deny_pkgs})
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
echo "Shizuku config updated for mode=$MODE on $TARGET"
echo "  allow uid=$ALLOW_UID packages=$ALLOW_PKGS"
echo "  deny  uid=$DENY_UID packages=$DENY_PKGS"
sh_shell "cat $SHIZUKU_JSON"
