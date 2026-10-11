#!/usr/bin/env python3
"""Peer helper: start Handsets / Shizuku on a remote device via ADB.

Runs on a helper phone (oneui-device/stock-android-device) that already has a trusted ADB key on the
target. Invoked over SSH from a Fire OS device that cannot self-ADB.

Usage:
  stayturgid_peer_help.py handsets-start --target IP:5555 [--port N]
  stayturgid_peer_help.py shizuku-start --target IP:5555
  stayturgid_peer_help.py ping --target IP:5555
  stayturgid_peer_help.py status --target IP:5555

Env:
  STAYTURGID_HS_JAR   local path to push (default ~/.stayturgid/lib/hs.jar)
  ANDROID_SDK_HOME / HOME — adb uses ~/.android/adbkey (fleet-shared key)
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time

try:
    import stayturgid_shell
except ImportError:
    stayturgid_shell = None

HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
STG = os.path.join(HOME, ".stayturgid")
DEFAULT_JAR = os.path.join(STG, "lib", "hs.jar")
REMOTE_JAR = "/data/local/tmp/hs.jar"
SHIZUKU_PKG = "moe.shizuku.privileged.api"
# Shared fleet identity — do NOT overwrite ~/.android/adbkey (breaks localhost:5555).
FLEET_ADBKEY = os.environ.get("STAYTURGID_FLEET_ADBKEY", os.path.join(STG, "adbkey-fleet"))

# On-device native-starter resolution, POSIX sh (toybox/mksh) only — no
# bash-isms: prefer the device's primary ABI's lib dir, else the first
# executable <apkdir>/lib/*/libshizuku.so. ``@APKDIR@`` is replaced with a
# shlex.quote()d apk dir. No shared-storage start.sh fallback; a missing
# starter fails the command.
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
    if stayturgid_shell is not None:
        # This adb is Termux's own server; a peer connect can be what starts it.
        stayturgid_shell.pin_adb_server_env(env)
    if os.path.isfile(FLEET_ADBKEY):
        # Prefer fleet key for peer connections; keep device key as fallback.
        existing = env.get("ADB_VENDOR_KEYS", "")
        keys = FLEET_ADBKEY
        device_key = os.path.join(HOME, ".android", "adbkey")
        if os.path.isfile(device_key) and device_key != FLEET_ADBKEY:
            keys = FLEET_ADBKEY + ":" + device_key
        if existing:
            keys = keys + ":" + existing
        env["ADB_VENDOR_KEYS"] = keys
    return env


def _adb(*args: str, timeout: float = 45) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_adb_env(),
    )


def _ensure_connected(target: str, timeout: float = 20) -> None:
    r = _adb("connect", target, timeout=timeout)
    ((r.stdout or "") + (r.stderr or "")).lower()
    # Refresh device list
    d = _adb("devices", timeout=15)
    lines = (d.stdout or "").splitlines()
    state = None
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == target or line.startswith(target):
            if len(parts) >= 2:
                state = parts[1]
            break
    if state == "device":
        return
    if state == "unauthorized":
        raise SystemExit("adb %s unauthorized — accept Always allow on target once (shared fleet adbkey)" % target)
    if state == "offline":
        raise SystemExit("adb %s offline" % target)
    raise SystemExit("adb connect %s failed (state=%s): %s" % (target, state, (r.stdout or r.stderr or "").strip()))


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
    src = os.environ.get("STAYTURGID_HS_JAR", DEFAULT_JAR)
    if not os.path.isfile(src):
        # Fall back to already-on-device jar
        check = _shell(target, "test -f %s && echo ok" % REMOTE_JAR, timeout=10)
        if "ok" in (check.stdout or ""):
            return
        raise SystemExit("hs.jar missing locally (%s) and on target" % src)
    r = _adb("-s", target, "push", src, REMOTE_JAR, timeout=60)
    if r.returncode != 0:
        raise SystemExit("adb push hs.jar failed: %s" % ((r.stderr or r.stdout or "").strip()))


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
        # Daemon binds 127.0.0.1 on the *target* — probe via adb shell.
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
    print(
        "FAIL handsets not ready: %s" % ((log.stdout or "").strip()),
        file=sys.stderr,
    )
    return 1


def start_shizuku_native(shell) -> tuple[bool, str]:
    """Run Shizuku's own starter (libshizuku.so, resolved on the device).

    ``shell(cmd, timeout)`` runs one command in an adb shell that is already
    authorised on the target and returns ``(rc, stdout, stderr)``. The starter
    never goes through the manager app, so it offers Shizuku's ADB key to
    nobody and raises no dialog. The native lib dir is resolved from the
    installed APK (the device's primary ABI) rather than assumed arm64; there
    is no shared-storage ``start.sh`` fallback. Returns ``(ok, detail)``;
    ``detail`` is the failure reason when ``ok`` is False.
    """
    _rc, out, _err = shell("pm path %s" % SHIZUKU_PKG, 15)
    apk = ""
    for line in (out or "").splitlines():
        line = line.strip().replace("\r", "")
        if line.startswith("package:"):
            apk = line.split(":", 1)[1]
            break
    if not apk:
        return False, "Shizuku not installed"
    start = _SHIZUKU_NATIVE_START.replace("@APKDIR@", shlex.quote(apk.rsplit("/", 1)[0]))
    _rc, out, err = shell(start, 30)
    text = ((out or "") + (err or "")).replace("\r", "")
    time.sleep(1.5)
    _rc, check, _err = shell("pgrep -f '[s]hizuku_(plus_)?server' >/dev/null && echo up", 10)
    if "up" in (check or ""):
        return True, ""
    return False, "shizuku start: %s" % text.strip()[:500]


def cmd_shizuku_start(target: str) -> int:
    _ensure_connected(target)

    def shell(cmd: str, timeout: float) -> tuple[int, str, str]:
        r = _shell(target, cmd, timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""

    ok, detail = start_shizuku_native(shell)
    if ok:
        print("OK shizuku_server target=%s" % target)
        return 0
    print("FAIL %s" % detail, file=sys.stderr)
    return 1


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "verb",
        choices=("handsets-start", "shizuku-start", "ping", "status"),
    )
    p.add_argument("--target", required=True, help="host:port of target adbd")
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("STAYTURGID_HANDSETS_PORT", "9012")),
        help="Handsets daemon port on target (default from STAYTURGID_HANDSETS_PORT, else 9012)",
    )
    args = p.parse_args(argv)
    if args.verb == "ping":
        return cmd_ping(args.target)
    if args.verb == "status":
        return cmd_status(args.target)
    if args.verb == "handsets-start":
        return cmd_handsets_start(args.target, args.port)
    if args.verb == "shizuku-start":
        return cmd_shizuku_start(args.target)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
