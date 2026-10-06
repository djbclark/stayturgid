#!/data/data/com.termux/files/usr/bin/python
"""Low-battery tier alerts (Python) — deployed as ~/stayturgid_battery_alarm.py.

Migrated from stayturgid-battery-alarm.sh; unit-tested via tests/test-unit.sh
(battery_suite). Called from the boot loop each ~5 min while discharging.

Python is guaranteed on-device: it's in stayturgid_termux_packages and Ansible
itself requires it (ansible_python_interpreter).
"""

import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time

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

import stayturgid_shell as sh

sh.ensure_lib_path()
try:
    import termux_api as tapi
except ImportError:
    tapi = None

STATE_FILE = os.path.join(STG, "state", "batt_alerted")
COLOR_DIR = os.path.join(STG, "battery-colors")
WALLPAPER_BACKUP = os.path.join(STG, "state", "wallpaper-backup.png")
SAVED_BRIGHT_FILE = os.path.join(STG, "state", "batt_saved_brightness")
BATT_LOG = os.path.join(STG, "logs", "battery.log")
# Fire OS: termux-battery-status / localhost adb can hang forever.
CMD_TIMEOUT_SEC = 8

TIERS = [30, 25, 20, 15, 10, 5, 4, 3, 2, 1, 0]
TIER_COLOR = {30: "purple", 25: "blue", 20: "green", 15: "yellow", 10: "orange"}
TIER_BLINKS = {30: 1, 25: 2, 20: 3, 15: 4, 10: 5}

# Locate sound (2026-10-05): a lost phone should be found by ear before it dies and
# Find Hub goes blind. The clip (control/tools/gen_locate_sound.py) is a broadband chime:
# broadband sounds with sharp onsets are much easier to locate than pure beeps. It plays
# whatever the phone's DND/silent setting, never 21:00-09:00, and loops from 2% until
# dismissed from its notification or plugged in.
SOUND_FILE = os.path.join(COLOR_DIR, "locate.mp3")
SOUND_CLIP_SEC = 4.0
TIER_SOUND_SEC = {30: 10, 25: 20, 20: 30, 15: 40, 10: 50, 5: 60}
CONTINUOUS_PCT = 2
QUIET_START_H, QUIET_END_H = 21, 9
# Evening warnings, only if the phone is predicted dead before 10:00 tomorrow. Each
# slot may fire from 10 min before to 5 min after, so the ~5 min boot loop can't miss it.
EVENING_SLOTS = [((18, 55), 15), ((19, 55), 30), ((20, 55), 60)]
EVENING_DEADLINE_H = 10
IDLE_DRAIN_PER_H = 1.0  # assumed when battery.log has too little history to measure
ZEN_TO_DND = {"1": "priority", "2": "none", "3": "alarms"}  # zen_mode -> set_dnd arg
STATE_DIR = os.path.join(STG, "state")
STATUS_JSON = os.path.join(STATE_DIR, "batt_status.json")  # read by the Mac hub
SOUND_PID = os.path.join(STATE_DIR, "batt_sound.pid")
SOUND_STOP = os.path.join(STATE_DIR, "batt_sound_stop")
CONT_DISMISSED = os.path.join(STATE_DIR, "batt_continuous_dismissed")
SKIP_NIGHT = os.path.join(STATE_DIR, "batt_skip_night")
EVENING_DONE = os.path.join(STATE_DIR, "batt_evening_done")
_LOG_RE = re.compile(r"^(\S+ \S+) \[batt\] pct=(\d+)% status=(\S+)")


