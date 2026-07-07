#!/usr/bin/env python3
"""Live Tailscale-down test — use USB serial (Tailscale SSH may blip).

Usage: ./test_tailscale_down.py [s24|RFCX219CHKA]

1. Mac: force-stop Tailscale + wait for coord ping to fail
2. AutoJs6: probe, run watchdog cycle (notify + relaunch path), wait for recovery
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "mac"))
import adb_cli as adb  # noqa: E402

SCRIPT = f"{adb.AUTOJS_PROJECT_BASE}/scripts/test-tailscale-down-once.js"
TS_PKG = "com.tailscale.ipn"
USB_S24 = "RFCX219CHKA"


def resolve_serial(alias: str) -> str:
    devices = adb.adb_devices()
    if f"{USB_S24}\tdevice" in devices.replace("\r", ""):
        return USB_S24
    return adb.resolve_target(alias)


def shell_line(serial: str, cmd: str) -> str:
    result = adb.adb(serial, "shell", cmd)
    return (result.stdout or "").strip()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    alias = argv[0] if argv else "s24"
    serial = resolve_serial(alias)

    print(f"=== Phase 1: baseline (USB {serial}) ===")
    adb.adb(serial, "shell", "input keyevent KEYCODE_WAKEUP", check=False)
    print(shell_line(serial, "ping -c1 -W2 100.100.100.100 >/dev/null && echo baseline_ping=ok || echo baseline_ping=fail"))

    print("=== Phase 2: force-stop Tailscale + wait for tunnel blip ===")
    adb.adb(serial, "shell", f"am force-stop {TS_PKG}", check=False)
    for i in range(1, 16):
        time.sleep(1)
        ping = adb.adb(serial, "shell", "ping -c1 -W2 100.100.100.100", check=False)
        if ping.returncode != 0:
            print(f"coord ping failed after {i}s")
            break

    print("=== Phase 3: AutoJs6 probe + watchdog + relaunch ===")
    adb.start_autojs_file(serial, SCRIPT)

    print("Waiting up to 60s for recovery...")
    for _ in range(12):
        time.sleep(5)
        line = shell_line(
            serial,
            "grep tailscale-down-test /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1",
        )
        if "after-relaunch" in line:
            break

    print("--- tailscale-down-test log lines ---")
    print(
        shell_line(
            serial,
            "grep -E 'tailscale-down-test|tailscale tun=' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -10",
        )
    )
    probe_down = shell_line(
        serial,
        "grep 'tailscale-down-test probe' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1",
    )
    recovered = shell_line(
        serial,
        "grep 'after-relaunch' /sdcard/stayturgid/logs/watchdog.log 2>/dev/null | tail -1",
    )

    if "up=false" in probe_down:
        print("PASS: probe detected Tailscale down")
    else:
        print(f"WARN: probe did not report up=false — {probe_down}", file=sys.stderr)

    if "after-relaunch" in recovered and "up=true" in recovered:
        print("PASS: Tailscale recovered after relaunch")
        return 0

    print(f"FAIL: recovery not confirmed — {recovered}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
