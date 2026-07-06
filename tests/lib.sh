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
  *"dumpsys window"*) printf 'mCurrentFocus=Window{1a2 u0 %s/.Main}\n' "${ADB_FG_PKG:-com.sec.android.app.launcher}"; exit 0 ;;
  *"dumpsys power"*) printf 'mWakefulness=%s\n' "${ADB_WAKE:-Awake}"; exit 0 ;;
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
    cat > "$d/termux-dialog" <<'STUB'
#!/usr/bin/env bash
echo "termux-dialog $*" >> "$STUB_LOG"
if [ -n "${DIALOG_CHOICE:-}" ]; then
    printf '{\n  "code": -1,\n  "text": "%s"\n}\n' "$DIALOG_CHOICE"
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
    printf '#!/usr/bin/env bash\nexit 0\n'                > "$d/sleep"
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
    rm -rf "$SANDBOX/home" "$SANDBOX/sd" "$SANDBOX/sshd_started" "$SANDBOX/batt.json"
    mkdir -p "$SANDBOX/home" "$SANDBOX/sd"
}

# run_sandboxed <script> [args...]: run a repo script inside the sandbox.
# Sets OUT (stdout), ERR (stderr), RC. Never aborts the test file.
run_sandboxed() {
    set +e
    OUT="$(HOME="$SANDBOX/home" PREFIX="$SANDBOX/prefix" \
           TMPDIR="$SANDBOX/prefix/tmp" STAYTURGID_SD="$SANDBOX/sd" \
           PATH="$SANDBOX/stubs:$PATH" bash "$@" 2>"$SANDBOX/err")"
    RC=$?
    ERR="$(cat "$SANDBOX/err" 2>/dev/null)"
    set -e 2>/dev/null || true
    return 0
}

stub_calls() { grep -c "^$1" "$STUB_LOG" 2>/dev/null || true; }
