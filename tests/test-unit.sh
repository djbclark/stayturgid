#!/usr/bin/env bash
# Tier (b): device-free unit tests. Termux scripts run in a sandbox with
# stubbed termux-*/adb/pgrep/flock commands (see tests/lib.sh); AutoJs6 log
# parsing runs under node with a files{} shim; termux_pkg runs through
# `ansible localhost` against a fake Termux prefix.
#
# Most cases are regressions for CODE-REVIEW.md findings (noted inline).
set -u
cd "$(dirname "$0")/.." || exit 2
. tests/lib.sh
REPO="$PWD"

make_sandbox
trap 'kill_sandbox_pid "$SANDBOX/home/.stayturgid/run/bootloop.pid" 2>/dev/null || true
      kill_sandbox_pid "$SANDBOX/home/.stayturgid/run/bridge.pid" 2>/dev/null || true
      rm -rf "$SANDBOX"' EXIT

# ===========================================================================
# stayturgid-battery-alarm.sh
# ===========================================================================
# Same suite runs against the shell implementation and its Python twin —
# parity gate for the ongoing bash->python migration (Ansible best practice:
# Python beyond trivial wrappers). Shell stays deployed until parity soaks.
battery_suite() {
  local BATT="$1" T="$2"
  # M2 regression: first run at 12% fires ONE alert (lowest tier), marks all
  reset_sandbox
  echo '{"percentage": 12, "status": "DISCHARGING"}' >"$SANDBOX/batt.json"
  run_sandboxed "$BATT"
  tap_is "$RC" 0 "battery[$T]: run at 12% exits 0"
  tap_is "$(stub_calls 'termux-notification ')" 1 "battery[$T]: single alert at 12% (no tier cascade)"
  tap_is "$(sort -n "$SANDBOX/home/.stayturgid/state/batt_alerted" | tr '\n' ' ')" "15 20 25 30 " \
    "battery[$T]: tiers 30/25/20/15 all marked alerted"
  tap_like "$OUT$(grep termux-toast "$STUB_LOG")" "tier 15" "battery[$T]: alert names lowest tier (15)"

  # idempotent rerun
  run_sandboxed "$BATT"
  tap_is "$(stub_calls 'termux-notification ')" 1 "battery[$T]: rerun at same pct fires nothing new"

  # drop to 9% fires exactly the next tier
  echo '{"percentage": 9, "status": "DISCHARGING"}' >"$SANDBOX/batt.json"
  run_sandboxed "$BATT"
  tap_is "$(stub_calls 'termux-notification ')" 2 "battery[$T]: drop to 9% fires exactly one more alert"

  # M1 regression: no valid wallpaper backup => zero wallpaper writes
  tap_is "$(stub_calls 'termux-wallpaper')" 0 "battery[$T]: wallpaper untouched without verified backup"

  # charging clears state and removes the notification
  echo '{"percentage": 50, "status": "CHARGING"}' >"$SANDBOX/batt.json"
  run_sandboxed "$BATT"
  if [ ! -f "$SANDBOX/home/.stayturgid/state/batt_alerted" ]; then
    tap_ok "battery[$T]: charging clears alert state"
  else
    tap_fail "battery[$T]: charging clears alert state"
  fi
  tap_like "$(cat "$STUB_LOG")" "termux-notification-remove stayturgid-batt" \
    "battery[$T]: charging removes the notification"

  # M3 regression: battery JSON without percentage => clean exit 0 (guard, not set -e)
  reset_sandbox
  echo '{"status": "DISCHARGING"}' >"$SANDBOX/batt.json"
  run_sandboxed "$BATT"
  tap_is "$RC" 0 "battery[$T]: malformed battery JSON exits 0 via guard"

  # valid backup => wallpaper blink used AND restored from backup afterwards
  reset_sandbox
  printf '\x89PNG\r\n\x1a\nfakepixels' >"$SANDBOX/wall.png"
  export ADB_WALLPAPER_FILE="$SANDBOX/wall.png"
  mkdir -p "$SANDBOX/home/.stayturgid/battery-colors"
  for c in purple blue green yellow orange red black; do
    : >"$SANDBOX/home/.stayturgid/battery-colors/$c.png"
  done
  echo '{"percentage": 28, "status": "DISCHARGING"}' >"$SANDBOX/batt.json"
  run_sandboxed "$BATT"
  unset ADB_WALLPAPER_FILE
  if [ "$(stub_calls 'termux-wallpaper')" -gt 0 ]; then
    tap_ok "battery[$T]: wallpaper blink runs with verified backup"
  else
    tap_fail "battery[$T]: wallpaper blink runs with verified backup"
  fi
  tap_like "$(grep termux-wallpaper "$STUB_LOG" | tail -1)" "wallpaper-backup.png" \
    "battery[$T]: last wallpaper write restores the backup"

  # quiet mode (DND): no toast/vibrate, silent notification, single torch flash
  reset_sandbox
  export ADB_ZEN=1
  echo '{"percentage": 12, "status": "DISCHARGING"}' >"$SANDBOX/batt.json"
  run_sandboxed "$BATT"
  unset ADB_ZEN
  tap_is "$(stub_calls 'termux-toast')" 0 "battery[$T]: DND fires no toast"
  tap_is "$(stub_calls 'termux-vibrate')" 0 "battery[$T]: DND fires no vibrate"
  tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "quiet hours" "battery[$T]: DND posts silent notification"
  tap_is "$(stub_calls 'termux-torch on')" 1 "battery[$T]: DND single quick torch flash (tier<=15)"
}