def _log(msg):
    """Write a timestamped entry to the battery log (self-healing dir)."""
    try:
        os.makedirs(os.path.dirname(BATT_LOG) or ".", exist_ok=True)
        line = "%s [batt] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
        with open(BATT_LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _no_local_adb() -> bool:
    return os.environ.get("STAYTURGID_NO_LOCAL_ADB") == "1"


def run(args, **kw):
    """Best-effort external command; never SIGKILL Termux:API clients."""
    timeout = kw.pop("timeout", CMD_TIMEOUT_SEC)
    if kw:
        # Rare callers pass extra subprocess kwargs — fall through carefully.
        opts = {"capture_output": True, "text": True, "timeout": timeout, "start_new_session": True}
        opts.update(kw)
        try:
            return subprocess.run(args, **opts)
        except (OSError, subprocess.TimeoutExpired):
            return None
    if tapi is not None and tapi.is_termux_api(args):
        if tapi.is_fire_and_forget(args):
            return tapi.run_ff(args, timeout=min(float(timeout), 4.0))
        return tapi.run(args, timeout=timeout)
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def out_of(args):
    r = run(args)
    return (r.stdout if r and r.returncode == 0 else "").replace("\r", "").strip()


def adb_shell(*cmd):
    if _no_local_adb():
        return ""
    if not sh.connect(timeout=5):
        return ""
    return out_of(["adb", "-s", "localhost:5555", "shell"] + list(cmd))


def dnd_or_sleep_quiet():
    if adb_shell("settings", "get", "global", "zen_mode") in ("1", "2", "3"):
        return True
    dump = adb_shell("dumpsys", "notification")
    for f in ("PRIORITY", "ALARMS", "NONE"):
        if "mInterruptionFilter=" + f in dump:
            return True
    return adb_shell("cmd", "audio", "get-ringer-mode") == "0"


def alerted_tiers():
    try:
        with open(STATE_FILE) as f:
            return {line.strip() for line in f if line.strip()}
    except OSError:
        return set()


def mark_alerted(tier):
    tiers = alerted_tiers()
    if str(tier) not in tiers:
        os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
        with open(STATE_FILE, "a") as f:
            f.write("%d\n" % tier)


def save_brightness():
    os.makedirs(os.path.dirname(SAVED_BRIGHT_FILE), exist_ok=True)
    b = adb_shell("settings", "get", "system", "screen_brightness")
    try:
        with open(SAVED_BRIGHT_FILE, "w") as f:
            f.write(b + "\n")
    except OSError:
        pass


def restore_brightness():
    try:
        with open(SAVED_BRIGHT_FILE) as f:
            b = f.read().replace("\r", "").strip()
    except OSError:
        return
    if b:
        run(["termux-brightness", b])


def wallpaper_backup_valid():
    try:
        with open(WALLPAPER_BACKUP, "rb") as f:
            magic = f.read(3)
    except OSError:
        return False
    return magic in (b"\x89PN", b"\xff\xd8\xff")


def backup_wallpaper_once():
    if os.path.exists(WALLPAPER_BACKUP):
        return
    if _no_local_adb():
        return
    os.makedirs(os.path.dirname(WALLPAPER_BACKUP), exist_ok=True)
    if sh.connect(timeout=5):
        # exec-out keeps the image byte-exact
        rr = run(["adb", "-s", "localhost:5555", "exec-out", "cmd", "wallpaper", "get-image"], text=False)
        if rr is not None:
            try:
                with open(WALLPAPER_BACKUP, "wb") as f:
                    f.write(rr.stdout or b"")
            except OSError:
                pass
    if not wallpaper_backup_valid():
        try:
            os.unlink(WALLPAPER_BACKUP)
        except OSError:
            pass


def restore_wallpaper():
    if os.path.exists(WALLPAPER_BACKUP):
        run(["termux-wallpaper", "-f", WALLPAPER_BACKUP])


def clear_alert_state():
    if os.path.exists(STATE_FILE):
        restore_wallpaper()
        restore_brightness()
        for p in (WALLPAPER_BACKUP, SAVED_BRIGHT_FILE, STATE_FILE):
            try:
                os.unlink(p)
            except OSError:
                pass
    run(["termux-notification-remove", "stayturgid-batt"])


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text + "\n")


def _rm(*paths):
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def quiet_hours(now=None):
    h = (now or datetime.datetime.now()).hour
    return h >= QUIET_START_H or h < QUIET_END_H


