#!/usr/bin/env python3
"""Localhost:5555 privileged shell for Termux on-device scripts.

Matches stayturgid_repair.py channel (uid 2000). Fire OS hosts with
privilegedShellExpected=false must not use this — Mac USB adb instead.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time

HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
STG = os.path.join(HOME, ".stayturgid")
SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")
SERIAL = "localhost:5555"

# adbd raises a separate "Allow USB debugging?" dialog for every connection
# that offers an unknown key. After "Revoke USB debugging authorisations" the
# s24 queued four within three seconds (2026-10-04), three of them for Termux's
# key. Every on-device caller (boot loop, repair, guards, cf-agent) and the
# Mac's ssh health gather share Termux's one adb server, so they share one
# stand-down: a marker under ~/.stayturgid/state plus a lock around the attempt.
# Only these states mean adbd holds a dialog for Termux's key. "offline" and
# "connecting" are also what an authorised transport shows while adbd restarts
# or 5555 is closed, and standing down there skipped the rish adbd restart
# that is the phone's only way to reopen 5555.
ADB_AUTH_PENDING = ("unauthorized", "authorizing")
ADB_AUTH_WAITING_MSG = "adb unauthorised, waiting for the user"
try:
    ADB_AUTH_RETRY_SEC = int(os.environ.get("STAYTURGID_ADB_AUTH_RETRY_SEC", "600"))
except ValueError:
    ADB_AUTH_RETRY_SEC = 600
# A dismissed dialog must come back within the hour whatever the override says.
ADB_AUTH_RETRY_SEC = min(max(ADB_AUTH_RETRY_SEC, 60), 3600)
# Boot loops before the gate also connected this alias. adb keeps it as a
# second transport and re-dials it on its own, so a revoke raised a dialog for
# each serial.
LOOPBACK_ALIAS = "127.0.0.1:5555"


def _ensure_env():
    os.environ.setdefault("PATH", "%s/bin:/system/bin" % PREFIX)
    os.environ.setdefault("TMPDIR", "%s/tmp" % PREFIX)
    os.environ.setdefault("PREFIX", PREFIX)
    os.environ.setdefault("HOME", HOME)
    env_path = os.path.join(STG, "env")
    if os.path.isfile(env_path):
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("export "):
                        continue
                    body = line[len("export ") :]
                    if "=" not in body:
                        continue
                    key, val = body.split("=", 1)
                    val = val.strip().strip('"').strip("'")
                    if key == "STAYTURGID_SD" and val:
                        os.environ["STAYTURGID_SD"] = val
                        global SD
                        SD = val
                    elif key == "STAYTURGID_NO_LOCAL_ADB" and val:
                        os.environ["STAYTURGID_NO_LOCAL_ADB"] = val
                    elif key == "STAYTURGID_HANDSETS_PORT" and val:
                        os.environ.setdefault("STAYTURGID_HANDSETS_PORT", val)
        except OSError:
            pass


def run(args, timeout=60, input_text=None):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def adb_auth_marker():
    return os.path.join(STG, "state", "adb-auth-wait")


def adb_devices_rows(timeout=10):
    """``adb devices`` as {serial: state}, or None when adb fails."""
    r = run(["adb", "devices"], timeout=timeout)
    if r is None or r.returncode != 0:
        return None
    rows = {}
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] != "List":
            rows[parts[0]] = parts[1]
    return rows


def adb_devices_state(serial=SERIAL, timeout=10):
    """*serial*'s state in ``adb devices``: "" when not listed, None when adb fails."""
    rows = adb_devices_rows(timeout)
    return None if rows is None else rows.get(serial, "")


def _boot_epoch():
    """Wall-clock time this boot started, or None where CLOCK_BOOTTIME is missing."""
    clock = getattr(time, "CLOCK_BOOTTIME", None)
    if clock is None:
        return None
    try:
        return time.time() - time.clock_gettime(clock)
    except OSError:
        return None


def _adb_auth_marker_age(now):
    try:
        with open(adb_auth_marker()) as f:
            stamp = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    # A clock stepped backwards must not hold the stand-down forever, and a
    # dialog from before a reboot is gone with the adbd that showed it.
    boot = _boot_epoch()
    if stamp > now or (boot is not None and stamp < boot):
        return None
    return now - stamp


def _write_adb_auth_marker(now, state):
    path = adb_auth_marker()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("%d %s\n" % (int(now), state))
        return True
    except OSError:
        return False


def _clear_adb_auth_marker():
    try:
        os.remove(adb_auth_marker())
    except OSError:
        pass


def _take_adb_auth_lock(wait):
    """(fd, busy): the lock on the one connection attempt.

    fd is None when it was not taken; busy is True only when another process
    still held it after *wait* seconds, not when the lock file is unusable.
    """
    path = adb_auth_marker() + ".lock"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = open(path, "a")
    except OSError:
        return None, False
    deadline = time.monotonic() + max(wait, 0)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd, False
        except BlockingIOError:
            if time.monotonic() >= deadline:
                fd.close()
                return None, True
            time.sleep(0.2)
        except OSError:
            fd.close()
            return None, False


def _release_adb_auth_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        fd.close()


def _connect_says_unauthorised(r):
    text = ((r.stdout or "") + (r.stderr or "")).lower() if r is not None else ""
    return "authenticate" in text or "unauthorized" in text


