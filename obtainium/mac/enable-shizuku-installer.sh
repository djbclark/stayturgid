#!/usr/bin/env bash
# Enable Obtainium's Shizuku/Dhizuku/Sui installer for quieter APK updates.
#
# 1. pm grant API_V23 (Obtainium must be allowed in Shizuku manager)
# 2. Ensure Obtainium uid is in /data/local/tmp/shizuku/shizuku.json (flags=2)
# 3. Toggle "Use Dhizuku, Shizuku or Sui to install" in Obtainium settings UI
#
# Usage: ./enable-shizuku-installer.sh <p7a|s24|serial>
#
# Requires: unlocked screen, Shizuku running, privileged shell on localhost:5555.
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../../shared/mac/resolve-adb.sh
source "$REPO_ROOT/shared/mac/resolve-adb.sh"

ALIAS="${1:?usage: enable-shizuku-installer.sh <p7a|s24|serial>}"
TARGET="$(resolve_adb "$ALIAS")"

OBTAINIUM_PKG="dev.imranr.obtainium"
SHIZUKU_PERM="moe.shizuku.manager.permission.API_V23"
SHIZUKU_JSON="/data/local/tmp/shizuku/shizuku.json"

ssh_host="$(resolve_ssh_host "$ALIAS")"

# Remote commands travel on stdin to an explicit bash — never the login
# shell (Termux users may run fish/zsh, and %q quoting is bash-specific).
sh_shell() {
  local cmd="$1"
  if [[ -n "$ssh_host" ]]; then
    printf 'adb -s localhost:5555 shell %q\n' "$cmd" | \
      ssh -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR "$ssh_host" "bash -s"
    return $?
  fi
  adb -s "$TARGET" shell "$cmd"
}

dev_adb() {
  if [[ -n "$ssh_host" ]]; then
    printf 'adb -s localhost:5555 %s\n' "$*" | \
      ssh -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR "$ssh_host" "bash -s"
    return $?
  fi
  adb -s "$TARGET" "$@"
}

uid_for() {
  local pkg="$1"
  sh_shell "pm list packages -U $pkg" 2>/dev/null \
    | sed -n 's/.*uid:\([0-9]*\).*/\1/p' | head -1
}

OBT_UID="$(uid_for "$OBTAINIUM_PKG")"
if [[ -z "$OBT_UID" ]]; then
  echo "ERROR: Obtainium not installed on $TARGET" >&2
  exit 1
fi

echo "Granting Shizuku API to $OBTAINIUM_PKG (uid=$OBT_UID)..."
sh_shell "pm grant $OBTAINIUM_PKG $SHIZUKU_PERM" 2>/dev/null || true

# Distinguish "file missing" (fresh config OK) from "read failed" (abort):
# patching from an empty read would rewrite shizuku.json with ONLY this app,
# revoking every other authorized app.
if ! sh_shell "true" >/dev/null 2>&1; then
  echo "ERROR: no privileged shell on localhost:5555 — aborting before touching $SHIZUKU_JSON" >&2
  exit 1
fi
if sh_shell "test -f $SHIZUKU_JSON" >/dev/null 2>&1; then
  CURRENT="$(sh_shell "cat $SHIZUKU_JSON" 2>/dev/null | tr -d '\r')"
  if [[ -z "$CURRENT" ]]; then
    echo "ERROR: $SHIZUKU_JSON exists but read came back empty — aborting to avoid clobbering" >&2
    exit 1
  fi
else
  CURRENT=""
fi
TMP_JSON="$(mktemp)"
printf '%s' "$CURRENT" > "$TMP_JSON"
PATCH_JSON="$(python3 - "$TMP_JSON" "$OBT_UID" "$OBTAINIUM_PKG" <<'PY'
import json, sys
path, uid_s, pkg = sys.argv[1:4]
uid = int(uid_s)
try:
    raw = open(path).read().strip()
    data = json.loads(raw) if raw else {"version": 2, "packages": []}
