#!/data/data/com.termux/files/usr/bin/bash
# On-device "an agent is controlling this phone" indicator.
# Deployed to ~/claude-presence.sh on each device; called over SSH/ADB by the
# agent at the start and end of a device session.
#
#   claude-presence.sh on  [label] [agent]   # torch+vibrate pulse, then ongoing notification
#   claude-presence.sh off [label] [agent]   # torch+vibrate pulse, remove notification
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
AGENT="${STAYTURGID_AGENT:-${3:-Auto}}"
NID="stayturgid-presence"

invert() {  # $1 = 1|0 — best-effort whole-screen inversion via the 5555 shell
    adb connect localhost:5555 >/dev/null 2>&1 && \
    adb -s localhost:5555 shell \
        "settings put secure accessibility_display_inversion_enabled $1" 2>/dev/null
}

pulse() {   # $1 = number of torch blinks
    for _ in $(seq 1 "$1"); do
        termux-torch on  2>/dev/null; sleep 0.25
        termux-torch off 2>/dev/null; sleep 0.20
    done
}

case "$ACTION" in
    on)
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
    *)
        echo "usage: claude-presence.sh on|off [label] [agent]" >&2
        exit 2
        ;;
esac