def adb_connect(serial=SERIAL, timeout=15, now=None):
    """Connect *serial* unless a dialog for Termux's key is already outstanding.

    Returns "device" (connected, or ``adb connect`` succeeded), "waiting"
    (``adb devices`` lists *serial* as unauthorized/authorizing: stood down,
    ``ADB_AUTH_WAITING_MSG``) or "down" (adb missing, nothing listening). An
    authorised transport costs one ``adb devices`` and no connect. Any other
    state (offline, connecting, not listed) gets the plain ``adb connect``
    it always had, so callers still restart adbd when that fails. While a
    dialog is pending, at most one fresh attempt is made per
    ``ADB_AUTH_RETRY_SEC`` across all processes, so a dismissed dialog is
    raised again eventually rather than never or at every caller's cadence.
    Never touches adb_keys or answers a dialog.
    """
    probe = min(timeout, 10)
    rows = adb_devices_rows(probe)
    if rows is None:
        return "down"
    if serial == SERIAL and LOOPBACK_ALIAS in rows:
        run(["adb", "disconnect", LOOPBACK_ALIAS], timeout=timeout)
    state = rows.get(serial, "")
    if state == "device":
        _clear_adb_auth_marker()
        return "device"
    lock, busy = _take_adb_auth_lock(timeout)
    try:
        state = adb_devices_state(serial, probe)
        if state is None:
            return "down"
        if state == "device":
            _clear_adb_auth_marker()
            return "device"
        now = time.time() if now is None else now
        if state in ADB_AUTH_PENDING:
            if busy:
                # The holder owns the attempt and the dialog is already up.
                return "waiting"
            age = _adb_auth_marker_age(now)
            if age is not None and age < ADB_AUTH_RETRY_SEC:
                return "waiting"
            if age is None and _write_adb_auth_marker(now, state):
                return "waiting"
            if age is not None:
                # `adb connect` on a listed transport only answers "already
                # connected"; dropping it is the one way to put a dismissed
                # dialog back in front of the user.
                run(["adb", "disconnect", serial], timeout=timeout)
        r = run(["adb", "connect", serial], timeout=timeout)
        after = adb_devices_state(serial, probe)
        if after == "device":
            _clear_adb_auth_marker()
            return "device"
        if after in ADB_AUTH_PENDING or _connect_says_unauthorised(r):
            # Without a marker nothing bounds the stand-down, so report the
            # transport down and let callers recover as they did before.
            return "waiting" if _write_adb_auth_marker(now, after or "unauthorized") else "down"
        if r is not None and r.returncode == 0:
            return "device"
        return "down"
    finally:
        if lock is not None:
            _release_adb_auth_lock(lock)


def connect(timeout=15):
    _ensure_env()
    return adb_connect(timeout=timeout) == "device"


def shell(*args, timeout=30):
    """adb -s localhost:5555 shell … → (rc, stdout)."""
    if not connect():
        # An unauthorised or absent transport cannot run it; skip the call.
        return 1, ""
    r = run(["adb", "-s", SERIAL, "shell"] + list(args), timeout=timeout)
    if r is None:
        return 127, ""
    return r.returncode, (r.stdout or "").replace("\r", "")


def shell_fn(serial, *args, timeout=30):
    """Adapter matching ui_clearance / ScreenControlSession shell(serial, *args)."""
    del serial  # always localhost:5555 on-device
    return shell(*args, timeout=timeout)


def read_device_profile():
    _ensure_env()
    for path in (
        os.path.join(SD, "state", "device.json"),
        os.path.join(STG, "state", "device.json"),
        os.path.join(STG, "shared", "state", "device.json"),
    ):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def privileged_shell_expected():
    """False on Fire OS / split-storage hosts (Mac USB adb only)."""
    prof = read_device_profile()
    if prof.get("privilegedShellExpected") is False:
        return False
    if prof.get("privilegedShellExpected") is True:
        return True
    sd = os.environ.get("STAYTURGID_SD", SD)
    if sd.startswith(HOME) or "/com.termux/" in sd:
        return False
    return True


def privileged_shell_ok():
    if not privileged_shell_expected():
        return False
    if not connect():
        return False
    rc, out = shell("id", "-u")
    return rc == 0 and out.strip() == "2000"


def device_label():
    prof = read_device_profile()
    return prof.get("label") or prof.get("alias") or "this phone"


def lib_paths():
    """sys.path entries for ~/.stayturgid/lib and repo control/lib when developing."""
    paths = [
        os.path.join(STG, "lib"),
        os.path.join(HOME, ".stayturgid", "lib"),
    ]
    # Repo checkout (Mac unit tests / ad-hoc): walk up from termux/py
    here = os.path.dirname(os.path.abspath(__file__))
    repo = here
    while repo != os.path.dirname(repo):
        if os.path.isdir(os.path.join(repo, "control", "lib")):
            paths.append(os.path.join(repo, "control", "lib"))
            break
        repo = os.path.dirname(repo)
    return paths


def ensure_lib_path():
    for p in lib_paths():
        if p and p not in sys.path and os.path.isdir(p):
            sys.path.insert(0, p)


def main(argv=None):
    """``adb-connect``: the gated connect for shell callers (cf-agent, the Mac's
    ssh health gather). Prints device|waiting|down; exit 0 only for device."""
    args = sys.argv[1:] if argv is None else argv
    if args[:1] != ["adb-connect"]:
        sys.stderr.write("usage: stayturgid_shell.py adb-connect\n")
        return 64
    _ensure_env()
    state = adb_connect()
    print(state)
    if state == "waiting":
        sys.stderr.write(ADB_AUTH_WAITING_MSG + "\n")
    return 0 if state == "device" else (2 if state == "waiting" else 1)


if __name__ == "__main__":
    sys.exit(main())
