#!/data/data/com.termux/files/usr/bin/python
"""Screen-awake guard (Python) — deployed as ~/stayturgid_screen_awake_guard.py.

While the screen is held awake (stay-on setting, an app wakelock like Wakey,
or a very long screen_off_timeout), keep a notification up offering one tap to
restore normal screen lock. Called with `check` every 5 min from the boot loop;
`restore [ms]` applies a timeout. Migrated from screen-awake-guard.sh;
unit-tested via tests/test-unit.sh (guard_suite).
"""
import os
import subprocess
import sys

HOME = os.environ.get("HOME", "")
STG = os.path.join(HOME, ".stayturgid")  # Termux-private root (self-healing)
_ENV_FILE = os.path.join(STG, "env")
if os.path.isfile(_ENV_FILE):
    try:
        with open(_ENV_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("export STAYTURGID_NO_LOCAL_ADB="):
                    os.environ.setdefault(
                        "STAYTURGID_NO_LOCAL_ADB",
                        _line.split("=", 1)[1].strip().strip('"'),
                    )
    except OSError:
        pass

for _p in (
    os.path.join(HOME, ".stayturgid", "lib"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"),
):
    if _p and _p not in sys.path and os.path.isdir(_p):
        sys.path.insert(0, _p)
try:
    import termux_api as tapi  # noqa: E402
except ImportError:
    tapi = None  # type: ignore

NID = "stayturgid-screenlock"
BASELINE_FILE = os.path.join(STG, "state", "screen_timeout_baseline")
MAX_OK_MS = 600000  # timeouts above 10 min count as "held awake"
SELF = os.path.join(STG, "bin", "stayturgid_screen_awake_guard.py")  # notif button target
CMD_TIMEOUT_SEC = 8


def _no_local_adb() -> bool:
    return os.environ.get("STAYTURGID_NO_LOCAL_ADB") == "1"


def run(args, timeout=CMD_TIMEOUT_SEC):
    """Never SIGKILL Termux:API clients (avoids ResultReturner toasts)."""
    if tapi is not None and tapi.is_termux_api(args):
        if tapi.is_fire_and_forget(args):
            return tapi.run_ff(args, timeout=min(float(timeout), 4.0))
        return tapi.run(args, timeout=timeout)
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, start_new_session=True
        )
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        return None


def adb_shell(*cmd):
    # Fire OS: Termux cannot reach localhost:5555 — skip rather than hang.
    if _no_local_adb():
        return ""
    r = run(["adb", "connect", "localhost:5555"], timeout=5)
    if not r or r.returncode != 0:
        return ""
    r = run(["adb", "-s", "localhost:5555", "shell"] + list(cmd))
    return (r.stdout if r else "").replace("\r", "").strip()


def get_timeout():
    return adb_shell("settings", "get", "system", "screen_off_timeout")


def get_stay_on():
    return adb_shell("settings", "get", "global", "stay_on_while_plugged_in")


def power_dump():
    return adb_shell("dumpsys", "power")


def screen_interactive():
    dump = power_dump()
    return "mWakefulness=Awake" in dump or "mIsInteractive: true" in dump


def wakelock_holder():
    for line in power_dump().splitlines():
        if "SCREEN_BRIGHT_WAKE_LOCK" in line or "SCREEN_DIM_WAKE_LOCK" in line:
            # tag is the first single-quoted token
            if "'" in line:
                return line.split("'", 2)[1]
    return ""


def forced_awake_reason():
    """Return a human reason string when the screen is forced awake, else None."""
    stay = get_stay_on()
    if "mStayOn=true" in power_dump() or (stay and stay != "0"):
        return "stay-awake-while-plugged setting is on"
    holder = wakelock_holder()
    if holder:
        return "app wakelock: " + holder
    timeout = get_timeout()
    if timeout.isdigit() and int(timeout) > MAX_OK_MS:
        return "screen timeout is %d min" % (int(timeout) // 60000)
    return None


def save_baseline():
    timeout = get_timeout()
    if timeout.isdigit() and int(timeout) <= MAX_OK_MS:
        os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
        with open(BASELINE_FILE, "w") as f:
            f.write(timeout + "\n")


def read_baseline():
    try:
        with open(BASELINE_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def fmt_ms(ms):
    ms = int(ms)
    return "%ds" % (ms // 1000) if ms < 60000 else "%dm" % (ms // 60000)


def post_notification(reason):
    baseline = read_baseline()
    if baseline:
        run([
            "termux-notification", "--id", NID, "--priority", "high", "--alert-once",
            "--title", "Screen is being kept awake",
            "--content", reason + " — tap to restore normal lock. Ignore to keep it awake.",
            "--button1", "Restore lock (%s)" % fmt_ms(baseline),
            "--button1-action", "python3 %s restore %s" % (SELF, baseline),
            "--button2", "Other timeout…",
            "--button2-action", "python3 %s restore" % SELF,
        ])
    else:
        run([
            "termux-notification", "--id", NID, "--priority", "high", "--alert-once",
            "--title", "Screen is being kept awake",
            "--content", reason + " — pick a lock timeout to restore. Ignore to keep it awake.",
            "--button1", "Set lock timeout…",
            "--button1-action", "python3 %s restore" % SELF,
        ])


def do_check():
    if _no_local_adb():
        # Cannot read stay-on / wakelock via loopback adb on Fire.
        return
    reason = forced_awake_reason()
    if reason is not None:
        if screen_interactive():
            post_notification(reason)
    else:
        save_baseline()
        run(["termux-notification-remove", NID])


def _dialog_choice(values):
    r = run(["termux-dialog", "radio", "-t", "Restore screen lock after", "-v", values])
    return r.stdout if r else ""


def pick_timeout_full():
    out = _dialog_choice("15 seconds,30 seconds,1 minute,2 minutes,5 minutes,10 minutes,30 minutes")
    for needle, ms in (
        ("15 seconds", 15000), ("30 seconds", 30000), ("1 minute", 60000),
        ("2 minutes", 120000), ("5 minutes", 300000), ("10 minutes", 600000),
        ("30 minutes", 1800000),
    ):
        if needle in out:
            return ms
    return None


def pick_timeout():
    out = _dialog_choice("1 minute,3 minutes,5 minutes,10 minutes,Other…")
    for needle, ms in (
        ("1 minute", 60000), ("3 minutes", 180000),
        ("5 minutes", 300000), ("10 minutes", 600000),
    ):
        if needle in out:
            return ms
    if "Other" in out:
        return pick_timeout_full()
    return None


def do_restore(ms):
    if not ms:
        ms = pick_timeout()
        if not ms:
            print("restore cancelled")
            sys.exit(1)
    ms = str(ms)

    adb_shell("settings", "put", "system", "screen_off_timeout", ms)
    adb_shell("settings", "put", "global", "stay_on_while_plugged_in", "0")
    adb_shell("svc", "power", "stayon", "false")
    try:
        os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
        with open(BASELINE_FILE, "w") as f:
            f.write(ms)
    except OSError:
        pass

    holder = wakelock_holder()
    run(["termux-notification-remove", NID])
    if holder:
        run([
            "termux-notification", "--id", NID, "--priority", "high",
            "--title", "Screen lock restored (%s)" % fmt_ms(ms),
            "--content", "But '%s' still holds a wakelock — turn it off in that app." % holder,
        ])
        print("restored timeout=%sms; wakelock holder remains: %s" % (ms, holder))
    else:
        run(["termux-toast", "Screen lock restored (%s)" % fmt_ms(ms)])
        adb_shell("input", "keyevent", "KEYCODE_SLEEP")
        print("restored timeout=%sms; screen off" % ms)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    if action == "check":
        do_check()
    elif action == "restore":
        do_restore(sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        sys.stderr.write("usage: stayturgid_screen_awake_guard.py check | restore [ms]\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