# stayturgid-battery-alarm migrated to Python (shell retired).
battery_suite device/termux/py/stayturgid_battery_alarm.py py

# ===========================================================================
# stayturgid_repair.py
# ===========================================================================
# Same suite runs against the shell implementation and its Python twin.
repair_suite() {
  local RSCRIPT="$1" T="$2"
  unset PGREP_RC FLOCK_RC ADB_A11Y ADB_SHELL_UID 2>/dev/null || true
  # healthy path
  reset_sandbox
  export PGREP_RC=0
  run_sandboxed "$RSCRIPT"
  tap_is "$RC" 0 "repair[$T]: healthy => exit 0"
  _RSTATUS="$(cat "$SANDBOX/home/.stayturgid/run/repair.status" 2>/dev/null || echo "$OUT")"
  tap_like "$_RSTATUS" "STATUS port=open shizuku=up sshd=up a11y=up shell=yes wifi=up" "repair[$T]: healthy STATUS line"

  # Android 16 can report cosmetic toggle=0 while the UID-2000 shell is live.
  reset_sandbox
  export PGREP_RC=0 ADB_WIFI=0
  run_sandboxed "$RSCRIPT"
  unset ADB_WIFI
  _RSTATUS="$(cat "$SANDBOX/home/.stayturgid/run/repair.status" 2>/dev/null || echo "$OUT")"
  tap_like "$_RSTATUS" "wifi=up" "repair[$T]: cosmetic wifi=0 with live shell => healthy"
  tap_unlike "$(cat "$STUB_LOG")" "settings put global adb_wifi_enabled" \
    "repair[$T]: live shell avoids an ineffective Android 16 toggle write"

  # a11y: detection-only — no longer auto-repairs, reports status
  reset_sandbox
  export PGREP_RC=0 ADB_A11Y="com.other.app/.TheirService"
  run_sandboxed "$RSCRIPT"
  _RSTATUS="$(cat "$SANDBOX/home/.stayturgid/run/repair.status" 2>/dev/null || echo "$OUT")"
  tap_like "$_RSTATUS" "a11y=down" "repair[$T]: disabled accessibility => down (detection only)"
  # Check the repair log for the ACTION_REQUIRED message (not stdout)
  tap_like "$(cat "$SANDBOX/home/.stayturgid/logs/repair.log" 2>/dev/null)" \
    "ACTION_REQUIRED" "repair[$T]: logs ACTION_REQUIRED when a11y disabled"
  # a11y list is NOT modified — detection-only, no settings put
  if [ -f "$SANDBOX/a11y_state" ]; then
    tap_fail "repair[$T]: a11y list should NOT be modified (detection-only)"
  else
    tap_ok "repair[$T]: a11y list preserved (no auto-write)"
  fi

  # sshd down => restarted via sshd stub
  reset_sandbox
  export PGREP_RC=1
  run_sandboxed "$RSCRIPT"
  tap_is "$RC" 0 "repair[$T]: sshd down => restarted, exit 0"
  _RSTATUS="$(cat "$SANDBOX/home/.stayturgid/run/repair.status" 2>/dev/null || echo "$OUT")"
  tap_like "$_RSTATUS" "sshd=restarted" "repair[$T]: STATUS reports sshd=restarted"

  # 5555 dead (shell uid probe fails) => CLOSED_NO_SHELL, exit 1
  reset_sandbox
  export PGREP_RC=0 ADB_SHELL_UID=""
  run_sandboxed "$RSCRIPT"
  unset ADB_SHELL_UID
  tap_is "$RC" 1 "repair[$T]: no privileged shell => exit 1"
  _RSTATUS="$(cat "$SANDBOX/home/.stayturgid/run/repair.status" 2>/dev/null || echo "$OUT")"
  tap_like "$_RSTATUS" "port=CLOSED_NO_SHELL" "repair[$T]: STATUS reports CLOSED_NO_SHELL"

  # Fire OS / split-storage: localhost:5555 not expected — sshd-only heal, exit 0
  reset_sandbox
  export PGREP_RC=0 ADB_SHELL_UID=""
  mkdir -p "$SANDBOX/sd/state"
  printf '%s\n' '{"privilegedShellExpected":false}' >"$SANDBOX/sd/state/device.json"
  export STAYTURGID_SD="$SANDBOX/sd"
  run_sandboxed "$RSCRIPT"
  unset ADB_SHELL_UID STAYTURGID_SD
  _RSTATUS="$(cat "$SANDBOX/home/.stayturgid/run/repair.status" 2>/dev/null || echo "$OUT")"
  tap_is "$RC" 0 "repair[$T]: Fire OS skip privileged shell => exit 0"
  tap_like "$_RSTATUS" "port=skip" "repair[$T]: STATUS reports port=skip"
  tap_unlike "$_RSTATUS" "CLOSED_NO_SHELL" "repair[$T]: Fire OS does not log CLOSED_NO_SHELL"

  # H1 regression: lock-contention branch must resolve its helpers
  reset_sandbox
  export PGREP_RC=0 FLOCK_RC=1
  run_sandboxed "$RSCRIPT"
  unset FLOCK_RC
  tap_is "$RC" 0 "repair[$T]: duplicate invocation exits 0 (advisory)"
  _RSTATUS="$(cat "$SANDBOX/home/.stayturgid/run/repair.status" 2>/dev/null || echo "$OUT")"
  tap_like "$_RSTATUS" "sshd=up" "repair[$T]: duplicate branch reports real sshd state (H1)"
  tap_unlike "$ERR" "command not found" "repair[$T]: duplicate branch has no unresolved functions (H1)"

  # M8 regression: oversized log gets trimmed
  reset_sandbox
  export PGREP_RC=0
  mkdir -p "$SANDBOX/home/.stayturgid/logs"
  seq 1 1500 | sed 's/^/line /' >"$SANDBOX/home/.stayturgid/logs/repair.log"
  run_sandboxed "$RSCRIPT"
  lines=$(wc -l <"$SANDBOX/home/.stayturgid/logs/repair.log" | tr -d ' ')
  if [ "$lines" -le 510 ]; then
    tap_ok "repair[$T]: 1500-line log trimmed to <=510 ($lines)"
  else
    tap_fail "repair[$T]: 1500-line log trimmed to <=510" "got $lines lines"
  fi
  unset PGREP_RC
  unset PGREP_RC FLOCK_RC ADB_A11Y ADB_SHELL_UID 2>/dev/null || true
}

