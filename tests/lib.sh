#!/usr/bin/env bash
# Shared test helpers: TAP output + a sandbox with stubbed device commands.
# TAP (Test Anything Protocol): "ok N - desc" / "not ok N - desc", plan "1..N".
# Works on macOS /bin/bash 3.2 (no associative arrays, no mapfile).

TESTS_RUN=0
TESTS_FAILED=0

tap_ok()   { TESTS_RUN=$((TESTS_RUN + 1)); echo "ok $TESTS_RUN - $1"; }
tap_fail() {
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo "not ok $TESTS_RUN - $1"
    [ -n "${2:-}" ] && echo "# $2"
}
tap_skip() { TESTS_RUN=$((TESTS_RUN + 1)); echo "ok $TESTS_RUN - $1 # SKIP ${2:-}"; }
tap_todo_fail() {  # expected failure (doesn't fail the run) — e.g. known drift
    TESTS_RUN=$((TESTS_RUN + 1)); echo "not ok $TESTS_RUN - $1 # TODO ${2:-}"
}
tap_is()     { if [ "$1" = "$2" ]; then tap_ok "$3"; else tap_fail "$3" "got '$1', want '$2'"; fi; }
tap_like()   { if printf '%s' "$1" | grep -qF -- "$2"; then tap_ok "$3"; else tap_fail "$3" "missing '$2' in: $(printf '%s' "$1" | head -3)"; fi; }
tap_unlike() { if printf '%s' "$1" | grep -qF -- "$2"; then tap_fail "$3" "unexpectedly contains '$2'"; else tap_ok "$3"; fi; }
tap_done()   { echo "1..$TESTS_RUN"; [ "$TESTS_FAILED" -eq 0 ]; }

# ---------------------------------------------------------------------------
# make_sandbox: tmpdir with home/, sd/, prefix/tmp/, stubs/ for termux-*, adb,
# pgrep, ss, flock, sleep, curl, timeout, sshd. Stubs append to $STUB_LOG and
# are steered by env vars (ADB_*, PGREP_RC, SS_RC, FLOCK_RC, DIALOG_CHOICE,
# CURL_RC/CURL_BODY). Call once per test group; reset_sandbox between cases.
# ---------------------------------------------------------------------------
make_sandbox() {
    SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/stayturgid-test.XXXXXX")"
    export SANDBOX
    REAL_PYTHON3="$(command -v python3)"
    export REAL_PYTHON3
    mkdir -p "$SANDBOX/home" "$SANDBOX/sd" "$SANDBOX/prefix/tmp" "$SANDBOX/stubs"
    export STUB_LOG="$SANDBOX/calls.log"
    : > "$STUB_LOG"
    local d="$SANDBOX/stubs" c

    for c in termux-notification termux-toast termux-vibrate termux-torch \
             termux-brightness termux-wallpaper termux-notification-remove \
             termux-wake-lock; do
        printf '#!/usr/bin/env bash\necho "%s $*" >> "$STUB_LOG"\nexit 0\n' "$c" > "$d/$c"
    done

    cat > "$d/adb" <<'STUB'
#!/usr/bin/env bash
echo "adb $*" >> "$STUB_LOG"
case "$*" in
  connect*) exit "${ADB_CONNECT_RC:-0}" ;;
  *"exec-out cmd wallpaper get-image"*)
      [ -n "${ADB_WALLPAPER_FILE:-}" ] && cat "$ADB_WALLPAPER_FILE"
      exit 0 ;;
  *"shell id -u"*) printf '%s\n' "${ADB_SHELL_UID-2000}"; exit 0 ;;
  *shizuku_server*) exit "${ADB_SHIZUKU_RC:-0}" ;;
  *"settings get global zen_mode"*) printf '%s\n' "${ADB_ZEN:-0}"; exit 0 ;;
  *"dumpsys notification"*) printf 'mInterruptionFilter=%s\n' "${ADB_INTERRUPT:-ALL}"; exit 0 ;;
  *"cmd audio get-ringer-mode"*) printf '%s\n' "${ADB_RINGER:-2}"; exit 0 ;;
  *"settings get system screen_brightness"*) printf '128\n'; exit 0 ;;
  *"settings put secure enabled_accessibility_services"*)
      j="$*"   # ${*##...} would apply the pattern per-arg, not to the join
      v="${j##*enabled_accessibility_services }"
      v="${v#\'}"; v="${v%\'}"
      printf '%s' "$v" > "$SANDBOX/a11y_state"
      exit 0 ;;
  *"settings get secure enabled_accessibility_services"*)
      if [ -f "$SANDBOX/a11y_state" ]; then cat "$SANDBOX/a11y_state"; echo
      else printf '%s\n' "${ADB_A11Y:-org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher}"; fi
      exit 0 ;;
  *"settings get system screen_off_timeout"*) printf '%s\n' "${ADB_TIMEOUT:-60000}"; exit 0 ;;
  *"settings get global stay_on_while_plugged_in"*) printf '%s\n' "${ADB_STAYON:-0}"; exit 0 ;;
  *"settings get global adb_wifi_enabled"*)
      if [ -f "$SANDBOX/adb_wifi_state" ]; then cat "$SANDBOX/adb_wifi_state"; echo
      else printf '%s\n' "${ADB_WIFI:-1}"; fi
      exit 0 ;;
  *"settings put global adb_wifi_enabled"*)
      echo "1" > "$SANDBOX/adb_wifi_state"
      exit 0 ;;
  *"dumpsys window"*) printf 'mCurrentFocus=Window{1a2 u0 %s/.Main}\n' "${ADB_FG_PKG:-com.sec.android.app.launcher}"; exit 0 ;;
  *"dumpsys power"*)
      printf 'mWakefulness=%s\nmStayOn=%s\n' "${ADB_WAKE:-Awake}" "${ADB_MSTAYON:-false}"
      [ -n "${ADB_WAKELOCK:-}" ] && printf "  SCREEN_BRIGHT_WAKE_LOCK (tag='%s' uid=10123)\n" "$ADB_WAKELOCK"
      exit 0 ;;
