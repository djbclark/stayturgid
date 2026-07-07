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
trap 'rm -rf "$SANDBOX"' EXIT

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
    echo '{"percentage": 12, "status": "DISCHARGING"}' > "$SANDBOX/batt.json"
    run_sandboxed "$BATT"
    tap_is "$RC" 0 "battery[$T]: run at 12% exits 0"
    tap_is "$(stub_calls 'termux-notification ')" 1 "battery[$T]: single alert at 12% (no tier cascade)"
    tap_is "$(sort -n "$SANDBOX/home/.stayturgid_batt_alerted" | tr '\n' ' ')" "15 20 25 30 " \
        "battery[$T]: tiers 30/25/20/15 all marked alerted"
    tap_like "$OUT$(grep termux-toast "$STUB_LOG")" "tier 15" "battery[$T]: alert names lowest tier (15)"

    # idempotent rerun
    run_sandboxed "$BATT"
    tap_is "$(stub_calls 'termux-notification ')" 1 "battery[$T]: rerun at same pct fires nothing new"

    # drop to 9% fires exactly the next tier
    echo '{"percentage": 9, "status": "DISCHARGING"}' > "$SANDBOX/batt.json"
    run_sandboxed "$BATT"
    tap_is "$(stub_calls 'termux-notification ')" 2 "battery[$T]: drop to 9% fires exactly one more alert"

    # M1 regression: no valid wallpaper backup => zero wallpaper writes
    tap_is "$(stub_calls 'termux-wallpaper')" 0 "battery[$T]: wallpaper untouched without verified backup"

    # charging clears state and removes the notification
    echo '{"percentage": 50, "status": "CHARGING"}' > "$SANDBOX/batt.json"
    run_sandboxed "$BATT"
    if [ ! -f "$SANDBOX/home/.stayturgid_batt_alerted" ]; then
        tap_ok "battery[$T]: charging clears alert state"
    else
        tap_fail "battery[$T]: charging clears alert state"
    fi
    tap_like "$(cat "$STUB_LOG")" "termux-notification-remove stayturgid-batt" \
        "battery[$T]: charging removes the notification"

    # M3 regression: battery JSON without percentage => clean exit 0 (guard, not set -e)
    reset_sandbox
    echo '{"status": "DISCHARGING"}' > "$SANDBOX/batt.json"
    run_sandboxed "$BATT"
    tap_is "$RC" 0 "battery[$T]: malformed battery JSON exits 0 via guard"

    # valid backup => wallpaper blink used AND restored from backup afterwards
    reset_sandbox
    printf '\x89PNG\r\n\x1a\nfakepixels' > "$SANDBOX/wall.png"
    export ADB_WALLPAPER_FILE="$SANDBOX/wall.png"
    mkdir -p "$SANDBOX/home/.stayturgid/battery-colors"
    for c in purple blue green yellow orange red black; do
        : > "$SANDBOX/home/.stayturgid/battery-colors/$c.png"
    done
    echo '{"percentage": 28, "status": "DISCHARGING"}' > "$SANDBOX/batt.json"
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
    echo '{"percentage": 12, "status": "DISCHARGING"}' > "$SANDBOX/batt.json"
    run_sandboxed "$BATT"
    unset ADB_ZEN
    tap_is "$(stub_calls 'termux-toast')" 0 "battery[$T]: DND fires no toast"
    tap_is "$(stub_calls 'termux-vibrate')" 0 "battery[$T]: DND fires no vibrate"
    tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "quiet hours" "battery[$T]: DND posts silent notification"
    tap_is "$(stub_calls 'termux-torch on')" 1 "battery[$T]: DND single quick torch flash (tier<=15)"
}

battery_suite termux/stayturgid-battery-alarm.sh sh
battery_suite termux/py/stayturgid_battery_alarm.py py

