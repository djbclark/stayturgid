#!/data/data/com.termux/files/usr/bin/bash
# On-device "an agent is controlling this phone" indicator.
# Deployed to ~/claude-presence.sh on each device; called over SSH/ADB by the
# agent at the start and end of a device session.
#
#   claude-presence.sh on  [label] [agent]   # torch+vibrate pulse, then ongoing notification
#   claude-presence.sh off [label] [agent]   # torch+vibrate pulse, remove notification
#   claude-presence.sh gate [label] [agent]   # consent gate if phone appears in use
#   claude-presence.sh resume                 # clear a previous Pause choice
#
# Agent name: 3rd argument, or STAYTURGID_AGENT env var (default: Auto).
#
# Off the screen surface entirely (torch, vibration, status-bar notification),
# PLUS whole-screen color inversion while the session runs. Inversion is applied
# in the display pipeline AFTER the capture point, so `screencap`, uiautomator
# dumps and taps are all completely unaffected (verified empirically on both the
# Pixel 7a and Galaxy S24, 2026-07-05: screencap diff with inversion on vs off
# was ~0) — only the human looking at the panel sees it.
#
# Inversion needs a `shell`-uid `settings put secure`; Termux can't do that
# itself, so it goes through the localhost:5555 privileged-shell channel
# (same one stayturgid-repair.sh uses). Best-effort: skipped silently if 5555
# is down. If a session dies without running `off`, either rerun `off` or
# clear by hand: settings put secure accessibility_display_inversion_enabled 0

export PATH=/data/data/com.termux/files/usr/bin:$PATH
ACTION="$1"
LABEL="${2:-this phone}"
AGENT="${3:-${STAYTURGID_AGENT:-Auto}}"
NID="stayturgid-presence"
SD="${STAYTURGID_SD:-/sdcard}"   # override in tests (no /sdcard off-device)
PAUSE_FILE="$SD/stayturgid_presence_paused"
LATER_FILE="$SD/stayturgid_presence_check_after"

adb_shell() {
    adb connect localhost:5555 >/dev/null 2>&1 && adb -s localhost:5555 shell "$@" 2>/dev/null
}

invert() {  # $1 = 1|0 — best-effort whole-screen inversion via the 5555 shell
    adb_shell "settings put secure accessibility_display_inversion_enabled $1"
}

pulse() {   # $1 = number of torch blinks
    for _ in $(seq 1 "$1"); do
        termux-torch on  2>/dev/null; sleep 0.25
        termux-torch off 2>/dev/null; sleep 0.20
    done
}

foreground_pkg() {
    adb_shell dumpsys window \
        | awk -F '[ /}]' '/mCurrentFocus/ { for (i=1; i<=NF; i++) if ($i ~ /^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)+$/) { print $i; exit } }'
}

screen_interactive() {
    adb_shell dumpsys power | awk '
        /mWakefulness=Awake/ { awake=1 }
        /mIsInteractive: true/ { interactive=1 }
        END { exit !(awake || interactive) }
    '
}

idle_foreground() {
    case "$1" in
        ""|com.sec.android.app.launcher|com.google.android.apps.nexuslauncher|\
        com.android.launcher3|com.android.systemui|com.samsung.android.app.aodservice|\
        com.termux|com.tailscale.ipn|moe.shizuku.privileged.api|org.autojs.autojs6)
            return 0
            ;;
    esac
    return 1
}

pause_active() {
    [ -f "$PAUSE_FILE" ]
}

later_active() {
    [ -f "$LATER_FILE" ] || return 1
    local now until
    now="$(date +%s)"
    until="$(cat "$LATER_FILE" 2>/dev/null || echo 0)"
    [ "$until" -gt "$now" ] 2>/dev/null
}

consent_gate() {
    if pause_active; then
        echo "presence gate: paused (run claude-presence.sh resume to clear)"
        return 75
    fi
    if later_active; then
        echo "presence gate: check later active until $(cat "$LATER_FILE")"
        return 75
    fi

    local pkg
    pkg="$(foreground_pkg)"
    if ! screen_interactive || idle_foreground "$pkg"; then
        echo "presence gate: proceed (screen idle; foreground=${pkg:-unknown})"
        return 0
    fi

    termux-vibrate -d 200 2>/dev/null
    local out choice
    out="$(timeout 30 termux-dialog radio \
        -t "$AGENT wants to use $LABEL" \
        -v "Continue,Pause,Check again in 10 minutes" 2>/dev/null || true)"
    choice="$(printf '%s\n' "$out" | awk -F '"' '/text/ { print $4; exit }')"

    case "$choice" in
        "Continue")
            rm -f "$LATER_FILE"
            echo "presence gate: continue"
            return 0
            ;;
        "Pause")
            date +%s > "$PAUSE_FILE"
            termux-notification --id "$NID" --priority high --alert-once \
                --title "$AGENT paused on $LABEL" \
                --content "Run claude-presence.sh resume to clear." 2>/dev/null
            echo "presence gate: pause"
            return 75
            ;;
        *)
            # "Check again in 10 minutes", dialog timeout, or anything
            # unrecognized: fail closed. The gate only shows while the phone
            # is actively in use, so silence is not consent.
            echo $(( $(date +%s) + 600 )) > "$LATER_FILE"
            echo "presence gate: later (choice=${choice:-timeout})"
            return 75
            ;;
    esac
}

case "$ACTION" in
    gate)
        consent_gate
        ;;
    on)
        rm -f "$LATER_FILE"
        invert 1
        termux-vibrate -d 400 2>/dev/null
        pulse 3
        termux-notification --id "$NID" --ongoing --alert-once \
            --priority high --icon developer_board \
            --title "🤖 $AGENT is using $LABEL" \
            --content "Automation in progress — started $(date '+%H:%M:%S'). This clears when the run ends." \
            2>/dev/null
        echo "presence ON ($LABEL)"
        ;;
    off)
        invert 0
        termux-notification-remove "$NID" 2>/dev/null
        termux-notification-remove "claude-presence" 2>/dev/null  # legacy id
        pulse 2
        termux-vibrate -d 250 2>/dev/null
        echo "presence OFF ($LABEL)"
        ;;
    resume|clear-pause)
        rm -f "$PAUSE_FILE" "$LATER_FILE"
        echo "presence gate: pause cleared"
        ;;
    *)
        echo "usage: claude-presence.sh on|off|gate [label] [agent] | resume" >&2
        exit 2
        ;;
esac
