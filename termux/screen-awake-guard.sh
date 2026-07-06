#!/data/data/com.termux/files/usr/bin/bash
# Screen-awake guard: while the screen is being held awake (stay-on setting,
# an app wakelock like Wakey, or a very long screen_off_timeout), keep a
# notification up offering one tap to restore normal screen lock.
#
# Called with `check` from ~/.termux/boot/start-adb.sh every 5 min, so a
# dismissed notification reappears each cycle for as long as the forced-awake
# state persists (respecting a deliberate keep-awake: just ignore it).
#
#   screen-awake-guard.sh check          # detect + (re)post/remove notification
#   screen-awake-guard.sh restore [ms]   # restore lock: ms arg, saved baseline,
#                                        # or ask with the usual timeout options
#
# Baseline: whenever the screen is NOT forced awake, the current
# screen_off_timeout is remembered so "Restore lock" knows what normal was.

export PATH=/data/data/com.termux/files/usr/bin:$PATH
export TMPDIR="${TMPDIR:-/data/data/com.termux/files/usr/tmp}"

ACTION="${1:-check}"
NID="stayturgid-screenlock"
BASELINE_FILE="$HOME/.stayturgid/screen_timeout_baseline"
MAX_OK_MS=600000   # timeouts above 10 min count as "held awake"

adb_shell() {
    adb connect localhost:5555 >/dev/null 2>&1 </dev/null && \
        adb -s localhost:5555 shell "$@" </dev/null 2>/dev/null | tr -d '\r'
}

get_timeout()  { adb_shell settings get system screen_off_timeout; }
get_stay_on()  { adb_shell settings get global stay_on_while_plugged_in; }

power_dump()   { adb_shell dumpsys power; }

screen_interactive() {
    power_dump | grep -qE 'mWakefulness=Awake|mIsInteractive: true'
}

wakelock_holder() {   # prints the tag of a screen-holding wakelock, if any
    power_dump | grep -oE "SCREEN_(BRIGHT|DIM)_WAKE_LOCK[^)]*'[^']*'" \
        | sed -n "s/.*'\(.*\)'/\1/p" | head -1
}

forced_awake_reason() {   # prints a human reason and returns 0 when forced
    local stay timeout holder
    stay="$(get_stay_on)"
    if power_dump | grep -q 'mStayOn=true' || { [ -n "$stay" ] && [ "$stay" != "0" ]; }; then
        echo "stay-awake-while-plugged setting is on"
        return 0
    fi
    holder="$(wakelock_holder)"
    if [ -n "$holder" ]; then
        echo "app wakelock: $holder"
        return 0
    fi
    timeout="$(get_timeout)"
    if [ -n "$timeout" ] && [ "$timeout" -gt "$MAX_OK_MS" ] 2>/dev/null; then
        echo "screen timeout is $((timeout / 60000)) min"
        return 0
    fi
    return 1
}

save_baseline() {
    local timeout
    timeout="$(get_timeout)"
    if [ -n "$timeout" ] && [ "$timeout" -le "$MAX_OK_MS" ] 2>/dev/null; then
        mkdir -p "$(dirname "$BASELINE_FILE")"
        echo "$timeout" > "$BASELINE_FILE"
    fi
}

fmt_ms() {
    local ms="$1"
    if [ "$ms" -lt 60000 ]; then echo "$((ms / 1000))s"; else echo "$((ms / 60000))m"; fi
}

post_notification() {
    local reason="$1" baseline self
    self="$HOME/screen-awake-guard.sh"
    baseline="$(cat "$BASELINE_FILE" 2>/dev/null)"
    if [ -n "$baseline" ]; then
        termux-notification --id "$NID" --priority high --alert-once \
            --title "Screen is being kept awake" \
            --content "$reason — tap to restore normal lock. Ignore to keep it awake." \
            --button1 "Restore lock ($(fmt_ms "$baseline"))" \
            --button1-action "bash $self restore $baseline" \
            --button2 "Other timeout…" \
            --button2-action "bash $self restore" \
            2>/dev/null
    else
        # Notifications max out at 3 buttons; the timeout choices (1/3/5/10m
        # + full picker) live in the restore dialog instead.
        termux-notification --id "$NID" --priority high --alert-once \
            --title "Screen is being kept awake" \
            --content "$reason — pick a lock timeout to restore. Ignore to keep it awake." \
            --button1 "Set lock timeout…" \
            --button1-action "bash $self restore" \
            2>/dev/null
    fi
}

do_check() {
    local reason
    if reason="$(forced_awake_reason)"; then
        # Only nag while the panel is actually lit.
        if screen_interactive; then
            post_notification "$reason"
        fi
    else
        save_baseline
        termux-notification-remove "$NID" 2>/dev/null
    fi
}

pick_timeout_full() {   # full picker — the usual Android options
    local out
    out="$(termux-dialog radio -t "Restore screen lock after" \
        -v "15 seconds,30 seconds,1 minute,2 minutes,5 minutes,10 minutes,30 minutes" 2>/dev/null)"
    case "$out" in
        *"15 seconds"*) echo 15000 ;;
        *"30 seconds"*) echo 30000 ;;
        *"1 minute"*)   echo 60000 ;;
        *"2 minutes"*)  echo 120000 ;;
        *"5 minutes"*)  echo 300000 ;;
        *"10 minutes"*) echo 600000 ;;
        *"30 minutes"*) echo 1800000 ;;
        *) return 1 ;;
    esac
}

pick_timeout() {        # quick options first, full picker behind Other…
    local out
    out="$(termux-dialog radio -t "Restore screen lock after" \
        -v "1 minute,3 minutes,5 minutes,10 minutes,Other…" 2>/dev/null)"
    case "$out" in
        *"1 minute"*)   echo 60000 ;;
        *"3 minutes"*)  echo 180000 ;;
        *"5 minutes"*)  echo 300000 ;;
        *"10 minutes"*) echo 600000 ;;
        *"Other…"*)     pick_timeout_full ;;
        *) return 1 ;;
    esac
}

do_restore() {
    local ms="${1:-}"
    if [ -z "$ms" ]; then
        if ! ms="$(pick_timeout)" || [ -z "$ms" ]; then
            echo "restore cancelled"
            exit 1
        fi
    fi

    adb_shell settings put system screen_off_timeout "$ms" >/dev/null
    adb_shell settings put global stay_on_while_plugged_in 0 >/dev/null
    adb_shell svc power stayon false >/dev/null
    echo "$ms" > "$BASELINE_FILE" 2>/dev/null

    local holder
    holder="$(wakelock_holder)"
    termux-notification-remove "$NID" 2>/dev/null
    if [ -n "$holder" ]; then
        # Can't release another app's wakelock — tell the user who holds it.
        termux-notification --id "$NID" --priority high \
            --title "Screen lock restored ($(fmt_ms "$ms"))" \
            --content "But '$holder' still holds a wakelock — turn it off in that app." \
            2>/dev/null
        echo "restored timeout=${ms}ms; wakelock holder remains: $holder"
    else
        termux-toast "Screen lock restored ($(fmt_ms "$ms"))" 2>/dev/null
        # Turn the screen off now as tactile confirmation.
        adb_shell input keyevent KEYCODE_SLEEP >/dev/null
        echo "restored timeout=${ms}ms; screen off"
    fi
}

case "$ACTION" in
    check)   do_check ;;
    restore) do_restore "${2:-}" ;;
    *) echo "usage: screen-awake-guard.sh check | restore [ms]" >&2; exit 2 ;;
esac
