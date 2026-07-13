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

import stayturgid_shell as sh  # noqa: E402

sh.ensure_lib_path()
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
    markers = (marker,) if isinstance(marker, str) else tuple(marker)
    if not os.path.isfile(path):
        return None, None
    last = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if all(item in line for item in markers):
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


def _read_int(path, default=0):
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip() or default)
    except (OSError, ValueError):
        return default


def maybe_notify():
    now = int(time.time())
    last = _read_int(NOTIFY_STAMP) if os.path.isfile(NOTIFY_STAMP) else 0
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
        with open(NOTIFY_STAMP, "w", encoding="utf-8") as fh:
            fh.write(str(now))
    except OSError:
        pass


def maybe_restart_trigger():
    """Restart AutoJs6 watchdog directly via am start from Termux.

    The bridge (autojs6-bridge.sh) was removed in the 2026-07-10 restructure.
    When port 5555 is down, the boot loop's RunIntentActivity path can't fire.
    Termux am start works without ADB and restarts main.js immediately.
    """
    now = int(time.time())
    last = _read_int(RESTART_STAMP) if os.path.isfile(RESTART_STAMP) else 0
    if now - last < RESTART_COOLDOWN_SEC:
        return
    # Arm trigger file as backup (repair-bridge may still poll it).
    os.makedirs(os.path.dirname(TRIGGER), exist_ok=True)
    os.makedirs(os.path.dirname(TRIGGER_SDCARD), exist_ok=True)
    try:
        with open(TRIGGER, "w", encoding="utf-8") as fh:
            fh.write(str(now))
        with open(TRIGGER_SDCARD, "w", encoding="utf-8") as fh:
            fh.write(str(now))
    except OSError:
        pass
    else:
        append_log("[termux] autojs6 guard: armed start_autojs6_now")
    # Restart AutoJs6 watchdog directly via am start (no ADB needed).
    boot_script = os.path.join(SD, "autojs6", "scripts", "boot-launcher.js")
    if os.path.isfile(boot_script):
        result = run(
            ["am", "start", "-a", "android.intent.action.VIEW",
             "-d", "file://" + boot_script,
             "-t", "text/javascript",
             "-n", "org.autojs.autojs6/org.autojs.autojs.external.open.RunIntentActivity"],
        )
        if result is not None and result.returncode == 0:
            append_log("[termux] autojs6 guard: restart requested via am start")
        else:
            rc = result.returncode if result is not None else "unavailable"
            append_log("[termux] autojs6 guard: restart request FAILED rc=%s" % rc)
    else:
        append_log("[termux] autojs6 guard: boot-launcher.js NOT FOUND at %s" % boot_script)
    os.makedirs(STATE, exist_ok=True)
    try:
        with open(RESTART_STAMP, "w", encoding="utf-8") as fh:
            fh.write(str(now))
    except OSError:
        pass


def action_check():
    cycle_ts, _cycle = latest_line_marker(LOG, "[watchdog] cycle start")
    repair_ts, _repair = latest_line_marker(LOG, ("[repair]", "STATUS"))
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
