#!/data/data/com.termux/files/usr/bin/bash
# Low-battery tier alerts for stayturgid fleet.
# Called from ~/.termux/boot/start-adb.sh every 5 min.
#
# Fires once per tier while discharging: 30, 25, 20, 15, 10, 5, then each % below 5.
# Only the lowest applicable tier fires (no catch-up cascade when starting low);
# higher tiers are marked as already alerted.
# Each tier: colored screen blink(s), optional torch (15% and below), notification.
# During DND / silent ringer: screen (+ single quick torch from 15%) only — no toast/vibrate/sound.

set -euo pipefail
export PATH=/data/data/com.termux/files/usr/bin:$PATH

STATE_FILE="$HOME/.stayturgid_batt_alerted"
COLOR_DIR="$HOME/.stayturgid/battery-colors"
WALLPAPER_BACKUP="$HOME/.stayturgid/wallpaper-backup.png"
SAVED_BRIGHT_FILE="$HOME/.stayturgid/batt_saved_brightness"

adb_shell() {
    adb connect localhost:5555 >/dev/null 2>&1 && adb -s localhost:5555 shell "$@" 2>/dev/null
}

dnd_or_sleep_quiet() {
    local zen ringer
    zen="$(adb_shell settings get global zen_mode 2>/dev/null | tr -d '\r')"
    case "$zen" in
        1|2|3) return 0 ;;
    esac
    # Interruption filter from notification service (bedtime / DND schedules)
    if adb_shell dumpsys notification 2>/dev/null | grep -qE 'mInterruptionFilter=(PRIORITY|ALARMS|NONE)'; then
        return 0
    fi
    # Fully silent ringer (no vibrate) counts as sleep-quiet
    ringer="$(adb_shell cmd audio get-ringer-mode 2>/dev/null | tr -d '\r')"
    [ "$ringer" = "0" ] && return 0
    return 1
}

already_alerted() {
    [ -f "$STATE_FILE" ] && grep -qx "$1" "$STATE_FILE" 2>/dev/null
}

mark_alerted() {
    mkdir -p "$(dirname "$STATE_FILE")"
    already_alerted "$1" || echo "$1" >> "$STATE_FILE"
}

clear_alert_state() {
    if [ -f "$STATE_FILE" ]; then
        # An alert ran (or was killed mid-blink): put the screen back, then
        # drop the snapshots so the next alert cycle re-captures fresh ones.
        restore_wallpaper
        restore_brightness
        rm -f "$WALLPAPER_BACKUP" "$SAVED_BRIGHT_FILE" "$STATE_FILE"
    fi
    termux-notification-remove stayturgid-batt 2>/dev/null || true
}

tier_color() {
    case "$1" in
        30) echo purple ;;
        25) echo blue ;;
        20) echo green ;;
        15) echo yellow ;;
        10) echo orange ;;
        5|4|3|2|1|0) echo red ;;
        *) echo red ;;
    esac
}

tier_blinks() {
    case "$1" in
        30) echo 1 ;;
        25) echo 2 ;;
        20) echo 3 ;;
        15) echo 4 ;;
        10) echo 5 ;;
        5|4|3|2|1|0) echo 10 ;;
        *) echo 1 ;;
    esac
}

save_brightness() {
    mkdir -p "$(dirname "$SAVED_BRIGHT_FILE")"
    adb_shell settings get system screen_brightness 2>/dev/null | tr -d '\r' > "$SAVED_BRIGHT_FILE" || true
}

restore_brightness() {
    local b
    [ -f "$SAVED_BRIGHT_FILE" ] || return 0
    b="$(cat "$SAVED_BRIGHT_FILE" 2>/dev/null | tr -d '\r')"
    [ -n "$b" ] && termux-brightness "$b" 2>/dev/null || true
}

wallpaper_backup_valid() {
    # PNG or JPEG magic bytes — anything else means the capture failed or was
    # mangled; treat as no backup.
    local magic
    [ -s "$WALLPAPER_BACKUP" ] || return 1
    magic="$(head -c 3 "$WALLPAPER_BACKUP" 2>/dev/null | od -An -tx1 | tr -d ' \n')"
    [ "$magic" = "89504e" ] || [ "$magic" = "ffd8ff" ]
}

backup_wallpaper_once() {
    [ -f "$WALLPAPER_BACKUP" ] && return 0
    mkdir -p "$(dirname "$WALLPAPER_BACKUP")"
    # exec-out keeps the image byte-exact; plain `adb shell` can mangle binary.
    if adb connect localhost:5555 >/dev/null 2>&1; then
        adb -s localhost:5555 exec-out cmd wallpaper get-image > "$WALLPAPER_BACKUP" 2>/dev/null || true
    fi
    wallpaper_backup_valid || rm -f "$WALLPAPER_BACKUP"
}

