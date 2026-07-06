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
BATT=termux/stayturgid-battery-alarm.sh

# M2 regression: first run at 12% fires ONE alert (lowest tier), marks all
reset_sandbox
echo '{"percentage": 12, "status": "DISCHARGING"}' > "$SANDBOX/batt.json"
run_sandboxed "$BATT"
tap_is "$RC" 0 "battery: run at 12% exits 0"
tap_is "$(stub_calls 'termux-notification ')" 1 "battery: single alert at 12% (no tier cascade)"
tap_is "$(sort -n "$SANDBOX/home/.stayturgid_batt_alerted" | tr '\n' ' ')" "15 20 25 30 " \
    "battery: tiers 30/25/20/15 all marked alerted"
tap_like "$OUT$(grep termux-toast "$STUB_LOG")" "tier 15" "battery: alert names lowest tier (15)"

# idempotent rerun
run_sandboxed "$BATT"
tap_is "$(stub_calls 'termux-notification ')" 1 "battery: rerun at same pct fires nothing new"

# drop to 9% fires exactly the next tier
echo '{"percentage": 9, "status": "DISCHARGING"}' > "$SANDBOX/batt.json"
run_sandboxed "$BATT"
tap_is "$(stub_calls 'termux-notification ')" 2 "battery: drop to 9% fires exactly one more alert"

# M1 regression: no valid wallpaper backup => zero wallpaper writes
tap_is "$(stub_calls 'termux-wallpaper')" 0 "battery: wallpaper untouched without verified backup"

# charging clears state and removes the notification
echo '{"percentage": 50, "status": "CHARGING"}' > "$SANDBOX/batt.json"
run_sandboxed "$BATT"
if [ ! -f "$SANDBOX/home/.stayturgid_batt_alerted" ]; then
    tap_ok "battery: charging clears alert state"
else
    tap_fail "battery: charging clears alert state"
fi
tap_like "$(cat "$STUB_LOG")" "termux-notification-remove stayturgid-batt" \
    "battery: charging removes the notification"

# M3 regression: battery JSON without percentage => clean exit 0 (guard, not set -e)
reset_sandbox
echo '{"status": "DISCHARGING"}' > "$SANDBOX/batt.json"
run_sandboxed "$BATT"
tap_is "$RC" 0 "battery: malformed battery JSON exits 0 via guard"

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
    tap_ok "battery: wallpaper blink runs with verified backup"
else
    tap_fail "battery: wallpaper blink runs with verified backup"
fi
tap_like "$(grep termux-wallpaper "$STUB_LOG" | tail -1)" "wallpaper-backup.png" \
    "battery: last wallpaper write restores the backup"

# quiet mode (DND): no toast/vibrate, silent notification, single torch flash
reset_sandbox
export ADB_ZEN=1
echo '{"percentage": 12, "status": "DISCHARGING"}' > "$SANDBOX/batt.json"
run_sandboxed "$BATT"
unset ADB_ZEN
tap_is "$(stub_calls 'termux-toast')" 0 "battery: DND fires no toast"
tap_is "$(stub_calls 'termux-vibrate')" 0 "battery: DND fires no vibrate"
tap_like "$(grep 'termux-notification ' "$STUB_LOG")" "quiet hours" "battery: DND posts silent notification"
tap_is "$(stub_calls 'termux-torch on')" 1 "battery: DND single quick torch flash (tier<=15)"

# ===========================================================================
# stayturgid-repair.sh
# ===========================================================================
RSCRIPT=termux/stayturgid-repair.sh

# healthy path
reset_sandbox
export PGREP_RC=0
run_sandboxed "$RSCRIPT"
tap_is "$RC" 0 "repair: healthy => exit 0"
tap_like "$OUT" "STATUS port=open shizuku=up sshd=up shell=yes" "repair: healthy STATUS line"

# sshd down => restarted via sshd stub
reset_sandbox
export PGREP_RC=1
run_sandboxed "$RSCRIPT"
tap_is "$RC" 0 "repair: sshd down => restarted, exit 0"
tap_like "$OUT" "sshd=restarted" "repair: STATUS reports sshd=restarted"

# 5555 dead (shell uid probe fails) => CLOSED_NO_SHELL, exit 1
reset_sandbox
export PGREP_RC=0 ADB_SHELL_UID=""
run_sandboxed "$RSCRIPT"
unset ADB_SHELL_UID
tap_is "$RC" 1 "repair: no privileged shell => exit 1"
tap_like "$OUT" "port=CLOSED_NO_SHELL" "repair: STATUS reports CLOSED_NO_SHELL"

# H1 regression: lock-contention branch must resolve its helpers
reset_sandbox
export PGREP_RC=0 FLOCK_RC=1
run_sandboxed "$RSCRIPT"
unset FLOCK_RC
tap_is "$RC" 0 "repair: duplicate invocation exits 0 (advisory)"
tap_like "$OUT" "sshd=up" "repair: duplicate branch reports real sshd state (H1)"
tap_unlike "$ERR" "command not found" "repair: duplicate branch has no unresolved functions (H1)"

