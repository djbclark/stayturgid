#!/data/data/com.termux/files/usr/bin/bash
# On-device "an agent is controlling this phone" indicator.
# Deployed to ~/claude-presence.sh on each device; called over SSH/ADB by the
# agent at the start and end of a device session.
#
#   claude-presence.sh on  [label]   # torch+vibrate pulse, then ongoing notification
#   claude-presence.sh off [label]   # torch+vibrate pulse, remove notification
#
# Off the screen surface entirely (torch, vibration, status-bar notification),
# so it never interferes with UI automation or screenshots.

export PATH=/data/data/com.termux/files/usr/bin:$PATH
ACTION="$1"
LABEL="${2:-this phone}"
NID="claude-presence"

pulse() {   # $1 = number of torch blinks
    for _ in $(seq 1 "$1"); do
        termux-torch on  2>/dev/null; sleep 0.25
        termux-torch off 2>/dev/null; sleep 0.20
    done
}

case "$ACTION" in
    on)
        termux-vibrate -d 400 2>/dev/null
        pulse 3
        termux-notification --id "$NID" --ongoing --alert-once \
            --priority high --icon developer_board \
            --title "🤖 Claude is using $LABEL" \
            --content "Automation in progress — started $(date '+%H:%M:%S'). This clears when the run ends." \
            2>/dev/null
        echo "presence ON ($LABEL)"
        ;;
    off)
        termux-notification-remove "$NID" 2>/dev/null
        pulse 2
        termux-vibrate -d 250 2>/dev/null
        echo "presence OFF ($LABEL)"
        ;;
    *)
        echo "usage: claude-presence.sh on|off [label]" >&2
        exit 2
        ;;
esac