# stayturgid-repair migrated to Python (stayturgid_repair.py is now a compat shim).
repair_suite device/termux/py/stayturgid_repair.py py

# ===========================================================================
# stayturgid_agent_presence.py gate
# ===========================================================================
# Same suite runs against the shell implementation and its Python twin.
presence_suite() {
  local PRES="$1" T="$2"
  unset ADB_FG_PKG ADB_WAKE DIALOG_CHOICE 2>/dev/null || true
  # idle foreground (Samsung launcher) => proceed, no dialog
  reset_sandbox
  run_sandboxed "$PRES" gate
  tap_is "$RC" 0 "presence[$T]: idle launcher foreground => proceed"
  tap_is "$(stub_calls 'termux-dialog')" 0 "presence[$T]: no dialog when idle"

  # M5 regression: Pixel launcher counts as idle
  reset_sandbox
  export ADB_FG_PKG=com.google.android.apps.nexuslauncher
  run_sandboxed "$PRES" gate
  tap_is "$RC" 0 "presence[$T]: Pixel launcher foreground => proceed (M5)"

  # screen off => proceed without dialog
  reset_sandbox
  export ADB_FG_PKG=com.android.chrome ADB_WAKE=Asleep
  run_sandboxed "$PRES" gate
  tap_is "$RC" 0 "presence[$T]: screen not interactive => proceed"
  unset ADB_WAKE

  # M4 regression: active use + dialog timeout => fail closed (75 + later file)
  reset_sandbox
  export ADB_FG_PKG=com.android.chrome DIALOG_CHOICE=""
  run_sandboxed "$PRES" gate
  tap_is "$RC" 75 "presence[$T]: dialog timeout fails closed with 75 (M4)"
  if [ -f "$SANDBOX/sd/state/presence_check_after" ]; then
    tap_ok "presence[$T]: timeout arms 10-minute recheck"
  else
    tap_fail "presence[$T]: timeout arms 10-minute recheck"
  fi

  # explicit Continue => proceed
  reset_sandbox
  export DIALOG_CHOICE="Continue"
  run_sandboxed "$PRES" gate
  tap_is "$RC" 0 "presence[$T]: explicit Continue => proceed"

  # Pause => 75 now, 75 on next gate, cleared by resume
  reset_sandbox
  export DIALOG_CHOICE="Pause"
  run_sandboxed "$PRES" gate
  tap_is "$RC" 75 "presence[$T]: Pause => 75"
  export DIALOG_CHOICE="Continue" # must NOT be consulted while paused
  run_sandboxed "$PRES" gate
  tap_is "$RC" 75 "presence[$T]: paused gate stays closed without dialog"
  run_sandboxed "$PRES" resume
  run_sandboxed "$PRES" gate
  tap_is "$RC" 0 "presence[$T]: resume clears pause"
  unset DIALOG_CHOICE ADB_FG_PKG

  # usage error => exit 2
  run_sandboxed "$PRES" bogus-action
  tap_is "$RC" 2 "presence[$T]: unknown action => usage exit 2"

  # --- screen-control sharing flow -------------------------------------------
  # request-screen: Disallow => 75; Yes or 10s timeout => 0
  reset_sandbox
  export DIALOG_CHOICE="no"
  run_sandboxed "$PRES" request-screen
  tap_is "$RC" 75 "presence[$T]: request-screen Disallow => 75"
  export DIALOG_CHOICE="yes"
  run_sandboxed "$PRES" request-screen
  tap_is "$RC" 0 "presence[$T]: request-screen Yes => proceed"
  export DIALOG_CHOICE=""
  run_sandboxed "$PRES" request-screen
  tap_is "$RC" 0 "presence[$T]: request-screen 10s timeout => proceed"
  unset DIALOG_CHOICE

  # on posts the running notification with a Graceful stop button
  reset_sandbox
  run_sandboxed "$PRES" on "TestPhone" "TestAgent"
  tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "Graceful stop" \
    "presence[$T]: running notification carries Graceful stop button"

  # stop-requested: 1 before the button, 0 after
  run_sandboxed "$PRES" stop-requested
  tap_is "$RC" 1 "presence[$T]: no stop requested initially"
  mkdir -p "$SANDBOX/sd/state"
  touch "$SANDBOX/sd/state/stop_requested"
  run_sandboxed "$PRES" stop-requested
  tap_is "$RC" 0 "presence[$T]: stop-requested detects the flag"

  # off after a stop: clears flag, reports honored, pops the modal release dialog
  run_sandboxed "$PRES" off "TestPhone" "TestAgent"
  tap_is "$RC" 0 "presence[$T]: off exits 0 after graceful stop"
  tap_like "$OUT" "graceful stop honored" "presence[$T]: off reports the stop was honored"
  if [ ! -f "$SANDBOX/sd/state/stop_requested" ]; then
    tap_ok "presence[$T]: off clears the stop flag"
  else
    tap_fail "presence[$T]: off clears the stop flag"
  fi
  sleep 1 # the release dialog is backgrounded via nohup
  tap_like "$(grep 'termux-dialog' "$STUB_LOG")" "has released" \
    "presence[$T]: off pops modal release dialog after a stop"
  unset ADB_FG_PKG ADB_WAKE DIALOG_CHOICE 2>/dev/null || true

  # Quiet mode: no torch / vibrate / dialog / notification on request-screen + on/off
  reset_sandbox
  export STAYTURGID_PRESENCE_QUIET=1 DIALOG_CHOICE="no"
  : >"$STUB_LOG"
  run_sandboxed "$PRES" request-screen
  tap_is "$RC" 0 "presence[$T]: quiet request-screen auto-allows (ignores Disallow stub)"
  tap_is "$(stub_calls 'termux-dialog')" 0 "presence[$T]: quiet request-screen skips dialog"
  tap_is "$(stub_calls 'termux-vibrate')" 0 "presence[$T]: quiet request-screen skips vibrate"
  : >"$STUB_LOG"
  run_sandboxed "$PRES" on "QuietPhone" "QuietAgent"
  tap_is "$RC" 0 "presence[$T]: quiet on exits 0"
  tap_is "$(stub_calls 'termux-torch')" 0 "presence[$T]: quiet on skips torch"
  tap_is "$(stub_calls 'termux-notification ')" 0 "presence[$T]: quiet on skips notification"
  : >"$STUB_LOG"
  run_sandboxed "$PRES" off "QuietPhone" "QuietAgent"
  tap_is "$(stub_calls 'termux-torch')" 0 "presence[$T]: quiet off skips torch"
  tap_is "$(stub_calls 'termux-vibrate')" 0 "presence[$T]: quiet off skips vibrate"
  unset STAYTURGID_PRESENCE_QUIET DIALOG_CHOICE
  unset ADB_FG_PKG ADB_WAKE DIALOG_CHOICE 2>/dev/null || true
}