# ===========================================================================
# stayturgid-repair.sh
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
    tap_like "$OUT" "STATUS port=open shizuku=up sshd=up a11y=up shell=yes" "repair[$T]: healthy STATUS line"

    # a11y self-heal: service missing => APPENDED to existing list, never replaced
    reset_sandbox
    export PGREP_RC=0 ADB_A11Y="com.other.app/.TheirService"
    run_sandboxed "$RSCRIPT"
    tap_like "$OUT" "a11y=repaired" "repair[$T]: disabled accessibility => repaired"
    tap_is "$(cat "$SANDBOX/a11y_state" 2>/dev/null)" \
        "com.other.app/.TheirService:org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher" \
        "repair[$T]: a11y re-enable APPENDS, preserving other services (HACKING Part 5 rule)"
    reset_sandbox
    export ADB_A11Y="null"
    run_sandboxed "$RSCRIPT"
    tap_is "$(cat "$SANDBOX/a11y_state" 2>/dev/null)" \
        "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher" \
        "repair[$T]: empty a11y list => service alone, no stray separator"
    unset ADB_A11Y

    # sshd down => restarted via sshd stub
    reset_sandbox
    export PGREP_RC=1
    run_sandboxed "$RSCRIPT"
    tap_is "$RC" 0 "repair[$T]: sshd down => restarted, exit 0"
    tap_like "$OUT" "sshd=restarted" "repair[$T]: STATUS reports sshd=restarted"

    # 5555 dead (shell uid probe fails) => CLOSED_NO_SHELL, exit 1
    reset_sandbox
    export PGREP_RC=0 ADB_SHELL_UID=""
    run_sandboxed "$RSCRIPT"
    unset ADB_SHELL_UID
    tap_is "$RC" 1 "repair[$T]: no privileged shell => exit 1"
    tap_like "$OUT" "port=CLOSED_NO_SHELL" "repair[$T]: STATUS reports CLOSED_NO_SHELL"

    # H1 regression: lock-contention branch must resolve its helpers
    reset_sandbox
    export PGREP_RC=0 FLOCK_RC=1
    run_sandboxed "$RSCRIPT"
    unset FLOCK_RC
    tap_is "$RC" 0 "repair[$T]: duplicate invocation exits 0 (advisory)"
    tap_like "$OUT" "sshd=up" "repair[$T]: duplicate branch reports real sshd state (H1)"
    tap_unlike "$ERR" "command not found" "repair[$T]: duplicate branch has no unresolved functions (H1)"

    # M8 regression: oversized log gets trimmed
    reset_sandbox
    export PGREP_RC=0
    seq 1 1500 | sed 's/^/line /' > "$SANDBOX/home/.stayturgid-repair.log"
    run_sandboxed "$RSCRIPT"
    lines=$(wc -l < "$SANDBOX/home/.stayturgid-repair.log" | tr -d ' ')
    if [ "$lines" -le 510 ]; then
        tap_ok "repair[$T]: 1500-line log trimmed to <=510 ($lines)"
    else
        tap_fail "repair[$T]: 1500-line log trimmed to <=510" "got $lines lines"
    fi
    unset PGREP_RC
    unset PGREP_RC FLOCK_RC ADB_A11Y ADB_SHELL_UID 2>/dev/null || true
}

repair_suite termux/stayturgid-repair.sh sh
repair_suite termux/py/stayturgid_repair.py py

# ===========================================================================
# claude-presence.sh gate
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
    if [ -f "$SANDBOX/sd/stayturgid_presence_check_after" ]; then
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
    export DIALOG_CHOICE="Continue"   # must NOT be consulted while paused
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
    # request-screen: Disallow => 75; Yes or 60s timeout => 0
    reset_sandbox
    export DIALOG_CHOICE="no"
    run_sandboxed "$PRES" request-screen
    tap_is "$RC" 75 "presence[$T]: request-screen Disallow => 75"
    export DIALOG_CHOICE="yes"
    run_sandboxed "$PRES" request-screen
    tap_is "$RC" 0 "presence[$T]: request-screen Yes => proceed"
    export DIALOG_CHOICE=""
    run_sandboxed "$PRES" request-screen
    tap_is "$RC" 0 "presence[$T]: request-screen 60s timeout => proceed"
    unset DIALOG_CHOICE

    # on posts the running notification with a Graceful stop button
    reset_sandbox
    run_sandboxed "$PRES" on "TestPhone" "TestAgent"
    tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "Graceful stop" \
        "presence[$T]: running notification carries Graceful stop button"

    # stop-requested: 1 before the button, 0 after
    run_sandboxed "$PRES" stop-requested
    tap_is "$RC" 1 "presence[$T]: no stop requested initially"
    touch "$SANDBOX/sd/stayturgid_stop_requested"
    run_sandboxed "$PRES" stop-requested
    tap_is "$RC" 0 "presence[$T]: stop-requested detects the flag"

    # off after a stop: clears flag, reports honored, pops the modal release dialog
    run_sandboxed "$PRES" off "TestPhone" "TestAgent"
    tap_is "$RC" 0 "presence[$T]: off exits 0 after graceful stop"
    tap_like "$OUT" "graceful stop honored" "presence[$T]: off reports the stop was honored"
    if [ ! -f "$SANDBOX/sd/stayturgid_stop_requested" ]; then
        tap_ok "presence[$T]: off clears the stop flag"
    else
        tap_fail "presence[$T]: off clears the stop flag"
    fi
    sleep 1   # the release dialog is backgrounded via nohup
    tap_like "$(grep 'termux-dialog' "$STUB_LOG")" "has released" \
        "presence[$T]: off pops modal release dialog after a stop"
    unset ADB_FG_PKG ADB_WAKE DIALOG_CHOICE 2>/dev/null || true
}