def drain_per_hour(now=None, window_min=120):
    """%/hour over the current discharge (last 2 h of battery.log); None if too little history."""
    now = now or datetime.datetime.now()
    try:
        with open(BATT_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 32768))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    samples = []
    for line in lines:
        m = _LOG_RE.match(line)
        if not m:
            continue
        if m.group(3) != "DISCHARGING":
            samples = []  # a charge starts a new discharge
            continue
        try:
            ts = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if (now - ts).total_seconds() <= window_min * 60:
            samples.append((ts, int(m.group(2))))
    if len(samples) < 2:
        return None
    hours = (samples[-1][0] - samples[0][0]).total_seconds() / 3600
    drop = samples[0][1] - samples[-1][1]
    if hours < 0.5 or drop < 1:
        return None
    return drop / hours


def write_status(batt, pct, status, rate):
    """One JSON line for the Mac hub (control/lib/battery_watch.py)."""
    try:
        prev = json.loads(_read(STATUS_JSON) or "{}")
    except ValueError:
        prev = {}
    now = int(time.time())
    plugged = batt.get("plugged", "UNPLUGGED")
    on_charger = status in ("CHARGING", "FULL") or plugged not in ("UNPLUGGED", "")
    st = {
        "ts": now,
        "pct": pct,
        "status": status,
        "plugged": plugged,
        "eta_min": int(pct / rate * 60) if rate and not on_charger else None,
        "last_charged": now if on_charger else prev.get("last_charged"),
    }
    try:
        _write(STATUS_JSON, json.dumps(st))
    except OSError:
        pass


def _self_cmd(*args):
    """Shell command line for a notification button that re-enters this script."""
    return " ".join([sys.executable, os.path.abspath(__file__)] + list(args))


def _sound_pid_mode():
    """(pid, mode) of the running player, or (None, None)."""
    try:
        pid, mode = _read(SOUND_PID).split()
        os.kill(int(pid), 0)
        return int(pid), mode
    except (ValueError, OSError):
        return None, None


def start_sound(secs, why):
    """Detach a player: secs > 0 plays about that long; 0 loops until dismissed,
    plugged in, or quiet hours. Posts a notification whose button stops it."""
    if not os.path.exists(SOUND_FILE):
        _log("no %s; sound skipped (%s)" % (SOUND_FILE, why))
        return False
    if _sound_pid_mode()[0]:
        _log("sound already playing; %s skipped" % why)
        return False
    _rm(SOUND_STOP)
    _log("SOUND %s (%s)" % ("loop" if secs <= 0 else "%ds" % secs, why))
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "sound", str(int(secs))],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    run(
        [
            "termux-notification", "--id", "stayturgid-batt-sound", "--priority", "max",
            "--title", "stayturgid: locate sound playing (%s)" % why,
            "--content", "Tap Stop sound once you have found the device.",
            "--button1", "Stop sound", "--button1-action", _self_cmd("stop-sound"),
        ]
    )  # fmt: skip
    return True


def stop_sound(dismiss=True):
    """Stop the player; dismissing a loop keeps it off until the next charge."""
    pid, mode = _sound_pid_mode()
    if not pid:
        return
    _write(SOUND_STOP, "1")
    if dismiss and mode == "loop":
        _write(CONT_DISMISSED, "1")
    run(["termux-media-player", "stop"])


def _force_audible():
    """Max media volume and DND off while the sound plays; returns the undo."""
    undo = []
    try:
        streams = json.loads(out_of(["termux-volume"]) or "[]")
        music = next(s for s in streams if s.get("stream") == "music")
        run(["termux-volume", "music", str(music["max_volume"])])
        undo.append(lambda v=str(music["volume"]): run(["termux-volume", "music", v]))
    except (ValueError, StopIteration, KeyError, TypeError, AttributeError):
        pass
    zen = adb_shell("settings", "get", "global", "zen_mode")
    if zen in ZEN_TO_DND:
        adb_shell("cmd", "notification", "set_dnd", "off")
        undo.append(lambda m=ZEN_TO_DND[zen]: adb_shell("cmd", "notification", "set_dnd", m))
    return lambda: [u() for u in undo]