# agent-presence migrated to Python (stayturgid_agent_presence.py is now a compat shim).
presence_suite device/termux/py/stayturgid_agent_presence.py py

# ===========================================================================
# screen-awake-guard.sh
# ===========================================================================
# Same suite runs against the shell implementation and its Python twin.
guard_suite() {
  local GUARD="$1" T="$2"
  unset ADB_TIMEOUT ADB_WAKE DIALOG_CHOICE ADB_WAKELOCK 2>/dev/null || true
  # normal timeout: baseline saved, notification removed, nothing posted
  reset_sandbox
  export ADB_TIMEOUT=120000
  run_sandboxed "$GUARD" check
  tap_is "$RC" 0 "guard[$T]: normal timeout => check exits 0"
  tap_is "$(cat "$SANDBOX/home/.stayturgid/state/screen_timeout_baseline" 2>/dev/null)" "120000" \
    "guard[$T]: baseline timeout recorded while not forced"
  tap_is "$(stub_calls 'termux-notification ')" 0 "guard[$T]: no notification when not forced"
  tap_like "$(cat "$STUB_LOG")" "termux-notification-remove stayturgid-screenlock" \
    "guard[$T]: stale notification removed when not forced"

  # forced (30-min timeout) with screen on: restore notification with baseline button
  : >"$STUB_LOG"
  export ADB_TIMEOUT=1800000
  run_sandboxed "$GUARD" check
  tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "Restore lock (2m)" \
    "guard[$T]: forced awake posts restore notification with saved baseline"
  tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "screen timeout is 30 min" \
    "guard[$T]: notification names the forced-awake reason"

  # forced but screen off: don't nag a dark panel
  : >"$STUB_LOG"
  export ADB_WAKE=Asleep
  run_sandboxed "$GUARD" check
  tap_is "$(stub_calls 'termux-notification ')" 0 "guard[$T]: no notification while screen is off"
  unset ADB_WAKE

  # no baseline known: notification offers the timeout dialog
  : >"$STUB_LOG"
  rm -f "$SANDBOX/home/.stayturgid/state/screen_timeout_baseline"
  run_sandboxed "$GUARD" check
  tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "Set lock timeout" \
    "guard[$T]: without baseline offers the timeout dialog button"

  # restore dialog: quick options 1m/3m/5m/10m, full picker behind Other…
  : >"$STUB_LOG"
  export DIALOG_CHOICE="3 minutes"
  run_sandboxed "$GUARD" restore
  unset DIALOG_CHOICE
  tap_like "$(cat "$STUB_LOG")" "screen_off_timeout 180000" \
    "guard[$T]: dialog quick option 3 minutes applies 180000"
  tap_like "$(grep 'termux-dialog' "$STUB_LOG")" "1 minute,3 minutes,5 minutes,10 minutes,Other…" \
    "guard[$T]: dialog offers 1m/3m/5m/10m + Other…"

  : >"$STUB_LOG"
  printf 'Other…\n30 seconds\n' >"$SANDBOX/dialog_queue"
  run_sandboxed "$GUARD" restore
  tap_like "$(cat "$STUB_LOG")" "screen_off_timeout 30000" \
    "guard[$T]: Other… opens full picker (30 seconds => 30000)"

  : >"$STUB_LOG"
  export DIALOG_CHOICE=""
  run_sandboxed "$GUARD" restore
  unset DIALOG_CHOICE
  tap_is "$RC" 1 "guard[$T]: cancelled dialog changes nothing"
  tap_unlike "$(cat "$STUB_LOG")" "settings put" "guard[$T]: no settings written on cancel"

  # restore with explicit ms: settings restored, screen slept, baseline updated
  : >"$STUB_LOG"
  run_sandboxed "$GUARD" restore 60000
  tap_is "$RC" 0 "guard[$T]: restore exits 0"
  tap_like "$(cat "$STUB_LOG")" "settings put system screen_off_timeout 60000" \
    "guard[$T]: restore sets the requested timeout"
  tap_like "$(cat "$STUB_LOG")" "settings put global stay_on_while_plugged_in 0" \
    "guard[$T]: restore clears stay-on-while-plugged"
  tap_like "$(cat "$STUB_LOG")" "svc power stayon false" "guard[$T]: restore clears svc stayon"
  tap_like "$(cat "$STUB_LOG")" "input keyevent KEYCODE_SLEEP" \
    "guard[$T]: restore turns the screen off as confirmation"
  tap_is "$(cat "$SANDBOX/home/.stayturgid/state/screen_timeout_baseline" 2>/dev/null)" "60000" \
    "guard[$T]: restore updates the baseline"

  # wakelock holder (e.g. Wakey): named in notification; restore keeps screen on
  : >"$STUB_LOG"
  export ADB_WAKELOCK="wakey:wakelock" ADB_TIMEOUT=60000
  run_sandboxed "$GUARD" check
  tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "wakey:wakelock" \
    "guard[$T]: wakelock holder named in notification"
  : >"$STUB_LOG"
  run_sandboxed "$GUARD" restore 60000
  tap_like "$OUT" "wakelock holder remains" "guard[$T]: restore reports remaining wakelock holder"
  tap_unlike "$(cat "$STUB_LOG")" "KEYCODE_SLEEP" \
    "guard[$T]: restore doesn't force screen off while a wakelock persists"
  unset ADB_WAKELOCK ADB_TIMEOUT
  unset ADB_TIMEOUT ADB_WAKE DIALOG_CHOICE ADB_WAKELOCK 2>/dev/null || true
}

