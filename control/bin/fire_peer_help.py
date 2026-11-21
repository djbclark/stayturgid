#!/usr/bin/env python3
"""Mac-side peer ADB helper (Handsets / Shizuku on Fire via Mac adb).

Same verbs as Termux ``stayturgid_peer_help.py``, using Mac
``~/.config/stayturgid/adbkey`` and ``~/.handsets/hs.jar``.

Usage:
  python3 control/bin/fire_peer_help.py handsets-start --target IP:5555 --serial USB_SERIAL [--port N]
  python3 control/bin/fire_peer_help.py shizuku-start --target IP:5555 --serial USB_SERIAL
  python3 control/bin/fire_peer_help.py ping --target IP:5555 --serial USB_SERIAL

``--serial`` is the requester's USB serial; after ``adb connect`` the target's ``ro.serialno``
must equal it or the helper disconnects and refuses (#328, fail closed).

When invoked via SSH ForceCommand, reads ``SSH_ORIGINAL_COMMAND``.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path.home() / ".config" / "stayturgid"
FLEET_ADBKEY = Path(os.environ.get("STAYTURGID_FLEET_ADBKEY", ROOT / "adbkey"))
DEFAULT_JAR = Path(os.environ.get("STAYTURGID_HS_JAR", Path.home() / ".handsets" / "hs.jar"))
REMOTE_JAR = "/data/local/tmp/hs.jar"
SHIZUKU_PKG = "moe.shizuku.privileged.api"
ADB = os.environ.get("STAYTURGID_ADB", "/opt/homebrew/bin/adb")

# On-device native-starter resolution, POSIX sh (toybox/mksh) only — no
# bash-isms: prefer the device's primary ABI's lib dir, else the first
# executable <apkdir>/lib/*/libshizuku.so. No shared-storage start.sh fallback;
# a missing starter fails the command. Kept faithful to stayturgid_device.py.
_SHIZUKU_NATIVE_START = (
    "d=@APKDIR@; "
    "abi=$(getprop ro.product.cpu.abi 2>/dev/null); "
    'case "$abi" in arm64-v8a) abi=arm64;; armeabi-v7a) abi=arm;; x86_64) abi=x86_64;; x86) abi=x86;; *) abi= ;; esac; '
    "libdir=; "
    'if [ -n "$abi" ] && [ -x "$d/lib/$abi/libshizuku.so" ]; then libdir=$d/lib/$abi; '
    'else for e in "$d"/lib/*/libshizuku.so; do if [ -x "$e" ]; then libdir=${e%/*}; break; fi; done; fi; '
    'if [ -n "$libdir" ]; then LD_LIBRARY_PATH=$libdir "$libdir/libshizuku.so"; '
    'else echo "shizuku native starter not found" >&2; exit 1; fi'
)


def _adb_env() -> dict[str, str]:
    env = os.environ.copy()
    if FLEET_ADBKEY.is_file():
        keys = str(FLEET_ADBKEY)
        device_key = Path.home() / ".android" / "adbkey"
        if device_key.is_file():
            keys = keys + ":" + str(device_key)
        existing = env.get("ADB_VENDOR_KEYS", "")
        if existing:
            keys = keys + ":" + existing
        env["ADB_VENDOR_KEYS"] = keys
    return env


def _adb(*args: str, timeout: float = 45) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ADB, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_adb_env(),
    )


def _ensure_connected(target: str, timeout: float = 20) -> None:
    _adb("connect", target, timeout=timeout)
    d = _adb("devices", timeout=15)
    state = None
    for line in (d.stdout or "").splitlines():
        if line.startswith(target) or (line.split() and line.split()[0] == target):
            parts = line.split()
            if len(parts) >= 2:
                state = parts[1]
            break
    if state == "device":
        return
    if state == "unauthorized":
        raise SystemExit("adb %s unauthorized — accept Always allow on target (fleet adbkey)" % target)
    raise SystemExit("adb connect %s failed (state=%s)" % (target, state))


# A USB serial is alphanumeric plus a few separators; anything else is refused before adb runs.
_SERIAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
# A peer-help target is a routable IPv4 LAN/Tailscale address on the fleet's adb port: never
# loopback (the helper's own adbd), a hostname, or a USB serial the local adb server also lists.
_TARGET_RE = re.compile(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}:5555")


def valid_serial(serial: str | None) -> bool:
    return serial is not None and _SERIAL_RE.fullmatch(serial) is not None


def valid_target(target: str | None) -> bool:
    if target is None or _TARGET_RE.fullmatch(target) is None:
        return False
    octets = [int(o) for o in target.split(":")[0].split(".")]
    return all(o <= 255 for o in octets) and octets[0] not in (0, 127)


def _already_listed(target: str) -> bool:
    """True when the adb server already holds a transport named ``target`` (before our connect)."""
    r = _adb("devices", timeout=15)
    return any(line.split() and line.split()[0] == target for line in (r.stdout or "").splitlines())


def verify_identity(target: str, serial: str | None, *, disconnect: bool = True) -> None:
    """Exit unless the device at adb ``target`` reports ``ro.serialno == serial`` (fail closed).

    An unknown serial, an unreadable serial and a mismatch all refuse (#328): a drifted DHCP
    address may now answer for another phone. ``disconnect`` drops the transport this request
    created; it is False when the adb server already held it, because that transport belongs to
    the helper's other tooling. Mirrors the Mac-side ``endpoint_identity_ok``.
    """

    def refuse(message: str) -> None:
        if disconnect:
            _adb("disconnect", target, timeout=10)
        raise SystemExit(message)

    if not valid_serial(serial):
        refuse("refusing %s: no valid requester USB serial to identity-check it against" % target)
    r = _adb("-s", target, "shell", "getprop", "ro.serialno", timeout=15)
    found = (r.stdout or "").replace("\r", "").strip() if r.returncode == 0 else ""
    if found == serial:
        return
    if found:
        refuse("refusing %s: its ro.serialno is %r, expected %r" % (target, found, serial))
    refuse("refusing %s: could not read ro.serialno to confirm it is %r" % (target, serial))


def _identity_checked(target: str, serial: str | None) -> None:
    """Prove ``target`` is the requester before any verb touches it.

    Validates the serial and the target form first, so a bad request does no adb work at all;
    then connects and reads ``ro.serialno``. Only a transport this call created is disconnected.
    """
    if not valid_serial(serial):
        raise SystemExit("refusing %s: no valid requester USB serial to identity-check it against" % target)
    if not valid_target(target):
        raise SystemExit("refusing target %r: peer help only drives IPv4-address:5555 targets" % target)
    preexisting = _already_listed(target)
    _ensure_connected(target)
    verify_identity(target, serial, disconnect=not preexisting)


def _shell(target: str, cmd: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return _adb("-s", target, "shell", cmd, timeout=timeout)


def cmd_ping(target: str) -> int:
    _ensure_connected(target)
    r = _shell(target, "id -u", timeout=15)
    uid = (r.stdout or "").strip().replace("\r", "")
    if r.returncode != 0 or uid != "2000":
        print("FAIL uid=%r" % uid, file=sys.stderr)
        return 1
    print("OK shell uid=2000 target=%s" % target)
    return 0


def cmd_status(target: str) -> int:
    _ensure_connected(target)
    r = _shell(
        target,
        "id -u; pgrep -af '[s]hizuku_(plus_)?server' | head -2; "
        "pgrep -af 'dev.handsets.daemon.Main' | head -3; "
        "test -f %s && echo jar=ok || echo jar=missing" % REMOTE_JAR,
        timeout=20,
    )
    print((r.stdout or "").replace("\r", "").strip())
    return 0 if r.returncode == 0 else 1


def _push_jar(target: str) -> None:
    if not DEFAULT_JAR.is_file():
        check = _shell(target, "test -f %s && echo ok" % REMOTE_JAR, timeout=10)
        if "ok" in (check.stdout or ""):
            return
        raise SystemExit("hs.jar missing (%s)" % DEFAULT_JAR)
    r = _adb("-s", target, "push", str(DEFAULT_JAR), REMOTE_JAR, timeout=60)
    if r.returncode != 0:
        raise SystemExit("adb push hs.jar failed: %s" % ((r.stderr or "").strip()))


def cmd_handsets_start(target: str, port: int) -> int:
    _ensure_connected(target)
    _push_jar(target)
    nice = "hsd%d" % port
    _shell(
        target,
        "pkill -f '%s' 2>/dev/null; pkill -f 'dev.handsets.daemon.Main --port=%d' 2>/dev/null; true" % (nice, port),
        timeout=15,
    )
    time.sleep(0.3)
    start = (
        "CLASSPATH=%s nohup app_process /system/bin --nice-name=%s "
        "dev.handsets.daemon.Main --port=%d >/data/local/tmp/%s.log 2>&1 &" % (REMOTE_JAR, nice, port, nice)
    )
    _shell(target, start, timeout=15)
    deadline = time.time() + 12
    while time.time() < deadline:
        r = _shell(
            target,
            "toybox nc -z 127.0.0.1 %d >/dev/null 2>&1 && echo up || "
            "(ss -lntp 2>/dev/null | grep -q ':%d' && echo up || "
            "grep -q 'listening' /data/local/tmp/%s.log 2>/dev/null && echo up || echo down)" % (port, port, nice),
            timeout=10,
        )
        if "up" in (r.stdout or ""):
            print("OK handsets port=%d target=%s" % (port, target))
            return 0
        time.sleep(0.4)
    log = _shell(target, "tail -20 /data/local/tmp/%s.log" % nice, timeout=10)
    print("FAIL handsets: %s" % ((log.stdout or "").strip()), file=sys.stderr)
    return 1


def cmd_shizuku_start(target: str) -> int:
    _ensure_connected(target)
    r = _shell(target, "pm path %s" % SHIZUKU_PKG, timeout=15)
    apk = ""
    for line in (r.stdout or "").splitlines():
        line = line.strip().replace("\r", "")
        if line.startswith("package:"):
            apk = line.split(":", 1)[1]
            break
    if not apk:
        print("FAIL Shizuku not installed", file=sys.stderr)
        return 1
    start = _SHIZUKU_NATIVE_START.replace("@APKDIR@", apk.rsplit("/", 1)[0])
    out = _shell(target, start, timeout=30)
    text = ((out.stdout or "") + (out.stderr or "")).replace("\r", "")
    time.sleep(1.5)
    check = _shell(target, "pgrep -f '[s]hizuku_(plus_)?server' >/dev/null && echo up", timeout=10)
    if "up" in (check.stdout or ""):
        print("OK shizuku_server target=%s" % target)
        return 0
    print("FAIL shizuku start: %s" % text.strip()[:500], file=sys.stderr)
    return 1


def run_verb(verb: str, target: str, port: int, serial: str | None) -> int:
    if verb not in ("handsets-start", "shizuku-start", "ping", "status"):
        print("unknown verb %r" % verb, file=sys.stderr)
        return 2
    _identity_checked(target, serial)
    if verb == "ping":
        return cmd_ping(target)
    if verb == "status":
        return cmd_status(target)
    if verb == "handsets-start":
        return cmd_handsets_start(target, port)
    if verb == "shizuku-start":
        return cmd_shizuku_start(target)
    print("unknown verb %r" % verb, file=sys.stderr)
    return 2


def _from_ssh_original() -> int | None:
    raw = os.environ.get("SSH_ORIGINAL_COMMAND")
    if not raw:
        return None
    # Expected: python3 …/fire_peer_help.py VERB --target T [--port N]
    # or: fire_peer_help.py VERB …
    try:
        parts = shlex.split(raw)
    except ValueError:
        print("denied: bad SSH_ORIGINAL_COMMAND", file=sys.stderr)
        return 1
    # Find verb among known tokens
    verbs = ("handsets-start", "shizuku-start", "ping", "status")
    verb = None
    target = None
    serial = None
    port = 9012
    i = 0
    while i < len(parts):
        if parts[i] in verbs and verb is None:
            verb = parts[i]
        elif parts[i] == "--target" and i + 1 < len(parts):
            target = parts[i + 1]
            i += 1
        elif parts[i] == "--serial" and i + 1 < len(parts):
            serial = parts[i + 1]
            i += 1
        elif parts[i] == "--port" and i + 1 < len(parts):
            port = int(parts[i + 1])
            i += 1
        i += 1
    if not verb or not target or not valid_serial(serial):
        print("denied: need verb + --target + --serial", file=sys.stderr)
        return 1
    return run_verb(verb, target, port, serial)


def main(argv: list[str] | None = None) -> int:
    ssh_rc = _from_ssh_original()
    if ssh_rc is not None:
        return ssh_rc
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("verb", choices=("handsets-start", "shizuku-start", "ping", "status"))
    p.add_argument("--target", required=True)
    p.add_argument("--serial", required=True, help="USB serial the target must report as ro.serialno")
    p.add_argument("--port", type=int, default=9012)
    args = p.parse_args(argv)
    return run_verb(args.verb, args.target, args.port, args.serial)


if __name__ == "__main__":
    raise SystemExit(main())
