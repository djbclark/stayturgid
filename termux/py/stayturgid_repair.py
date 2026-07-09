#!/data/data/com.termux/files/usr/bin/python
"""stayturgid-repair.py — Termux-side self-heal (deployed as ~/stayturgid_repair.py,
reached via the ~/stayturgid-repair.sh compat shim).

Unit-tested via tests/test-unit.sh (repair_suite). The ~/stayturgid-repair.sh
shim keeps AutoJs6 RUN_COMMAND / boot-loop / repair-bridge callers unchanged.

Uses Shizuku's shell-privileged adbd on localhost:5555 (uid 2000) for
privileged checks/repairs. Exit 0 = healthy after repair; 1 = a subsystem
still down (needs AutoJs6 UI repair or reboot). Prints one STATUS line.
"""
import datetime
import fcntl
import json
import os
import subprocess
import sys
import time

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
TMPDIR = os.environ.get("TMPDIR", PREFIX + "/tmp")
os.environ["PATH"] = PREFIX + "/bin:" + PREFIX + "/sbin:" + os.environ.get("PATH", "")
os.environ["LC_ALL"] = "C"

# All stayturgid files live under one root per filesystem (self-healing: every
# writer mkdir -p's its dir, so a user-deleted dir just gets recreated).
STG = os.path.join(HOME, ".stayturgid")             # Termux-private root
_ENV_FILE = os.path.join(STG, "env")
if os.path.isfile(_ENV_FILE):
    try:
        with open(_ENV_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("export STAYTURGID_SD="):
                    os.environ["STAYTURGID_SD"] = _line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")  # shared-storage root


def ensure_parent(path):
    """mkdir -p the parent dir so a deleted stayturgid dir self-heals."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except OSError:
        pass
    return path


LOCKFILE = os.path.join(TMPDIR, "stayturgid-repair.lock")
LOG = os.path.join(STG, "logs", "repair.log")
SDLOG = os.path.join(SD, "logs", "watchdog.log")
# AutoJs6 always reads /sdcard/stayturgid/logs (cannot write Termux-private
# paths on Fire). Dual-write STATUS there so the JS co-monitor can see Termux
# freshness even when STAYTURGID_SD is ~/.stayturgid/shared.
SDCARD_WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
A11Y_SVC = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"
A11Y_BACKUP = os.path.join(SD, "state", "a11y_services_backup.txt")


def _parse_a11y_list(raw):
    text = (raw or "").strip()
    if text in ("", "null"):
        return []
    out, seen = [], set()
    for part in text.split(":"):
        svc = part.strip()
        if svc and svc not in seen:
            seen.add(svc)
            out.append(svc)
    return out


def _merge_a11y_list(current, add):
    merged = _parse_a11y_list(current)
    seen = set(merged)
    for svc in add:
        if svc and svc not in seen:
            seen.add(svc)
            merged.append(svc)
    return ":".join(merged)


def _a11y_lost(before, after):
    return [s for s in _parse_a11y_list(before) if s not in set(_parse_a11y_list(after))]


def _backup_a11y_list(value):
    ensure_parent(A11Y_BACKUP)
    try:
        with open(A11Y_BACKUP, "w") as f:
            f.write((value or "").strip() + "\n")
    except OSError:
        pass


def _read_a11y_backup():
    try:
        with open(A11Y_BACKUP) as f:
            return f.read().strip()
    except OSError:
        return ""


def _repair_a11y_shrink(before, after):
    lost = _a11y_lost(before, after)
    if not lost:
        return ""
    backup = _read_a11y_backup()
    return _merge_a11y_list(_merge_a11y_list(before, _parse_a11y_list(backup)), [A11Y_SVC])


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    line = "%s [repair] %s" % (ts(), msg)
    paths = [LOG, SDLOG]
    if os.path.normpath(SDLOG) != os.path.normpath(SDCARD_WATCHDOG_LOG):
        paths.append(SDCARD_WATCHDOG_LOG)
    for path in paths:
        try:
            with open(ensure_parent(path), "a") as f:
                f.write(line + "\n")
        except OSError:
            pass


def trim_log(path, keep=500, over=1000):
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) > over:
        try:
            with open(path, "w") as f:
                f.writelines(lines[-keep:])
        except OSError:
            pass


def run(args):
    """Run a command via the sandbox/real PATH; return (rc, stdout)."""
    try:
        p = subprocess.run(args, capture_output=True, text=True)
        return p.returncode, p.stdout
    except OSError:
        return 127, ""


def sh_adb(cmd):
    """adb -s localhost:5555 shell <cmd> — cmd is one string, matching $SH "...".
    Returns (rc, stdout without CR)."""
    rc, out = run(["adb", "-s", "localhost:5555", "shell", cmd])
    return rc, out.replace("\r", "")


def sshd_listening():
    if run(["ss", "-tln"])[0] == 0 and ":8022 " in run(["ss", "-tln"])[1]:
        return True
    rc, out = run(["netstat", "-tln"])
    return rc == 0 and ":8022 " in out


def sshd_up():
    if run(["pgrep", "-x", "sshd"])[0] == 0:
        return True
    if run(["pgrep", "-f", "[s]shd"])[0] == 0:
        return True
    return sshd_listening()


def privileged_shell():
    """Return True if localhost:5555 gives a uid-2000 shell."""
    if run(["adb", "connect", "localhost:5555"])[0] != 0:
        return False
    _rc, out = sh_adb("id -u")
    return out.strip() == "2000"


def read_device_profile():
    for path in (
        os.path.join(SD, "state", "device.json"),
        os.path.join(STG, "state", "device.json"),
    ):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def privileged_shell_expected():
    """Fire OS and split-storage hosts use Mac adb, not Termux loopback 5555."""
    prof = read_device_profile()
    if prof.get("privilegedShellExpected") is False:
        return False
    if prof.get("privilegedShellExpected") is True:
        return True
    if SD.startswith(HOME) or "/com.termux/" in SD:
        return False
    return True


def ensure_wireless_debugging():
    """Re-enable the Developer-options wireless-debugging toggle when shell can."""
    wifi = sh_adb("settings get global adb_wifi_enabled")[1].strip()
    if wifi in ("1", "true"):
        return "up"
    sh_adb("settings put global adb_wifi_enabled 1")
    time.sleep(2)
    wifi2 = sh_adb("settings get global adb_wifi_enabled")[1].strip()
    if wifi2 in ("1", "true"):
        log("wireless debugging was off -> re-enabled adb_wifi_enabled")
        return "repaired"
    log("wireless debugging re-enable FAILED (adb_wifi_enabled=%s)" % wifi2)
    return "FAILED"


def duplicate_branch():
    """Another invocation holds the lock: read-only advisory probe, exit 0."""
    sshd = "up" if (sshd_up() or sshd_listening()) else "unknown"
    if not privileged_shell_expected():
        port, sh, shizuku = "skip", False, "skip"
    elif privileged_shell():
        port, sh = "open", True
        rc, _ = sh_adb("pgrep -f shizuku_server")
        shizuku = "up" if rc == 0 else "down"
        wifi = "up" if sh_adb("settings get global adb_wifi_enabled")[1].strip() in ("1", "true") else "down"
    else:
        port, sh, shizuku, wifi = "CLOSED_NO_SHELL", False, "unknown", "unknown"
    status = "STATUS port=%s shizuku=%s sshd=%s shell=%s wifi=%s" % (
        port, shizuku, sshd, "yes" if sh else "no", wifi)
    log(status + " rc=0 (skipped-duplicate)")
    print(status)
    return 0


def acquire_lock():
    """Non-blocking exclusive lock. FLOCK_RC=1 is a test seam for the
    contention path (macOS test host has no flock(1)); real runs use fcntl."""
    if os.environ.get("FLOCK_RC") == "1":
        return None
    try:
        os.makedirs(os.path.dirname(LOCKFILE), exist_ok=True)
        fd = open(LOCKFILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (OSError, IOError):
        return None


def main():
    try:
        os.makedirs(TMPDIR, exist_ok=True)
    except OSError:
        pass

    lock = acquire_lock()
    if lock is None:
        return duplicate_branch()

    trim_log(LOG)
    trim_log(SDLOG)
    if os.path.normpath(SDLOG) != os.path.normpath(SDCARD_WATCHDOG_LOG):
        trim_log(SDCARD_WATCHDOG_LOG)
    rc = 0

    # --- 1. sshd ---
    if sshd_up():
        sshd = "up"
    else:
        if not sshd_listening():
            run(["sshd"])
        time.sleep(2)
        if sshd_up():
            sshd = "restarted"
            log("sshd was down -> restarted")
        else:
            sshd = "FAILED"
            rc = 1
            log("sshd restart FAILED")

    # --- 2. privileged shell via Shizuku's adbd on localhost:5555 ---
    expect_shell = privileged_shell_expected()
    if not expect_shell:
        have_sh = False
        port = "skip"
        shizuku = "skip"
        a11y = "skip"
        wifi = "skip"
    elif privileged_shell():
        have_sh = True
        port = "open"
        sh_adb("setprop service.adb.tcp.port 5555")  # keep 5555 sticky
        wifi = ensure_wireless_debugging()
    else:
        have_sh = False
        port = "CLOSED_NO_SHELL"
        wifi = "unknown"
        rc = 1
        log("5555 CLOSED / no privileged shell — escalate to AutoJs6 UI repair or reboot")

    # --- 3. shizuku (via privileged shell) ---
    if expect_shell and have_sh:
        shizuku = "up" if sh_adb("pgrep -f shizuku_server")[0] == 0 else "down"
    elif expect_shell:
        shizuku = "unknown"

    # --- 4. AutoJs6 accessibility (Samsung disables it) — merge, never replace ---
    if expect_shell:
        a11y = "unknown"
        if have_sh:
            before = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
            _backup_a11y_list(before)
            if A11Y_SVC in before:
                a11y = "up"
            else:
                new = _merge_a11y_list(before, [A11Y_SVC])
                sh_adb("settings put secure enabled_accessibility_services '%s'" % new)
                sh_adb("settings put secure accessibility_enabled 1")
                recheck = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
                repaired = _repair_a11y_shrink(before, recheck)
                if repaired:
                    sh_adb("settings put secure enabled_accessibility_services '%s'" % repaired)
                    sh_adb("settings put secure accessibility_enabled 1")
                    recheck = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
                if A11Y_SVC in recheck:
                    a11y = "repaired"
                    lost = _a11y_lost(before, recheck)
                    if lost:
                        log("AutoJs6 a11y re-enabled but still missing: %s" % ",".join(lost))
                    else:
                        log("AutoJs6 accessibility was off -> re-enabled (merged)")
                else:
                    a11y = "FAILED"
                    log("AutoJs6 accessibility re-enable FAILED")

    status = "STATUS port=%s shizuku=%s sshd=%s a11y=%s shell=%s wifi=%s" % (
        port, shizuku, sshd, a11y, "yes" if have_sh else "no", wifi)
    log(status + " rc=%d" % rc)
    print(status)
    return rc


if __name__ == "__main__":
    sys.exit(main())