# screen-awake-guard migrated to Python (shell retired).
guard_suite device/termux/py/stayturgid_screen_awake_guard.py py

# ===========================================================================
# check-repo-version.sh
# ===========================================================================
# Same suite runs against the shell implementation and its Python twin.
version_check_suite() {
  local CRV="$1" T="$2"
  unset CURL_RC CURL_BODY 2>/dev/null || true
  reset_sandbox
  export CURL_BODY='{"version": "9.9", "changelog": "test build"}'
  run_sandboxed "$CRV"
  tap_is "$RC" 0 "version-check[$T]: new version exits 0"
  tap_like "$(cat "$STUB_LOG")" "stayturgid 9.9 on GitHub" "version-check[$T]: notifies on new version"
  tap_is "$(cat "$SANDBOX/home/.stayturgid/state/repo_version" 2>/dev/null)" "9.9" "version-check[$T]: stamp recorded"

  : >"$STUB_LOG"
  run_sandboxed "$CRV" # same version again
  tap_is "$(stub_calls 'termux-notification')" 0 "version-check[$T]: no repeat notification for same version"

  : >"$STUB_LOG"
  export CURL_RC=22
  run_sandboxed "$CRV"
  tap_is "$RC" 0 "version-check[$T]: network failure exits 0 quietly"
  unset CURL_RC CURL_BODY
  unset CURL_RC CURL_BODY 2>/dev/null || true
}

# check-repo-version migrated to Python (shell retired); py is now the deployed impl.
version_check_suite device/termux/py/stayturgid_check_repo_version.py py

# ===========================================================================
# AutoJs6 log parsing (node + files{} shim)
# ===========================================================================
if command -v node >/dev/null 2>&1; then
  if jsout="$(node tests/js/log.test.js 2>&1)"; then
    tap_ok "autojs6 log.js: node unit tests pass"
  else
    tap_fail "autojs6 log.js: node unit tests pass"
  fi
  printf '%s\n' "$jsout" | sed 's/^/#   /'
  if jsout="$(node tests/js/comonitor.test.js 2>&1)"; then
    tap_ok "autojs6 comonitor.js: node unit tests pass"
  else
    tap_fail "autojs6 comonitor.js: node unit tests pass"
  fi
  printf '%s\n' "$jsout" | sed 's/^/#   /'
  if jsout="$(node tests/js/boot-launcher.test.js 2>&1)"; then
    tap_ok "autojs6 boot-launcher.js: node unit tests pass"
  else
    tap_fail "autojs6 boot-launcher.js: node unit tests pass"
  fi
  printf '%s\n' "$jsout" | sed 's/^/#   /'