restore_wallpaper() {
    [ -f "$WALLPAPER_BACKUP" ] && termux-wallpaper -f "$WALLPAPER_BACKUP" 2>/dev/null || true
}

blink_screen_color() {
  # $1=color name  $2=blink count  $3=quiet (dnd)
    local color="$1" count="$2" quiet="${3:-0}"
    local png="$COLOR_DIR/${color}.png"
    local black="$COLOR_DIR/black.png"
    local on_ms=0.35 off_ms=0.20 use_wallpaper=0

    [ "$quiet" -eq 1 ] && { on_ms=0.18; off_ms=0.10; }

    # Only swap the wallpaper when we hold a verified backup of the original —
    # otherwise an interrupted blink (or failed get-image: live wallpapers,
    # 5555 down) would permanently replace the user's wallpaper. Without a
    # backup, blink via brightness only.
    backup_wallpaper_once
    if [ -f "$png" ] && wallpaper_backup_valid; then
        use_wallpaper=1
    fi

    save_brightness
    adb_shell input keyevent KEYCODE_WAKEUP 2>/dev/null || true

    local i
    for i in $(seq 1 "$count"); do
        termux-brightness 255 2>/dev/null || true
        if [ "$use_wallpaper" -eq 1 ]; then
            termux-wallpaper -f "$png" 2>/dev/null || true
        fi
        sleep "$on_ms"
        if [ "$use_wallpaper" -eq 1 ] && [ -f "$black" ]; then
            termux-wallpaper -f "$black" 2>/dev/null || true
        fi
        termux-brightness 32 2>/dev/null || true
        sleep "$off_ms"
    done

    if [ "$use_wallpaper" -eq 1 ]; then
        restore_wallpaper
    fi
    restore_brightness
}

pulse_torch() {
  # $1=blinks  $2=quiet (single fast flash)
    local n="$1" quiet="${2:-0}"
    if [ "$quiet" -eq 1 ]; then
        termux-torch on 2>/dev/null || true
        sleep 0.06
        termux-torch off 2>/dev/null || true
        return 0
    fi
    local i
    for i in $(seq 1 "$n"); do
        termux-torch on 2>/dev/null || true
        sleep 0.22
        termux-torch off 2>/dev/null || true
        sleep 0.18
    done
}

fire_tier_alert() {
  # $1=tier percent  $2=current pct  $3=quiet
    local tier="$1" pct="$2" quiet="$3"
    local color blinks

    color="$(tier_color "$tier")"
    blinks="$(tier_blinks "$tier")"

    blink_screen_color "$color" "$blinks" "$quiet"

    if [ "$tier" -le 15 ]; then
        if [ "$quiet" -eq 1 ]; then
            pulse_torch 1 1
        else
            pulse_torch "$blinks" 0
        fi
    fi

    if [ "$quiet" -eq 0 ]; then
        termux-notification --id stayturgid-batt --priority max --ongoing \
            --title "⚠ stayturgid: battery ${pct}% (tier ${tier}%)" \
            --content "Not charging — remote access dies when this powers off. Plug in a charger." \
            2>/dev/null || true
        termux-toast "stayturgid: battery ${pct}% — plug in! (tier ${tier}%)" 2>/dev/null || true
        termux-vibrate -d 400 2>/dev/null || true
    else
        # Silent notification record (no sound/vibrate); screen already blinked.
        termux-notification --id stayturgid-batt --priority max --ongoing --alert-once \
            --title "⚠ stayturgid: battery ${pct}% (tier ${tier}%)" \
            --content "Not charging — plug in. (quiet hours: screen/torch only)" \
            2>/dev/null || true
    fi
}

main() {
    local batt pct status quiet=0 tier lowest="" t
    local applicable=()

    batt="$(termux-battery-status 2>/dev/null || true)"
    [ -n "$batt" ] || exit 0

    pct="$(echo "$batt" | grep -o '"percentage": *[0-9]*' | grep -o '[0-9]*' | head -1 || true)"
    status="$(echo "$batt" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4 || true)"
    [ -n "$pct" ] || exit 0

    if [ "$status" = "CHARGING" ] || [ "$status" = "FULL" ]; then
        clear_alert_state
        exit 0
    fi

    if [ "$pct" -gt 30 ]; then
        clear_alert_state
        exit 0
    fi

    dnd_or_sleep_quiet && quiet=1 || true

    # Tiers are descending, so applicable tiers (pct <= tier) form a prefix;
    # the last one collected is the lowest. Fire only that one, mark them all.
    for tier in 30 25 20 15 10 5 4 3 2 1 0; do
        if [ "$pct" -le "$tier" ]; then
            applicable+=("$tier")
            lowest="$tier"
        fi
    done
    [ -n "$lowest" ] || exit 0

    if ! already_alerted "$lowest"; then
        fire_tier_alert "$lowest" "$pct" "$quiet"
        for t in "${applicable[@]}"; do
            mark_alerted "$t"
        done
    fi
}

main "$@"