def sound_loop(secs):
    """The detached player itself (`sound <secs>`)."""
    _write(SOUND_PID, "%d %s" % (os.getpid(), "loop" if secs <= 0 else "timed"))
    restore = _force_audible()
    end = time.time() + secs
    try:
        while not os.path.exists(SOUND_STOP):
            if secs > 0 and time.time() >= end:
                break
            if secs <= 0 and quiet_hours():
                break
            run(["termux-media-player", "play", SOUND_FILE])
            time.sleep(SOUND_CLIP_SEC)
    finally:
        run(["termux-media-player", "stop"])
        restore()
        _rm(SOUND_PID, SOUND_STOP)
        run(["termux-notification-remove", "stayturgid-batt-sound"])


def evening_check(pct, rate, now=None):
    """18:55/19:55/20:55 warnings when the phone is predicted dead before 10:00 tomorrow."""
    now = now or datetime.datetime.now()
    today = now.strftime("%Y-%m-%d")
    if _read(SKIP_NIGHT) == today:
        return
    done = _read(EVENING_DONE).split()
    if done[:1] != [today]:
        done = [today]
    for (h, m), secs in EVENING_SLOTS:
        slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = "%02d%02d" % (h, m)
        if key in done or not (slot - datetime.timedelta(minutes=10) <= now < slot + datetime.timedelta(minutes=5)):
            continue
        done.append(key)
        _write(EVENING_DONE, " ".join(done))
        dead_at = now + datetime.timedelta(hours=pct / (rate or IDLE_DRAIN_PER_H))
        deadline = (now + datetime.timedelta(days=1)).replace(
            hour=EVENING_DEADLINE_H, minute=0, second=0, microsecond=0
        )
        if dead_at >= deadline:
            _log("evening %s: ok until %s" % (key, dead_at.strftime("%a %H:%M")))
            continue
        _log("evening %s: predicted dead ~%s" % (key, dead_at.strftime("%a %H:%M")))
        start_sound(secs, "evening %s" % key)
        run(
            [
                "termux-notification", "--id", "stayturgid-batt-night", "--priority", "max",
                "--title", "stayturgid: battery %d%% — likely dead by ~%s" % (pct, dead_at.strftime("%H:%M")),
                "--content", "Plug in before bed.",
                "--button1", "No nightly warnings today",
                "--button1-action", _self_cmd("skip-tonight"),
            ]
        )  # fmt: skip


def skip_tonight():
    _write(SKIP_NIGHT, datetime.datetime.now().strftime("%Y-%m-%d"))
    stop_sound()
    run(["termux-notification-remove", "stayturgid-batt-night"])
    run(["termux-toast", "stayturgid: no nightly battery warnings today"])


def blink_screen_color(color, count, quiet):
    png = os.path.join(COLOR_DIR, "%s.png" % color)
    black = os.path.join(COLOR_DIR, "black.png")

    backup_wallpaper_once()
    use_wallpaper = os.path.exists(png) and wallpaper_backup_valid()

    save_brightness()
    adb_shell("input", "keyevent", "KEYCODE_WAKEUP")

    if use_wallpaper:
        on_s, off_s = (0.18, 0.10) if quiet else (0.35, 0.20)
    else:
        on_s, off_s = (0.50, 0.30)

    for _ in range(count):
        run(["termux-brightness", "255"])
        if use_wallpaper:
            run(["termux-wallpaper", "-f", png])
        time.sleep(on_s)
        if use_wallpaper and os.path.exists(black):
            run(["termux-wallpaper", "-f", black])
        run(["termux-brightness", "32"])
        time.sleep(off_s)

    if use_wallpaper:
        restore_wallpaper()
    restore_brightness()


def pulse_torch(n, quiet):
    if tapi is not None:
        if quiet:
            tapi.pulse_torch(1, on_s=0.06, off_s=0.0, torch_timeout=2.0)
            return
        tapi.pulse_torch(n, on_s=0.22, off_s=0.18, torch_timeout=2.0)
        return
    if quiet:
        run(["termux-torch", "on"])
        time.sleep(0.06)
        run(["termux-torch", "off"])
        return
    for _ in range(n):
        run(["termux-torch", "on"])
        time.sleep(0.22)
        run(["termux-torch", "off"])
        time.sleep(0.18)