else
  tap_skip "autojs6 log.js unit tests" "node not installed"
  tap_skip "autojs6 comonitor.js unit tests" "node not installed"
  tap_skip "autojs6 boot-launcher.js unit tests" "node not installed"
fi

# ===========================================================================
# termux_pkg Ansible module (via ansible localhost + fake Termux prefix)
# ===========================================================================
if command -v ansible >/dev/null 2>&1; then
  FAKE="$SANDBOX/fakeprefix"
  mkdir -p "$FAKE/bin"
  cat >"$FAKE/bin/bash" <<'STUB'
#!/usr/bin/env bash
LOG="$(dirname "$0")/../module-calls.log"
printf '%s\n' "$2" >> "$LOG"
case "$2" in
  *dpkg-query*)    exit 1 ;;                                  # nothing installed
  *"pkg update"*)
      if [ -f "$(dirname "$0")/../fail-update" ]; then
          echo "E: Failed to fetch ... Mirror sync in progress?" >&2; exit 100
      fi
      echo "Get:1 https://example stable InRelease"; exit 0 ;;
  *full-upgrade*|*"pkg upgrade"*) echo "0 upgraded, 0 newly installed."; exit 0 ;;
  *"pkg install"*) echo "installed."; exit 0 ;;
esac
exit 0
STUB
  chmod +x "$FAKE/bin/bash"
  MODLOG="$FAKE/module-calls.log"
  MODARGS="{\"name\": [\"foo\"], \"update_cache\": true, \"upgrade\": true, \"_termux_prefix\": \"$FAKE\"}"

  # M6 regression: --check must not run pkg update / upgrade
  : >"$MODLOG"
  out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
    ansible localhost -c local --check -m stayturgid.fleet.termux_pkg -a "$MODARGS" 2>&1)" || true
  tap_like "$out" "CHANGED" "termux_pkg: check mode reports would-change for missing pkg"
  tap_unlike "$(cat "$MODLOG")" "pkg update" "termux_pkg: check mode runs no pkg update (M6)"
  tap_unlike "$(cat "$MODLOG")" "full-upgrade" "termux_pkg: check mode runs no upgrade (M6)"
  tap_like "$(cat "$MODLOG")" "dpkg-query" "termux_pkg: check mode still probes installed state"

  # M6 regression: real install runs pkg update exactly once (no re-run)
  : >"$MODLOG"
  out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
    ansible localhost -c local -m stayturgid.fleet.termux_pkg -a "$MODARGS" 2>&1)" || true
  tap_like "$out" "CHANGED" "termux_pkg: install of missing pkg reports changed"
  tap_is "$(grep -c 'pkg update' "$MODLOG" | tr -d ' ')" 1 \
    "termux_pkg: pkg update runs exactly once per module run (M6)"
  tap_like "$(cat "$MODLOG")" "pkg install -y foo" "termux_pkg: installs the missing package"

  # update/upgrade-only invocation (role task 1 shape)
  : >"$MODLOG"
  out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
    ansible localhost -c local -m stayturgid.fleet.termux_pkg \
    -a "{\"name\": [], \"update_cache\": true, \"upgrade\": true, \"_termux_prefix\": \"$FAKE\"}" 2>&1)" || true
  # fake `pkg update` emits "Get:" so the module correctly reports changed
  tap_like "$out" "CHANGED" "termux_pkg: bare update/upgrade run succeeds (changed: cache fetched)"
  tap_is "$(grep -c 'full-upgrade' "$MODLOG" | tr -d ' ')" 1 "termux_pkg: upgrade runs exactly once"

  # mirror-sync tolerance: failed pkg update warns but install still proceeds
  touch "$FAKE/fail-update"
  : >"$MODLOG"
  out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
    ansible localhost -c local -m stayturgid.fleet.termux_pkg -a "$MODARGS" 2>&1)" || true
  rm -f "$FAKE/fail-update"
  tap_like "$out" "CHANGED" "termux_pkg: install succeeds despite failed pkg update (mirror sync)"
  tap_like "$out" "cached" "termux_pkg: failed update surfaces as warning, not failure"
  tap_like "$(cat "$MODLOG")" "pkg install -y foo" "termux_pkg: install ran after tolerated update failure"
else
  tap_skip "termux_pkg module tests" "ansible not installed"
fi

# ===========================================================================
# Termux boot / bridge shell scripts (device-free sandbox)
# ===========================================================================
START_ADB="$REPO/device/termux/py/start_adb.py"
BRIDGES_PY="$REPO/device/termux/py/stayturgid_bridges.py"
START_BRIDGE="$REPO/device/termux/boot/start-repair-bridge.sh"
START_AUTOJS6="$REPO/device/termux/boot/start-autojs6-watchdog.sh"

