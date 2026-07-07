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
A11Y_SVC = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher"


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    line = "%s [repair] %s" % (ts(), msg)
    for path in (LOG, SDLOG):
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


def duplicate_branch():
    """Another invocation holds the lock: read-only advisory probe, exit 0."""
    sshd = "up" if (sshd_up() or sshd_listening()) else "unknown"
    if not privileged_shell_expected():
        port, sh, shizuku = "skip", False, "skip"
    elif privileged_shell():
        port, sh = "open", True
        rc, _ = sh_adb("pgrep -f shizuku_server")
        shizuku = "up" if rc == 0 else "down"
    else:
        port, sh, shizuku = "CLOSED_NO_SHELL", False, "unknown"
    status = "STATUS port=%s shizuku=%s sshd=%s shell=%s" % (
        port, shizuku, sshd, "yes" if sh else "no")
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
    elif privileged_shell():
        have_sh = True
        port = "open"
        sh_adb("setprop service.adb.tcp.port 5555")  # keep 5555 sticky
    else:
        have_sh = False
        port = "CLOSED_NO_SHELL"
        rc = 1
        log("5555 CLOSED / no privileged shell — escalate to AutoJs6 UI repair or reboot")

    # --- 3. shizuku (via privileged shell) ---
    if expect_shell and have_sh:
        shizuku = "up" if sh_adb("pgrep -f shizuku_server")[0] == 0 else "down"
    elif expect_shell:
        shizuku = "unknown"

    # --- 4. AutoJs6 accessibility (Samsung disables it) — APPEND-ONLY ---
    if expect_shell:
        a11y = "unknown"
        if have_sh:
            cur = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
            if A11Y_SVC in cur:
                a11y = "up"
            else:
                new = A11Y_SVC if cur in ("", "null") else "%s:%s" % (cur, A11Y_SVC)
                sh_adb("settings put secure enabled_accessibility_services '%s'" % new)
                sh_adb("settings put secure accessibility_enabled 1")
                recheck = sh_adb("settings get secure enabled_accessibility_services")[1].strip()
                if A11Y_SVC in recheck:
                    a11y = "repaired"
                    log("AutoJs6 accessibility was off -> re-enabled (appended)")
                else:
                    a11y = "FAILED"
                    log("AutoJs6 accessibility re-enable FAILED")

    status = "STATUS port=%s shizuku=%s sshd=%s a11y=%s shell=%s" % (
        port, shizuku, sshd, a11y, "yes" if have_sh else "no")
    log(status + " rc=%d" % rc)
    print(status)
    return rc


if __name__ == "__main__":
    sys.exit(main())