except (OSError, json.JSONDecodeError):
    data = {"version": 2, "packages": []}
pkgs = [e for e in data.get("packages", []) if e.get("uid") != uid]
pkgs.append({"uid": uid, "flags": 2, "packages": [pkg]})
data["packages"] = pkgs
print(json.dumps(data, separators=(",", ":")))
PY
)"
rm -f "$TMP_JSON"

TMP="$(mktemp)"
printf '%s' "$PATCH_JSON" > "$TMP"
adb -s "$TARGET" push "$TMP" /sdcard/Download/shizuku-obtainium.json >/dev/null
rm -f "$TMP"
sh_shell "cp /sdcard/Download/shizuku-obtainium.json $SHIZUKU_JSON && chmod 666 $SHIZUKU_JSON"

echo "Opening Obtainium settings to enable Shizuku installer..."
sh_shell "input keyevent KEYCODE_WAKEUP"
sleep 1
sh_shell "am start -n ${OBTAINIUM_PKG}/.MainActivity"
sleep 2
sh_shell "input tap 945 2196"
sleep 2

# Scroll to top, then walk down until the Installation row is visible.
for _ in 1 2 3 4 5 6; do
  sh_shell "input swipe 540 400 540 1600 350" 2>/dev/null || true
  sleep 0.4
done

FOUND=0
for _ in $(seq 1 12); do
  sh_shell "uiautomator dump /sdcard/obtainium_shizuku.xml" 2>/dev/null || true
  XML="$(sh_shell "cat /sdcard/obtainium_shizuku.xml" 2>/dev/null || true)"
  if echo "$XML" | grep -q 'Use Dhizuku, Shizuku or Sui to install'; then
    FOUND=1
    break
  fi
  sh_shell "input swipe 540 1600 540 400 350" 2>/dev/null || true
  sleep 0.6
done

if [[ "$FOUND" -ne 1 ]]; then
  echo "WARN: Shizuku installer row not found — scroll settings manually." >&2
  exit 1
fi

SWITCH="$(echo "$XML" | tr '>' '\n' | grep -A1 'Use Dhizuku, Shizuku or Sui to install' \
  | grep 'android.widget.Switch' | head -1 \
  | sed -n 's/.*checked="\([^"]*\)".*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4 \5/p')"
read -r checked x1 y1 x2 y2 <<< "$SWITCH"
if [[ "$checked" == "true" ]]; then
  echo "Shizuku installer already enabled in Obtainium UI."
elif [[ -n "$x1" ]]; then
  sh_shell "input tap $(( (x1+x2)/2 )) $(( (y1+y2)/2 ))"
  sleep 2
  echo "Tapped Shizuku installer switch."
else
  sh_shell "input tap 959 1266"
  sleep 2
  echo "Tapped Shizuku installer switch (fallback coords)."
fi

# Shizuku may prompt "Allow Obtainium to access Shizuku?" — approve if shown.
sh_shell "uiautomator dump /sdcard/obtainium_shizuku_perm.xml" 2>/dev/null || true
PERM_XML="$(sh_shell "cat /sdcard/obtainium_shizuku_perm.xml" 2>/dev/null || true)"
if echo "$PERM_XML" | grep -q 'Allow Obtainium to access Shizuku'; then
  BTN="$(echo "$PERM_XML" | tr '>' '\n' | grep 'android:id/button1' | head -1 \
    | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p')"
  read -r px1 py1 px2 py2 <<< "$BTN"
  if [[ -n "$px1" ]]; then
    sh_shell "input tap $(( (px1+px2)/2 )) $(( (py1+py2)/2 ))"
  else
    sh_shell "input tap 540 1284"
  fi
  sleep 1
  echo "Approved Shizuku permission dialog for Obtainium."
fi

sh_shell "input keyevent KEYCODE_HOME"
echo "Done. Obtainium should use Shizuku for installs (fewer dialogs)."