# start_adb.py: writes bootloop.pid immediately (parent forks, child daemon loop)
reset_sandbox
mkdir -p "$SANDBOX/home/.stayturgid/bin"
cat >"$SANDBOX/home/.stayturgid/env" <<'ENV'
export STAYTURGID_SD=/sdcard/stayturgid
export STAYTURGID_BOOT_SETTLE_SEC=0
export STAYTURGID_INTERVAL_SEC=300
ENV
cat >"$SANDBOX/home/.stayturgid/bin/firerpa_lifecycle.py" <<'STUB'
#!/usr/bin/env python3
import os
import sys

with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as log:
    log.write("firerpa_lifecycle.py " + " ".join(sys.argv[1:]) + "\n")
STUB
printf 'export STAYTURGID_FIRERPA_LIFECYCLE=%s\n' \
  "$SANDBOX/home/.stayturgid/bin/firerpa_lifecycle.py" \
  >>"$SANDBOX/home/.stayturgid/env"
touch "$SANDBOX/home/.stayturgid/bin/stayturgid_repair.py"
chmod +x "$SANDBOX/home/.stayturgid/bin/stayturgid_repair.py" \
  "$SANDBOX/home/.stayturgid/bin/firerpa_lifecycle.py"
run_sandboxed "$START_ADB"
if [ -f "$SANDBOX/home/.stayturgid/run/bootloop.pid" ]; then
  tap_ok "start-adb: writes bootloop.pid immediately (before 30s settle)"
else
  tap_fail "start-adb: writes bootloop.pid immediately (before 30s settle)"
fi
# The parent intentionally records the child before startup_firerpa() runs.
# Observe the asynchronous launch before terminating the sandbox daemon.
wait_stub_like "firerpa_lifecycle.py start" || true
kill_sandbox_pid "$SANDBOX/home/.stayturgid/run/bootloop.pid"
tap_is "$RC" 0 "start-adb: exits 0 after launching boot loop"

tap_like "$(cat "$STUB_LOG")" "sshd" "start-adb: starts sshd"
tap_like "$(cat "$STUB_LOG")" "termux-wake-lock" "start-adb: requests wakelock"
tap_like "$(cat "$STUB_LOG")" "adb -s localhost:5555 shell" \
  "start-adb: FIRERPA lifecycle uses uid-2000 localhost ADB shell"
tap_like "$(cat "$STUB_LOG")" \
  "--certificate=/data/local/tmp/firerpa/server/lamda.pem" \
  "start-adb: FIRERPA launch requires the service certificate"
tap_like "$(cat "$STUB_LOG")" \
  "firerpa_lifecycle.py start" \
  "start-adb: FIRERPA launch uses the accessibility coexistence lifecycle"
tap_unlike "$(cat "$STUB_LOG")" \
  "/data/local/tmp/firerpa/server/bin/python3.9 -u -m lamda" \
  "start-adb: never launches FIRERPA directly as the Termux app UID"

# start-adb: empty version stamp must not break daily check arithmetic
reset_sandbox
mkdir -p "$SANDBOX/home/.stayturgid/bin" "$SANDBOX/home/.stayturgid/state" \
  "$SANDBOX/sd/logs"
# Write env file so start_adb.py picks up test-speed settings
cat >"$SANDBOX/home/.stayturgid/env" <<'ENV'
export STAYTURGID_SD=/sdcard/stayturgid
export STAYTURGID_BOOT_SETTLE_SEC=0
export STAYTURGID_INTERVAL_SEC=1
export STAYTURGID_FIRERPA_ENABLED=0
ENV
: >"$SANDBOX/home/.stayturgid/state/last_version_check"
touch "$SANDBOX/home/.stayturgid/bin/stayturgid_check_repo_version.py"
chmod +x "$SANDBOX/home/.stayturgid/bin/stayturgid_check_repo_version.py"
cat >"$SANDBOX/home/.stayturgid/bin/stayturgid_autojs6_guard.py" <<'PY'
#!/usr/bin/env python3
import sys
print("guard", sys.argv[1:])
sys.exit(0)
PY
chmod +x "$SANDBOX/home/.stayturgid/bin/stayturgid_autojs6_guard.py"
run_sandboxed "$START_ADB"
wait_stub_like "stayturgid_check_repo_version.py" || true
wait_stub_like "stayturgid_autojs6_guard.py" || true
kill_sandbox_pid "$SANDBOX/home/.stayturgid/run/bootloop.pid"
tap_like "$(grep python3 "$STUB_LOG")" "stayturgid_check_repo_version.py" \
  "start-adb: empty version stamp treated as 0 (arithmetic safe)"
if grep -qF "stayturgid_autojs6_guard.py check" "$STUB_LOG" 2>/dev/null; then
  tap_ok "start-adb: runs autojs6 guard without RunIntentActivity"
else
  tap_fail "start-adb: runs autojs6 guard without RunIntentActivity"
fi
if grep -qF "boot-launcher.js" "$STUB_LOG" 2>/dev/null; then
  tap_fail "start-adb: does not am start boot-launcher from boot loop"
else
  tap_ok "start-adb: does not am start boot-launcher from boot loop"
fi