esac
exit 0
STUB

    cat > "$d/termux-battery-status" <<'STUB'
#!/usr/bin/env bash
[ -f "$SANDBOX/batt.json" ] && cat "$SANDBOX/batt.json"
exit 0
STUB

    # Multiline JSON like the real termux-dialog: the consumer awk expects
    # "text": "..." on its own line (field 4 with FS='"').
    # Answers come from DIALOG_CHOICE, or one per call from $SANDBOX/dialog_queue
    # (first line consumed each call) when multi-dialog flows need different answers.
    cat > "$d/termux-dialog" <<'STUB'
#!/usr/bin/env bash
echo "termux-dialog $*" >> "$STUB_LOG"
choice="${DIALOG_CHOICE:-}"
if [ -s "$SANDBOX/dialog_queue" ]; then
    choice="$(head -1 "$SANDBOX/dialog_queue")"
    tail -n +2 "$SANDBOX/dialog_queue" > "$SANDBOX/dialog_queue.t" && \
        mv "$SANDBOX/dialog_queue.t" "$SANDBOX/dialog_queue"
fi
if [ -n "$choice" ]; then
    printf '{\n  "code": -1,\n  "text": "%s"\n}\n' "$choice"
fi
exit 0
STUB

    # timeout: drop the duration, run the command (macOS has no timeout(1))
    printf '#!/usr/bin/env bash\nshift\nexec "$@"\n' > "$d/timeout"
    # pgrep: sshd counts as up once the sshd stub has "started" it
    cat > "$d/pgrep" <<'STUB'
#!/usr/bin/env bash
[ -f "$SANDBOX/sshd_started" ] && exit 0
exit "${PGREP_RC:-1}"
STUB
    cat > "$d/sshd" <<'STUB'
#!/usr/bin/env bash
echo "sshd" >> "$STUB_LOG"
touch "$SANDBOX/sshd_started"
exit 0
STUB
    printf '#!/usr/bin/env bash\nexit "${SS_RC:-1}"\n'    > "$d/ss"
    printf '#!/usr/bin/env bash\nexit "${SS_RC:-1}"\n'    > "$d/netstat"
    printf '#!/usr/bin/env bash\nexit "${FLOCK_RC:-0}"\n' > "$d/flock"
    printf '#!/usr/bin/env bash\n/bin/sleep "${SANDBOX_SLEEP_SECS:-0}"\nexit 0\n' > "$d/sleep"
    cat > "$d/am" <<'STUB'
#!/usr/bin/env bash
echo "am $*" >> "$STUB_LOG"
exit 0
STUB
    cat > "$d/python3" <<'STUB'
#!/usr/bin/env bash
echo "python3 $*" >> "$STUB_LOG"
exit 0
STUB
    cat > "$d/nohup" <<'STUB'
