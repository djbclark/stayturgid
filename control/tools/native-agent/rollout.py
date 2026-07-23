#!/usr/bin/env python3
"""Roll out stayturgid native-agent to one or more fleet hosts.

Steps per host (when adb-reachable):
  1. adb install -r debug APK
  2. grant_shizuku.py (pm + shizuku.json)
  3. restart Shizuku via /data/local/tmp/shizuku_starter (if present)
  4. start_agent.py (MainActivity → HostService)

Does **not** remove AutoJs6. Dual-run only (OPTIONS K1).

Usage:
  ./rollout.py                     # all hosts from devices.conf
  ./rollout.py device1 device2     # named aliases
  ./rollout.py --serial 100.x:5555 # raw serial only
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "control" / "lib"))
import stayturgid_device as dev  # noqa: E402

APK = REPO / "device" / "native-agent" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
GRANT = REPO / "control" / "tools" / "native-agent" / "grant_shizuku.py"
START = REPO / "control" / "tools" / "native-agent" / "start_agent.py"
PKG = "org.stayturgid.agent.debug"


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ensure_apk() -> Path:
    if APK.is_file():
        return APK
    print("APK missing — building (just agent-assemble)...")
    env = os.environ.copy()
    # Prefer JDK 21 for AGP
    for cand in (
        "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home",
        "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home",
    ):
        if Path(cand, "bin", "java").is_file():
            env["JAVA_HOME"] = cand
            env["PATH"] = f"{cand}/bin:" + env.get("PATH", "")
            break
    r = _run(["just", "agent-assemble"], timeout=600)
    if r.returncode != 0 or not APK.is_file():
        sys.stderr.write((r.stdout or "") + (r.stderr or "") + "\n")
        raise SystemExit("assemble failed")
    return APK


def resolve_serial(alias_or_serial: str) -> str | None:
    # Already looks like host:port or bare serial
    if ":" in alias_or_serial or alias_or_serial.startswith("RFC") or len(alias_or_serial) > 12:
        if alias_or_serial.count(":") == 1 and alias_or_serial.split(":")[0].replace(".", "").isdigit():
            # ts/lan ip:5555 — try connect
            _run(["adb", "connect", alias_or_serial], timeout=15)
            return alias_or_serial
    try:
        serial = dev.resolve_adb(alias_or_serial)
    except Exception as e:
        print(f"  resolve_adb failed: {e}")
        return None
    if not serial:
        return None
    # Prefer wireless connect when serial is host:port
    if ":" in serial:
        _run(["adb", "connect", serial], timeout=15)
    return serial


def device_online(serial: str) -> bool:
    r = _run(["adb", "-s", serial, "get-state"], timeout=10)
    return r.returncode == 0 and (r.stdout or "").strip() == "device"


def rollout_one(label: str, serial: str) -> bool:
    print(f"\n=== {label} ({serial}) ===")
    if not device_online(serial):
        print("  SKIP: adb not online")
        return False
    apk = ensure_apk()
    print(f"  install {apk.name}...")
    r = _run(["adb", "-s", serial, "install", "-r", str(apk)], timeout=180)
    if r.returncode != 0:
        print("  FAIL install:", (r.stderr or r.stdout or "")[:300])
        return False
    print("  grant Shizuku...")
    r = _run([sys.executable, str(GRANT), serial], timeout=90)
    print(
        "   ", (r.stdout or r.stderr or "").strip().splitlines()[-1] if (r.stdout or r.stderr) else f"rc={r.returncode}"
    )
    if r.returncode != 0:
        print("  WARN grant failed — continue start attempt")
    # Restart Shizuku so json grant is live (starter may no-op if missing)
    print("  restart Shizuku server...")
    st = _run(
        ["adb", "-s", serial, "shell", "/data/local/tmp/shizuku_starter"],
        timeout=30,
    )
    if st.stdout:
        for line in st.stdout.strip().splitlines()[-4:]:
            print("   ", line)
    time.sleep(4)
    srv = _run(
        ["adb", "-s", serial, "shell", "pgrep -f shizuku_server"],
        timeout=10,
    )
    if not (srv.stdout or "").strip():
        print("  WARN: shizuku_server not running after starter (UserService will not bind)")
    print("  start agent...")
    r = _run([sys.executable, str(START), serial], timeout=90)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    for line in out.splitlines()[-6:]:
        print("   ", line)
    if r.returncode != 0:
        print("  FAIL start")
        return False
    # verify package version + recent STATUS
    ver = _run(
        ["adb", "-s", serial, "shell", f"dumpsys package {PKG}"],
        timeout=30,
    )
    for line in (ver.stdout or "").splitlines():
        if "versionName=" in line:
            print(" ", line.strip())
            break
    time.sleep(4)
    log = _run(
        ["adb", "-s", serial, "shell", "tail -3 /sdcard/stayturgid/logs/agent.log 2>/dev/null"],
        timeout=15,
    )
    if log.stdout:
        print("  agent.log:")
        for line in log.stdout.strip().splitlines()[-3:]:
            print("   ", line)
    else:
        print("  WARN: no agent.log yet (Shizuku bind may still be settling)")
    print("  OK")
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("hosts", nargs="*", help="device aliases from devices.conf")
    p.add_argument("--serial", action="append", default=[], help="raw adb serial(s)")
    args = p.parse_args(argv)

    targets: list[tuple[str, str]] = []
    for s in args.serial:
        serial = resolve_serial(s) or s
        targets.append((s, serial))
    for h in args.hosts:
        serial = resolve_serial(h)
        if serial:
            targets.append((h, serial))
        else:
            print(f"=== {h} ===\n  SKIP: could not resolve adb serial")
    if not targets and not args.serial and not args.hosts:
        conf = os.environ.get(
            "STAYTURGID_DEVICES_CONF",
            os.path.join(os.path.expanduser("~"), ".config", "stayturgid", "devices.conf"),
        )
        for name, ts_ip, _lan in dev.iter_monitor_hosts(conf):
            # Prefer ts:5555 then resolve_adb
            serial = None
            if ts_ip and ts_ip != "-":
                cand = f"{ts_ip}:5555"
                _run(["adb", "connect", cand], timeout=15)
                if device_online(cand):
                    serial = cand
            if not serial:
                serial = resolve_serial(name)
            if serial:
                targets.append((name, serial))
            else:
                print(f"=== {name} ===\n  SKIP: unreachable / no adb")

    if not targets:
        print("No reachable targets.")
        return 1

    ensure_apk()
    ok = 0
    fail = 0
    skip = 0
    for label, serial in targets:
        try:
            if rollout_one(label, serial):
                ok += 1
            else:
                # distinguish skip vs fail crudely
                if not device_online(serial):
                    skip += 1
                else:
                    fail += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            fail += 1

    print(f"\nRollout summary: ok={ok} fail={fail} skip={skip} total={len(targets)}")
    print("AutoJs6 left installed (dual-run). See docs/archive/plans/native-agent-status-2026-07-22.md")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
