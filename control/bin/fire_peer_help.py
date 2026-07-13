#!/usr/bin/env python3
"""Mac-side peer ADB helper (Handsets / Shizuku on Fire via Mac adb).

Same verbs as Termux ``stayturgid_peer_help.py``, using Mac
``~/.config/stayturgid/adbkey`` and ``~/.handsets/hs.jar``.

Usage:
  python3 control/bin/fire_peer_help.py handsets-start --target IP:5555 [--port N]
  python3 control/bin/fire_peer_help.py shizuku-start --target IP:5555
  python3 control/bin/fire_peer_help.py ping --target IP:5555

When invoked via SSH ForceCommand, reads ``SSH_ORIGINAL_COMMAND``.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path.home() / ".config" / "stayturgid"
FLEET_ADBKEY = Path(os.environ.get("STAYTURGID_FLEET_ADBKEY", ROOT / "adbkey"))
DEFAULT_JAR = Path(
    os.environ.get("STAYTURGID_HS_JAR", Path.home() / ".handsets" / "hs.jar")
)
REMOTE_JAR = "/data/local/tmp/hs.jar"
SHIZUKU_PKG = "moe.shizuku.privileged.api"
ADB = os.environ.get("STAYTURGID_ADB", "/opt/homebrew/bin/adb")


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
        raise SystemExit(
            "adb %s unauthorized — accept Always allow on target (fleet adbkey)"
            % target
        )
    raise SystemExit("adb connect %s failed (state=%s)" % (target, state))


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
        "id -u; pgrep -af '[s]hizuku_server' | head -2; "
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
        "pkill -f '%s' 2>/dev/null; "
        "pkill -f 'dev.handsets.daemon.Main --port=%d' 2>/dev/null; true"
        % (nice, port),
        timeout=15,
    )
    time.sleep(0.3)
    start = (
        "CLASSPATH=%s nohup app_process /system/bin --nice-name=%s "
        "dev.handsets.daemon.Main --port=%d >/data/local/tmp/%s.log 2>&1 &"
        % (REMOTE_JAR, nice, port, nice)
    )
    _shell(target, start, timeout=15)
    deadline = time.time() + 12
    while time.time() < deadline:
        r = _shell(
            target,
            "toybox nc -z 127.0.0.1 %d >/dev/null 2>&1 && echo up || "
            "(ss -lntp 2>/dev/null | grep -q ':%d' && echo up || "
            "grep -q 'listening' /data/local/tmp/%s.log 2>/dev/null && echo up || echo down)"
            % (port, port, nice),
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
    libdir = apk.rsplit("/", 1)[0] + "/lib/arm64"
    start = (
        "test -x %s/libshizuku.so && "
        "LD_LIBRARY_PATH=%s %s/libshizuku.so || "
        "sh /storage/emulated/0/Android/data/%s/start.sh"
        % (libdir, libdir, libdir, SHIZUKU_PKG)
    )
    out = _shell(target, start, timeout=30)
    text = ((out.stdout or "") + (out.stderr or "")).replace("\r", "")
    time.sleep(1.5)
    check = _shell(target, "pgrep -f '[s]hizuku_server' >/dev/null && echo up", timeout=10)
    if "up" in (check.stdout or ""):
        print("OK shizuku_server target=%s" % target)
        return 0
    print("FAIL shizuku start: %s" % text.strip()[:500], file=sys.stderr)
    return 1


def run_verb(verb: str, target: str, port: int) -> int:
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
    port = 9012
    i = 0
    while i < len(parts):
        if parts[i] in verbs and verb is None:
            verb = parts[i]
        elif parts[i] == "--target" and i + 1 < len(parts):
            target = parts[i + 1]
            i += 1
        elif parts[i] == "--port" and i + 1 < len(parts):
            port = int(parts[i + 1])
            i += 1
        i += 1
    if not verb or not target:
        print("denied: need verb + --target", file=sys.stderr)
        return 1
    return run_verb(verb, target, port)


def main(argv: list[str] | None = None) -> int:
    ssh_rc = _from_ssh_original()
    if ssh_rc is not None:
        return ssh_rc
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("verb", choices=("handsets-start", "shizuku-start", "ping", "status"))
    p.add_argument("--target", required=True)
    p.add_argument("--port", type=int, default=9012)
    args = p.parse_args(argv)
    return run_verb(args.verb, args.target, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