# bridges.py --mode repair: trigger file => repair within one loop (~2s stubbed)
reset_sandbox
mkdir -p "$SANDBOX/home/.stayturgid/bin" "$SANDBOX/sd/run" "$SANDBOX/home/.stayturgid/logs"
cat >"$SANDBOX/home/.stayturgid/bin/stayturgid_repair.py" <<'EOF'
#!/usr/bin/env bash
echo "REPAIR_OK"
exit 0
EOF
chmod +x "$SANDBOX/home/.stayturgid/bin/stayturgid_repair.py"
touch "$SANDBOX/sd/run/repair_now"
run_sandboxed_alarm 3 "$BRIDGES_PY" --mode repair
BRIDGE_LOG="$SANDBOX/home/.stayturgid/logs/repair-bridge.log"
if [ ! -f "$SANDBOX/sd/run/repair_now" ]; then
  tap_ok "bridges: trigger file removed after handling (repair mode)"
else
  tap_fail "bridges: trigger file removed after handling (repair mode)"
fi
tap_like "$(cat "$BRIDGE_LOG" 2>/dev/null)" "trigger seen" "bridges: logs trigger (repair mode)"
tap_like "$(cat "$BRIDGE_LOG" 2>/dev/null)" "repair complete" "bridges: invokes stayturgid_repair.py"
if [ -f "$SANDBOX/home/.stayturgid/run/bridge.pid" ]; then
  tap_ok "bridges: writes bridge.pid on start (repair mode)"
else
  tap_fail "bridges: writes bridge.pid on start (repair mode)"
fi

# start-repair-bridge.sh: calls nohup python3 bridges.py when bridge not running
reset_sandbox
mkdir -p "$SANDBOX/home/.stayturgid/bin" "$SANDBOX/home/.stayturgid/logs" "$SANDBOX/home/.stayturgid/run"
cp "$BRIDGES_PY" "$SANDBOX/home/.stayturgid/bin/bridges.py"
chmod +x "$SANDBOX/home/.stayturgid/bin/bridges.py"
run_sandboxed "$START_BRIDGE"
# nohup stub writes to STUB_LOG asynchronously; wait briefly
sleep 0.5
tap_like "$(cat "$STUB_LOG")" "nohup" "start-repair-bridge: calls nohup to launch bridge when idle"

# Skips when pidfile shows running bridge
reset_sandbox
mkdir -p "$SANDBOX/home/.stayturgid/bin" "$SANDBOX/home/.stayturgid/run" "$SANDBOX/proc/4242"
printf 'bridges\0' >"$SANDBOX/proc/4242/cmdline"
echo 4242 >"$SANDBOX/home/.stayturgid/run/bridge.pid"
cp "$BRIDGES_PY" "$SANDBOX/home/.stayturgid/bin/bridges.py"
chmod +x "$SANDBOX/home/.stayturgid/bin/bridges.py"
: >"$STUB_LOG"
PROC_ROOT="$SANDBOX/proc" run_sandboxed "$START_BRIDGE"
tap_is "$(stub_calls 'nohup')" 0 \
  "start-repair-bridge: skips start when pidfile process is alive"

# start-autojs6-watchdog.sh: missing boot script => quiet exit; present => am start
reset_sandbox
run_sandboxed "$START_AUTOJS6"
tap_is "$RC" 0 "start-autojs6: exits 0 when boot-launcher.js missing"
tap_is "$(stub_calls 'am ')" 0 "start-autojs6: no am start without boot script"

reset_sandbox
mkdir -p "$SANDBOX/sd/autojs6/scripts"
: >"$SANDBOX/sd/autojs6/scripts/boot-launcher.js"
run_sandboxed "$START_AUTOJS6"
tap_is "$RC" 0 "start-autojs6: exits 0 when boot script present"
tap_like "$(cat "$STUB_LOG")" "boot-launcher.js" "start-autojs6: am start targets boot-launcher.js"

# bridges.py --mode autojs6: trigger file => am start within one loop
START_AUTOJS6_BRIDGE="$REPO/device/termux/boot/start-autojs6-bridge.sh"
reset_sandbox
mkdir -p "$SANDBOX/home/.stayturgid/bin" "$SANDBOX/sd/run" "$SANDBOX/sd/autojs6/scripts" \
  "$SANDBOX/home/.stayturgid/state" "$SANDBOX/home/.stayturgid/logs"
: >"$SANDBOX/sd/autojs6/scripts/boot-launcher.js"
touch "$SANDBOX/sd/run/start_autojs6_now"
run_sandboxed_alarm 3 "$BRIDGES_PY" --mode autojs6
AJ6_LOG="$SANDBOX/home/.stayturgid/logs/autojs6-bridge.log"
if [ ! -f "$SANDBOX/sd/run/start_autojs6_now" ]; then
  tap_ok "bridges: trigger file removed after handling (autojs6 mode)"
else
  tap_fail "bridges: trigger file removed after handling (autojs6 mode)"
fi
tap_like "$(cat "$AJ6_LOG" 2>/dev/null)" "boot-launcher" "bridges: am start boot-launcher"

# start-autojs6-bridge: calls nohup to launch autojs6 bridge when idle
reset_sandbox
mkdir -p "$SANDBOX/home/.stayturgid/bin" "$SANDBOX/home/.stayturgid/logs" "$SANDBOX/home/.stayturgid/run"
cp "$BRIDGES_PY" "$SANDBOX/home/.stayturgid/bin/bridges.py"
chmod +x "$SANDBOX/home/.stayturgid/bin/bridges.py"
run_sandboxed "$START_AUTOJS6_BRIDGE"
sleep 0.5
tap_like "$(cat "$STUB_LOG")" "nohup" "start-autojs6-bridge: calls nohup to launch autojs6 bridge when idle"

tap_done