def fire_tier_alert(tier, pct, quiet):
    color = TIER_COLOR.get(tier, "red")
    blinks = TIER_BLINKS.get(tier, 10 if tier <= 5 else 1)
    if tier in TIER_SOUND_SEC and not quiet_hours():
        start_sound(TIER_SOUND_SEC[tier], "battery %s%%" % pct)
    blink_screen_color(color, blinks, quiet)

    if tier <= 15:
        pulse_torch(1 if quiet else blinks, quiet)

    title = "⚠ stayturgid: battery %s%% (tier %d%%)" % (pct, tier)
    if not quiet:
        run(
            [
                "termux-notification",
                "--id",
                "stayturgid-batt",
                "--priority",
                "max",
                "--ongoing",
                "--title",
                title,
                "--content",
                "Not charging — remote access dies when this powers off. Plug in a charger.",
            ]
        )
        run(["termux-toast", "stayturgid: battery %s%% — plug in! (tier %d%%)" % (pct, tier)])
        run(["termux-vibrate", "-d", "400"])
    else:
        run(
            [
                "termux-notification",
                "--id",
                "stayturgid-batt",
                "--priority",
                "max",
                "--ongoing",
                "--alert-once",
                "--title",
                title,
                "--content",
                "Not charging — plug in. (quiet hours: screen/torch only)",
            ]
        )


def on_signal(_sig, _frm):
    restore_wallpaper()
    restore_brightness()
    sys.exit(130)


def main(argv=()):
    cmd = argv[0] if argv else ""
    if cmd == "sound":  # the detached player
        sound_loop(int(argv[1]) if len(argv) > 1 else 0)
        return 0
    if cmd == "ring":  # on demand (control/bin/ring_device.py): ignores quiet hours
        start_sound(int(argv[1]) if len(argv) > 1 else 60, "ring")
        return 0
    if cmd == "stop-sound":  # notification button
        stop_sound()
        return 0
    if cmd == "skip-tonight":  # stayturgid-agent button / evening notification button
        skip_tonight()
        return 0

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # Prefer short timeout; on Fire, termux-battery-status has been observed to hang.
    raw = out_of(["timeout", str(CMD_TIMEOUT_SEC), "termux-battery-status"])
    if not raw:
        _log("termux-battery-status returned empty (timeout/failure) — skipping cycle")
        return 0
    try:
        batt = json.loads(raw)
    except ValueError:
        _log("termux-battery-status returned invalid JSON: %s..." % raw[:80])
        return 0
    pct = batt.get("percentage")
    status = batt.get("status", "")
    if pct is None:
        _log("no 'percentage' in battery JSON — skipping")
        return 0
    pct = int(pct)

    _log("pct=%s%% status=%s plugged=%s" % (pct, status, batt.get("plugged", "?")))

    charging = status in ("CHARGING", "FULL")
    rate = None if charging else drain_per_hour()
    write_status(batt, pct, status, rate)
    if charging:
        stop_sound(dismiss=False)
        _rm(CONT_DISMISSED)
    else:
        evening_check(pct, rate)

    if charging or pct > 30:
        clear_alert_state()
        return 0

    quiet = dnd_or_sleep_quiet()

    applicable = [t for t in TIERS if pct <= t]
    if not applicable:
        return 0
    lowest = applicable[-1]

    if str(lowest) not in alerted_tiers():
        _log("FIRING tier=%d (pct=%d, quiet=%s)" % (lowest, pct, quiet))
        fire_tier_alert(lowest, pct, quiet)
        for t in applicable:
            mark_alerted(t)
    else:
        _log("tier=%d already alerted (pct=%d)" % (lowest, pct))

    if pct <= CONTINUOUS_PCT and not quiet_hours() and not os.path.exists(CONT_DISMISSED):
        if not _sound_pid_mode()[0]:
            start_sound(0, "battery %d%%" % pct)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