presence_suite termux/agent-presence.sh sh
presence_suite termux/py/stayturgid_agent_presence.py py

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
    tap_is "$(cat "$SANDBOX/home/.stayturgid/screen_timeout_baseline" 2>/dev/null)" "120000" \
        "guard[$T]: baseline timeout recorded while not forced"
    tap_is "$(stub_calls 'termux-notification ')" 0 "guard[$T]: no notification when not forced"
    tap_like "$(cat "$STUB_LOG")" "termux-notification-remove stayturgid-screenlock" \
        "guard[$T]: stale notification removed when not forced"

    # forced (30-min timeout) with screen on: restore notification with baseline button
    : > "$STUB_LOG"
    export ADB_TIMEOUT=1800000
    run_sandboxed "$GUARD" check
    tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "Restore lock (2m)" \
        "guard[$T]: forced awake posts restore notification with saved baseline"
    tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "screen timeout is 30 min" \
        "guard[$T]: notification names the forced-awake reason"

    # forced but screen off: don't nag a dark panel
    : > "$STUB_LOG"
    export ADB_WAKE=Asleep
    run_sandboxed "$GUARD" check
    tap_is "$(stub_calls 'termux-notification ')" 0 "guard[$T]: no notification while screen is off"
    unset ADB_WAKE

    # no baseline known: notification offers the timeout dialog
    : > "$STUB_LOG"
    rm -f "$SANDBOX/home/.stayturgid/screen_timeout_baseline"
    run_sandboxed "$GUARD" check
    tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "Set lock timeout" \
        "guard[$T]: without baseline offers the timeout dialog button"

    # restore dialog: quick options 1m/3m/5m/10m, full picker behind Other…
    : > "$STUB_LOG"
    export DIALOG_CHOICE="3 minutes"
    run_sandboxed "$GUARD" restore
    unset DIALOG_CHOICE
    tap_like "$(cat "$STUB_LOG")" "screen_off_timeout 180000" \
        "guard[$T]: dialog quick option 3 minutes applies 180000"
    tap_like "$(grep 'termux-dialog' "$STUB_LOG")" "1 minute,3 minutes,5 minutes,10 minutes,Other…" \
        "guard[$T]: dialog offers 1m/3m/5m/10m + Other…"

    : > "$STUB_LOG"
    printf 'Other…\n30 seconds\n' > "$SANDBOX/dialog_queue"
    run_sandboxed "$GUARD" restore
    tap_like "$(cat "$STUB_LOG")" "screen_off_timeout 30000" \
        "guard[$T]: Other… opens full picker (30 seconds => 30000)"

    : > "$STUB_LOG"
    export DIALOG_CHOICE=""
    run_sandboxed "$GUARD" restore
    unset DIALOG_CHOICE
    tap_is "$RC" 1 "guard[$T]: cancelled dialog changes nothing"
    tap_unlike "$(cat "$STUB_LOG")" "settings put" "guard[$T]: no settings written on cancel"

    # restore with explicit ms: settings restored, screen slept, baseline updated
    : > "$STUB_LOG"
    run_sandboxed "$GUARD" restore 60000
    tap_is "$RC" 0 "guard[$T]: restore exits 0"
    tap_like "$(cat "$STUB_LOG")" "settings put system screen_off_timeout 60000" \
        "guard[$T]: restore sets the requested timeout"
    tap_like "$(cat "$STUB_LOG")" "settings put global stay_on_while_plugged_in 0" \
        "guard[$T]: restore clears stay-on-while-plugged"
    tap_like "$(cat "$STUB_LOG")" "svc power stayon false" "guard[$T]: restore clears svc stayon"
    tap_like "$(cat "$STUB_LOG")" "input keyevent KEYCODE_SLEEP" \
        "guard[$T]: restore turns the screen off as confirmation"
    tap_is "$(cat "$SANDBOX/home/.stayturgid/screen_timeout_baseline" 2>/dev/null)" "60000" \
        "guard[$T]: restore updates the baseline"

    # wakelock holder (e.g. Wakey): named in notification; restore keeps screen on
    : > "$STUB_LOG"
    export ADB_WAKELOCK="wakey:wakelock" ADB_TIMEOUT=60000
    run_sandboxed "$GUARD" check
    tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "wakey:wakelock" \
        "guard[$T]: wakelock holder named in notification"
    : > "$STUB_LOG"
    run_sandboxed "$GUARD" restore 60000
    tap_like "$OUT" "wakelock holder remains" "guard[$T]: restore reports remaining wakelock holder"
    tap_unlike "$(cat "$STUB_LOG")" "KEYCODE_SLEEP" \
        "guard[$T]: restore doesn't force screen off while a wakelock persists"
    unset ADB_WAKELOCK ADB_TIMEOUT
    unset ADB_TIMEOUT ADB_WAKE DIALOG_CHOICE ADB_WAKELOCK 2>/dev/null || true
}