# M8 regression: oversized log gets trimmed
reset_sandbox
export PGREP_RC=0
seq 1 1500 | sed 's/^/line /' > "$SANDBOX/home/.stayturgid-repair.log"
run_sandboxed "$RSCRIPT"
lines=$(wc -l < "$SANDBOX/home/.stayturgid-repair.log" | tr -d ' ')
if [ "$lines" -le 510 ]; then
    tap_ok "repair: 1500-line log trimmed to <=510 ($lines)"
else
    tap_fail "repair: 1500-line log trimmed to <=510" "got $lines lines"
fi
unset PGREP_RC

# ===========================================================================
# claude-presence.sh gate
# ===========================================================================
PRES=termux/claude-presence.sh

# idle foreground (Samsung launcher) => proceed, no dialog
reset_sandbox
run_sandboxed "$PRES" gate
tap_is "$RC" 0 "presence: idle launcher foreground => proceed"
tap_is "$(stub_calls 'termux-dialog')" 0 "presence: no dialog when idle"

# M5 regression: Pixel launcher counts as idle
reset_sandbox
export ADB_FG_PKG=com.google.android.apps.nexuslauncher
run_sandboxed "$PRES" gate
tap_is "$RC" 0 "presence: Pixel launcher foreground => proceed (M5)"

# screen off => proceed without dialog
reset_sandbox
export ADB_FG_PKG=com.android.chrome ADB_WAKE=Asleep
run_sandboxed "$PRES" gate
tap_is "$RC" 0 "presence: screen not interactive => proceed"
unset ADB_WAKE

# M4 regression: active use + dialog timeout => fail closed (75 + later file)
reset_sandbox
export ADB_FG_PKG=com.android.chrome DIALOG_CHOICE=""
run_sandboxed "$PRES" gate
tap_is "$RC" 75 "presence: dialog timeout fails closed with 75 (M4)"
if [ -f "$SANDBOX/sd/stayturgid_presence_check_after" ]; then
    tap_ok "presence: timeout arms 10-minute recheck"
else
    tap_fail "presence: timeout arms 10-minute recheck"
fi

# explicit Continue => proceed
reset_sandbox
export DIALOG_CHOICE="Continue"
run_sandboxed "$PRES" gate
tap_is "$RC" 0 "presence: explicit Continue => proceed"

# Pause => 75 now, 75 on next gate, cleared by resume
reset_sandbox
export DIALOG_CHOICE="Pause"
run_sandboxed "$PRES" gate
tap_is "$RC" 75 "presence: Pause => 75"
export DIALOG_CHOICE="Continue"   # must NOT be consulted while paused
run_sandboxed "$PRES" gate
tap_is "$RC" 75 "presence: paused gate stays closed without dialog"
run_sandboxed "$PRES" resume
run_sandboxed "$PRES" gate
tap_is "$RC" 0 "presence: resume clears pause"
unset DIALOG_CHOICE ADB_FG_PKG

# usage error => exit 2
run_sandboxed "$PRES" bogus-action
tap_is "$RC" 2 "presence: unknown action => usage exit 2"

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
  *"pkg update"*)  echo "Get:1 https://example stable InRelease"; exit 0 ;;
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
    out="$(cd "$SANDBOX" && ANSIBLE_LIBRARY="$REPO/ansible/library" \
        ansible localhost -c local --check -m termux_pkg -a "$MODARGS" 2>&1)" || true
    tap_like "$out" "CHANGED" "termux_pkg: check mode reports would-change for missing pkg"
    tap_unlike "$(cat "$MODLOG")" "pkg update" "termux_pkg: check mode runs no pkg update (M6)"
    tap_unlike "$(cat "$MODLOG")" "full-upgrade" "termux_pkg: check mode runs no upgrade (M6)"
    tap_like "$(cat "$MODLOG")" "dpkg-query" "termux_pkg: check mode still probes installed state"

    # M6 regression: real install runs pkg update exactly once (no re-run)
    : > "$MODLOG"
    out="$(cd "$SANDBOX" && ANSIBLE_LIBRARY="$REPO/ansible/library" \
        ansible localhost -c local -m termux_pkg -a "$MODARGS" 2>&1)" || true
    tap_like "$out" "CHANGED" "termux_pkg: install of missing pkg reports changed"
    tap_is "$(grep -c 'pkg update' "$MODLOG" | tr -d ' ')" 1 \
        "termux_pkg: pkg update runs exactly once per module run (M6)"
    tap_like "$(cat "$MODLOG")" "pkg install -y foo" "termux_pkg: installs the missing package"

    # update/upgrade-only invocation (role task 1 shape)
    : > "$MODLOG"
    out="$(cd "$SANDBOX" && ANSIBLE_LIBRARY="$REPO/ansible/library" \
        ansible localhost -c local -m termux_pkg \
        -a "{\"name\": [], \"update_cache\": true, \"upgrade\": true, \"_termux_prefix\": \"$FAKE\"}" 2>&1)" || true
    # fake `pkg update` emits "Get:" so the module correctly reports changed
    tap_like "$out" "CHANGED" "termux_pkg: bare update/upgrade run succeeds (changed: cache fetched)"
    tap_is "$(grep -c 'full-upgrade' "$MODLOG" | tr -d ' ')" 1 "termux_pkg: upgrade runs exactly once"
else
    tap_skip "termux_pkg module tests" "ansible not installed"
fi

tap_done
