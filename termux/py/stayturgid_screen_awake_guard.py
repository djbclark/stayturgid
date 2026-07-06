#!/data/data/com.termux/files/usr/bin/python
"""Screen-awake guard — Python twin of ../screen-awake-guard.sh.

While the screen is held awake (stay-on setting, an app wakelock like Wakey,
or a very long screen_off_timeout), keep a notification up offering one tap to
restore normal screen lock. Called with `check` every 5 min from the boot loop;
`restore [ms]` applies a timeout. Behavioral parity with the shell version is
enforced by tests/test-unit.sh (guard_suite run against both). Shell stays
deployed until parity soaks.
"""
import os
import subprocess
import sys

HOME = os.environ.get("HOME", "")
NID = "stayturgid-screenlock"
BASELINE_FILE = os.path.join(HOME, ".stayturgid", "screen_timeout_baseline")
MAX_OK_MS = 600000  # timeouts above 10 min count as "held awake"
SELF = os.path.join(HOME, "screen-awake-guard.sh")  # notification button target


def run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except OSError:
        return None


def adb_shell(*cmd):
    r = run(["adb", "connect", "localhost:5555"])
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
            "--button1-action", "bash %s restore %s" % (SELF, baseline),
            "--button2", "Other timeout…",
            "--button2-action", "bash %s restore" % SELF,
        ])
    else:
        run([
            "termux-notification", "--id", NID, "--priority", "high", "--alert-once",
            "--title", "Screen is being kept awake",
            "--content", reason + " — pick a lock timeout to restore. Ignore to keep it awake.",
            "--button1", "Set lock timeout…",
            "--button1-action", "bash %s restore" % SELF,
        ])


def do_check():
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
        sys.stderr.write("usage: screen-awake-guard.py check | restore [ms]\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