#!/usr/bin/env bash
echo "nohup $*" >> "$STUB_LOG"
cmd="$1"
shift
case "$cmd" in
  *.sh) bash "$cmd" "$@" & ;;
  *) [ -n "$cmd" ] && "$cmd" "$@" & ;;
esac
exit 0
STUB
    cat > "$d/date" <<'STUB'
#!/usr/bin/env bash
echo "1700000000"
exit 0
STUB
    cat > "$d/curl" <<'STUB'
#!/usr/bin/env bash
echo "curl $*" >> "$STUB_LOG"
rc="${CURL_RC:-0}"
[ "$rc" = 0 ] && printf '%s' "${CURL_BODY:-}"
exit "$rc"
STUB
    chmod +x "$d"/*
}

reset_sandbox() {
    : > "$STUB_LOG"
    rm -rf "${SANDBOX:?}/home" "${SANDBOX:?}/sd" "${SANDBOX:?}/sshd_started" \
           "${SANDBOX:?}/batt.json" "${SANDBOX:?}/a11y_state" "${SANDBOX:?}/adb_wifi_state" "${SANDBOX:?}/proc"
    mkdir -p "$SANDBOX/home" "$SANDBOX/sd"
}

# Kill a background pid recorded in the sandbox (boot loops, bridge listeners).
kill_sandbox_pid() {
    local pf="$1"
    [ -f "$pf" ] || return 0
    local pid
    pid="$(tr -dc '0-9' < "$pf" 2>/dev/null || true)"
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
    rm -f "$pf"
}

# Wait up to ~2s for a sandbox pidfile to appear (async boot/bridge starters).
wait_sandbox_pidfile() {
    local pf="$1" n=0
    while [ "$n" -lt 20 ] && [ ! -f "$pf" ]; do
        sleep 0.1
        n=$((n + 1))
    done
    [ -f "$pf" ]
}

wait_stub_like() {
    local pattern="$1" n=0
    while [ "$n" -lt 30 ]; do
        grep -qF -- "$pattern" "$STUB_LOG" 2>/dev/null && return 0
        sleep 0.1
        n=$((n + 1))
    done
    return 1
}

# Shared env for sandboxed script runs (env(1) avoids SC2097/2098).
_sandbox_env() {
    env \
        HOME="$SANDBOX/home" \
        PREFIX="$SANDBOX/prefix" \
        TMPDIR="$SANDBOX/prefix/tmp" \
        STAYTURGID_SD="$SANDBOX/sd" \
        SANDBOX="$SANDBOX" \
        STUB_LOG="$STUB_LOG" \
        SANDBOX_SLEEP_SECS="${SANDBOX_SLEEP_SECS:-}" \
        PROC_ROOT="${PROC_ROOT:-}" \
        PATH="$SANDBOX/stubs:$PATH" \
        "$@"
}

# Run a script that loops forever; perl alarm stops it after <seconds>.
run_sandboxed_alarm() {
    local secs=$1; shift
    local interp=bash
    case "$1" in *.py) interp="${REAL_PYTHON3:-python3}" ;; esac
    set +e
    _sandbox_env perl -e 'alarm shift; exec @ARGV' "$secs" "$interp" "$@" \
        >"$SANDBOX/out" 2>/dev/null
    RC=$?
    OUT="$(cat "$SANDBOX/out" 2>/dev/null)"
    ERR="$(cat "$SANDBOX/err" 2>/dev/null)"
    set -e 2>/dev/null || true
    return 0
}

# run_sandboxed <script> [args...]: run a repo script inside the sandbox.
# Sets OUT (stdout), ERR (stderr), RC for the sourcing test file.
# *.py runs under python3 — the same suite exercises shell and Python twins
# to prove behavioral parity during language migrations.
# shellcheck disable=SC2034
run_sandboxed() {
    local interp=bash
    case "$1" in *.py) interp="${REAL_PYTHON3:-python3}" ;; esac
    set +e
    _sandbox_env "$interp" "$@" >"$SANDBOX/out" 2>"$SANDBOX/err"
    RC=$?
    OUT="$(cat "$SANDBOX/out" 2>/dev/null)"
    ERR="$(cat "$SANDBOX/err" 2>/dev/null)"
    set -e 2>/dev/null || true
    return 0
}

stub_calls() { grep -c "^$1" "$STUB_LOG" 2>/dev/null || true; }