guard_suite termux/screen-awake-guard.sh sh
guard_suite termux/py/stayturgid_screen_awake_guard.py py

# ===========================================================================
# check-repo-version.sh
# ===========================================================================
CRV=termux/check-repo-version.sh

reset_sandbox
export CURL_BODY='{"version": "9.9", "changelog": "test build"}'
run_sandboxed "$CRV"
tap_is "$RC" 0 "version-check: new version exits 0"
tap_like "$(cat "$STUB_LOG")" "stayturgid 9.9 on GitHub" "version-check: notifies on new version"
tap_is "$(cat "$SANDBOX/home/.stayturgid_repo_version" 2>/dev/null)" "9.9" "version-check: stamp recorded"

: > "$STUB_LOG"
run_sandboxed "$CRV"   # same version again
tap_is "$(stub_calls 'termux-notification')" 0 "version-check: no repeat notification for same version"

: > "$STUB_LOG"
export CURL_RC=22
run_sandboxed "$CRV"
tap_is "$RC" 0 "version-check: network failure exits 0 quietly"
unset CURL_RC CURL_BODY

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
else
    tap_skip "autojs6 log.js unit tests" "node not installed"
fi

# ===========================================================================
# termux_pkg Ansible module (via ansible localhost + fake Termux prefix)
# ===========================================================================
if command -v ansible >/dev/null 2>&1; then
    FAKE="$SANDBOX/fakeprefix"
    mkdir -p "$FAKE/bin"
    cat > "$FAKE/bin/bash" <<'STUB'
#!/bin/bash
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
    : > "$MODLOG"
    out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
        ansible localhost -c local --check -m stayturgid.fleet.termux_pkg -a "$MODARGS" 2>&1)" || true
    tap_like "$out" "CHANGED" "termux_pkg: check mode reports would-change for missing pkg"
    tap_unlike "$(cat "$MODLOG")" "pkg update" "termux_pkg: check mode runs no pkg update (M6)"
    tap_unlike "$(cat "$MODLOG")" "full-upgrade" "termux_pkg: check mode runs no upgrade (M6)"
    tap_like "$(cat "$MODLOG")" "dpkg-query" "termux_pkg: check mode still probes installed state"

    # M6 regression: real install runs pkg update exactly once (no re-run)
    : > "$MODLOG"
    out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
        ansible localhost -c local -m stayturgid.fleet.termux_pkg -a "$MODARGS" 2>&1)" || true
    tap_like "$out" "CHANGED" "termux_pkg: install of missing pkg reports changed"
    tap_is "$(grep -c 'pkg update' "$MODLOG" | tr -d ' ')" 1 \
        "termux_pkg: pkg update runs exactly once per module run (M6)"
    tap_like "$(cat "$MODLOG")" "pkg install -y foo" "termux_pkg: installs the missing package"

    # update/upgrade-only invocation (role task 1 shape)
    : > "$MODLOG"
    out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
        ansible localhost -c local -m stayturgid.fleet.termux_pkg \
        -a "{\"name\": [], \"update_cache\": true, \"upgrade\": true, \"_termux_prefix\": \"$FAKE\"}" 2>&1)" || true
    # fake `pkg update` emits "Get:" so the module correctly reports changed
    tap_like "$out" "CHANGED" "termux_pkg: bare update/upgrade run succeeds (changed: cache fetched)"
    tap_is "$(grep -c 'full-upgrade' "$MODLOG" | tr -d ' ')" 1 "termux_pkg: upgrade runs exactly once"

    # mirror-sync tolerance: failed pkg update warns but install still proceeds
    touch "$FAKE/fail-update"
    : > "$MODLOG"
    out="$(cd "$SANDBOX" && ANSIBLE_COLLECTIONS_PATH="$REPO" \
        ansible localhost -c local -m stayturgid.fleet.termux_pkg -a "$MODARGS" 2>&1)" || true
    rm -f "$FAKE/fail-update"
    tap_like "$out" "CHANGED" "termux_pkg: install succeeds despite failed pkg update (mirror sync)"
    tap_like "$out" "cached" "termux_pkg: failed update surfaces as warning, not failure"
    tap_like "$(cat "$MODLOG")" "pkg install -y foo" "termux_pkg: install ran after tolerated update failure"
else
    tap_skip "termux_pkg module tests" "ansible not installed"
fi

tap_done
