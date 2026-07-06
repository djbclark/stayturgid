#!/data/data/com.termux/files/usr/bin/python
"""Low-battery tier alerts — Python twin of ../stayturgid-battery-alarm.sh.

Behavioral parity is enforced by tests/test-unit.sh, which runs the same
sandboxed suite against both implementations. The shell version remains the
deployed one until parity has soaked; then this replaces it (Ansible docs and
community practice: Python for anything beyond trivial wrappers).

Python is guaranteed on-device: it's in stayturgid_termux_packages and Ansible
itself requires it (ansible_python_interpreter).
"""
import json
import os
import signal
import subprocess
import sys
import time

HOME = os.environ.get("HOME", "")
STATE_FILE = os.path.join(HOME, ".stayturgid_batt_alerted")
COLOR_DIR = os.path.join(HOME, ".stayturgid", "battery-colors")
WALLPAPER_BACKUP = os.path.join(HOME, ".stayturgid", "wallpaper-backup.png")
SAVED_BRIGHT_FILE = os.path.join(HOME, ".stayturgid", "batt_saved_brightness")

TIERS = [30, 25, 20, 15, 10, 5, 4, 3, 2, 1, 0]
TIER_COLOR = {30: "purple", 25: "blue", 20: "green", 15: "yellow", 10: "orange"}
TIER_BLINKS = {30: 1, 25: 2, 20: 3, 15: 4, 10: 5}


def run(args, **kw):
    """Best-effort external command (stub-interceptable via PATH)."""
    opts = {"capture_output": True, "text": True}
    opts.update(kw)
    try:
        return subprocess.run(args, **opts)
    except OSError:
        return None


def out_of(args):
    r = run(args)
    return (r.stdout if r and r.returncode == 0 else "").replace("\r", "").strip()


def adb_shell(*cmd):
    r = run(["adb", "connect", "localhost:5555"])
    if not r or r.returncode != 0:
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
    os.makedirs(os.path.dirname(WALLPAPER_BACKUP), exist_ok=True)
    r = run(["adb", "connect", "localhost:5555"])
    if r and r.returncode == 0:
        # exec-out keeps the image byte-exact
        rr = run(["adb", "-s", "localhost:5555", "exec-out",
                  "cmd", "wallpaper", "get-image"], text=False)
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


def blink_screen_color(color, count, quiet):
    png = os.path.join(COLOR_DIR, "%s.png" % color)
    black = os.path.join(COLOR_DIR, "black.png")
    on_s, off_s = (0.18, 0.10) if quiet else (0.35, 0.20)

    backup_wallpaper_once()
    use_wallpaper = os.path.exists(png) and wallpaper_backup_valid()

    save_brightness()
    adb_shell("input", "keyevent", "KEYCODE_WAKEUP")

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
    blink_screen_color(color, blinks, quiet)

    if tier <= 15:
        pulse_torch(1 if quiet else blinks, quiet)

    title = "⚠ stayturgid: battery %s%% (tier %d%%)" % (pct, tier)
    if not quiet:
        run(["termux-notification", "--id", "stayturgid-batt", "--priority", "max",
             "--ongoing", "--title", title,
             "--content", "Not charging — remote access dies when this powers off. "
                          "Plug in a charger."])
        run(["termux-toast",
             "stayturgid: battery %s%% — plug in! (tier %d%%)" % (pct, tier)])
        run(["termux-vibrate", "-d", "400"])
    else:
        run(["termux-notification", "--id", "stayturgid-batt", "--priority", "max",
             "--ongoing", "--alert-once", "--title", title,
             "--content", "Not charging — plug in. (quiet hours: screen/torch only)"])


def on_signal(_sig, _frm):
    restore_wallpaper()
    restore_brightness()
    sys.exit(130)


def main():
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    raw = out_of(["termux-battery-status"])
    if not raw:
        return 0
    try:
        batt = json.loads(raw)
    except ValueError:
        batt = {}
    pct = batt.get("percentage")
    status = batt.get("status", "")
    if pct is None:
        return 0
    pct = int(pct)

    if status in ("CHARGING", "FULL") or pct > 30:
        clear_alert_state()
        return 0

    quiet = dnd_or_sleep_quiet()

    applicable = [t for t in TIERS if pct <= t]
    if not applicable:
        return 0
    lowest = applicable[-1]

    if str(lowest) not in alerted_tiers():
        fire_tier_alert(lowest, pct, quiet)
        for t in applicable:
            mark_alerted(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
