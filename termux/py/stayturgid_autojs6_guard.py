#!/data/data/com.termux/files/usr/bin/python
"""AutoJs6 watchdog observer — no RunIntentActivity from the 5-min boot loop.

Termux stayturgid-repair owns routine self-heal. When main.js stalls while
repair is healthy, this script logs, arms autojs6-bridge (trigger file), and
optionally notifies the operator (rate-limited).
"""
import datetime
import os
import subprocess
import sys
import time

os.environ["PATH"] = "/data/data/com.termux/files/usr/bin:" + os.environ.get("PATH", "")
HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
_ENV_FILE = os.path.join(HOME, ".stayturgid", "env")
if os.path.isfile(_ENV_FILE):
    try:
        with open(_ENV_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("export STAYTURGID_SD="):
                    os.environ["STAYTURGID_SD"] = _line.split("=", 1)[1].strip().strip('"')
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

SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")
LOG = os.path.join(SD, "logs", "watchdog.log")
STATE = os.path.join(HOME, ".stayturgid", "state")
NOTIFY_STAMP = os.path.join(STATE, "last_autojs6_stale_notify")
WATCHDOG_STALE_SEC = 45 * 60
REPAIR_FRESH_SEC = 20 * 60
NOTIFY_COOLDOWN_SEC = 86400
RESTART_COOLDOWN_SEC = 30 * 60
RESTART_STAMP = os.path.join(STATE, "last_autojs6_restart_trigger")
TRIGGER = os.path.join(SD, "run", "start_autojs6_now")
TRIGGER_SDCARD = "/sdcard/stayturgid/run/start_autojs6_now"


def run(args):
    if tapi is not None and tapi.is_termux_api(args):
        return tapi.run_ff(args, timeout=4.0) if tapi.is_fire_and_forget(args) else tapi.run(args)
    try:
        return subprocess.run(
            args, capture_output=True, text=True, start_new_session=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def parse_ts(line):
    try:
        return datetime.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def latest_line_marker(path, marker):
    if not os.path.isfile(path):
        return None, None
    last = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if marker in line:
                    last = line
    except OSError:
        return None, None
    if not last:
        return None, None
    return parse_ts(last), last


def append_log(line):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (ts, line))
    except OSError:
        pass


def maybe_notify():
    now = int(time.time())
    last = 0
    if os.path.isfile(NOTIFY_STAMP):
        try:
            last = int(open(NOTIFY_STAMP).read().strip() or "0")
        except (OSError, ValueError):
            last = 0
    if now - last < NOTIFY_COOLDOWN_SEC:
        return
    run([
        "termux-notification", "--id", "stayturgid-autojs6-stale",
        "--priority", "default", "--alert-once",
        "--title", "stayturgid: AutoJs6 watchdog stalled",
        "--content",
        "Termux repair is healthy but main.js has not cycled in 45+ min. "
        "Mac fleet-health should restart main.js; if this persists, reboot.",
    ])
    os.makedirs(STATE, exist_ok=True)
    try:
        with open(NOTIFY_STAMP, "w") as fh:
            fh.write(str(now))
    except OSError:
        pass


def maybe_restart_trigger():
    """Arm autojs6-bridge (trigger file) — not RunIntentActivity from boot loop."""
    now = int(time.time())
    last = 0
    if os.path.isfile(RESTART_STAMP):
        try:
            last = int(open(RESTART_STAMP).read().strip() or "0")
        except (OSError, ValueError):
            last = 0
    if now - last < RESTART_COOLDOWN_SEC:
        return
    os.makedirs(os.path.dirname(TRIGGER), exist_ok=True)
    os.makedirs(os.path.dirname(TRIGGER_SDCARD), exist_ok=True)
    try:
        with open(TRIGGER, "w", encoding="utf-8") as fh:
            fh.write(str(now))
        with open(TRIGGER_SDCARD, "w", encoding="utf-8") as fh:
            fh.write(str(now))
    except OSError:
        return
    os.makedirs(STATE, exist_ok=True)
    try:
        with open(RESTART_STAMP, "w") as fh:
            fh.write(str(now))
    except OSError:
        pass
    append_log("[termux] autojs6 guard: armed start_autojs6_now for bridge")


def action_check():
    cycle_ts, _cycle = latest_line_marker(LOG, "[watchdog] cycle start")
    repair_ts, _repair = latest_line_marker(LOG, "[repair] STATUS")
    now = datetime.datetime.now()

    if cycle_ts is None:
        append_log("[termux] autojs6 guard: no watchdog cycle in log yet")
        return 0

    cycle_age = (now - cycle_ts).total_seconds()
    repair_age = (now - repair_ts).total_seconds() if repair_ts else 999999

    if cycle_age < WATCHDOG_STALE_SEC:
        return 0

    append_log(
        "[termux] autojs6 guard: watchdog stale %.0fs (repair_age=%.0fs)"
        % (cycle_age, repair_age)
    )

    if repair_ts and repair_age < REPAIR_FRESH_SEC:
        maybe_restart_trigger()
        maybe_notify()
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    action = argv[0] if argv else "check"
    if action == "check":
        return action_check()
    sys.stderr.write("usage: stayturgid_autojs6_guard.py check\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
