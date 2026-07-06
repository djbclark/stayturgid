#!/data/data/com.termux/files/usr/bin/bash
# On-device "an agent is controlling this phone" indicator.
# Deployed to ~/agent-presence.sh on each device; called over SSH/ADB by the
# agent at the start and end of a device session.
#
#   agent-presence.sh on  [label] [agent]   # torch+vibrate pulse, then ongoing notification
#   agent-presence.sh off [label] [agent]   # torch+vibrate pulse, remove notification
#   agent-presence.sh gate [label] [agent]   # consent gate if phone appears in use
#   agent-presence.sh resume                 # clear a previous Pause choice
#
# Screen-control sessions (agent will drive the display):
#   agent-presence.sh request-screen [label] [agent]
#       Modal dialog with a 60s countdown; exit 0 = allowed (or timed out),
#       75 = user pressed Disallow. Run BEFORE taking the screen, then `on`.
#   agent-presence.sh stop-requested
#       Exit 0 when the user tapped "Graceful stop" on the running
#       notification — the agent has ~1 minute to wrap up, then run `off`.
#   agent-presence.sh off
#       Also: if a graceful stop was requested, pops a modal "released"
#       dialog so the user knows the screen is theirs again.
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
STOP_FILE="$SD/stayturgid_stop_requested"

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
        echo "presence gate: paused (run agent-presence.sh resume to clear)"
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
                --content "Run agent-presence.sh resume to clear." 2>/dev/null
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

request_screen() {
    if pause_active; then
        echo "request-screen: paused (run agent-presence.sh resume to clear)"
        return 75
    fi
    termux-vibrate -d 300 2>/dev/null
    # Modal system dialog (stays on top until answered); auto-continues on
    # the 60s timeout — the minute is the user's window to Disallow.
    local out
    out="$(timeout 60 termux-dialog confirm \
        -t "$AGENT wants to CONTROL THE SCREEN of $LABEL" \
        -i "Starting in 60 seconds. Press No to disallow, Yes to start now." \
        2>/dev/null || true)"
    if printf '%s\n' "$out" | awk -F '"' '/text/ { print $4; exit }' | grep -qi '^no$'; then
        echo "request-screen: DISALLOWED by user"
        return 75
    fi
    rm -f "$STOP_FILE"
    echo "request-screen: allowed (answer or 60s timeout)"
    return 0
}

case "$ACTION" in
    gate)
        consent_gate
        ;;
    request-screen)
        request_screen
        ;;
    stop-requested)
        if [ -f "$STOP_FILE" ]; then
            echo "graceful stop requested — wrap up within ~1 minute, then run: agent-presence.sh off"
            exit 0
        fi
        echo "no stop requested"
        exit 1
        ;;
    on)
        rm -f "$LATER_FILE" "$STOP_FILE"
        invert 1
        termux-vibrate -d 400 2>/dev/null
        pulse 3
        termux-notification --id "$NID" --ongoing --alert-once \
            --priority high --icon developer_board \
            --title "🤖 $AGENT is using $LABEL" \
            --content "Automation in progress — started $(date '+%H:%M:%S'). Graceful stop gives the agent ~1 min to wrap up." \
            --button1 "Graceful stop" \
            --button1-action "mkdir -p $SD 2>/dev/null; touch $STOP_FILE; termux-toast 'Stop requested — agent wrapping up (~1 min)'" \
            2>/dev/null
        echo "presence ON ($LABEL)"
        ;;
    off)
        stopped=0
        [ -f "$STOP_FILE" ] && stopped=1
        invert 0
        termux-notification-remove "$NID" 2>/dev/null
        termux-notification-remove "claude-presence" 2>/dev/null  # legacy id
        pulse 2
        termux-vibrate -d 250 2>/dev/null
        rm -f "$STOP_FILE"
        if [ "$stopped" -eq 1 ]; then
            # Modal handoff-back dialog; backgrounded so `off` returns while
            # the dialog stays on screen until the user acts on it.
            nohup termux-dialog confirm \
                -t "$AGENT has released $LABEL" \
                -i "Screen control ended after your stop request. The phone is all yours." \
                >/dev/null 2>&1 &
        fi
        if [ "$stopped" -eq 1 ]; then
            echo "presence OFF ($LABEL) — graceful stop honored"
        else
            echo "presence OFF ($LABEL)"
        fi
        ;;
    resume|clear-pause)
        rm -f "$PAUSE_FILE" "$LATER_FILE"
        echo "presence gate: pause cleared"
        ;;
    *)
        echo "usage: agent-presence.sh on|off|gate|request-screen|stop-requested [label] [agent] | resume" >&2
        exit 2
        ;;
esac
