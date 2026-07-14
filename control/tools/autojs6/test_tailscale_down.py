#!/usr/bin/env python3
"""Live Tailscale-down test — use USB serial (Tailscale SSH may blip).

Usage: ./test_tailscale_down.py [s24|RFCX219CHKA]

1. Mac: force-stop Tailscale + wait for coord ping to fail
2. AutoJs6: probe, relaunch, wait for recovery (logged to watchdog.log)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as adb  # noqa: E402
import stayturgid_device as dev  # noqa: E402

SCRIPT = f"{adb.AUTOJS_PROJECT_BASE}/scripts/test-tailscale-down-once.js"
WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
TS_PKG = "com.tailscale.ipn"
PROBE_START = "tailscale-down-test probe start"
PROBE_MARKER = "tailscale-down-test probe tun="
RECOVERY_MARKER = "tailscale-down-test after-relaunch"


def resolve_serial(alias: str) -> str:
    """USB when plugged in, else first online wireless endpoint for this alias."""
    return dev.resolve_adb(alias)


def is_tailscale_path(alias: str, serial: str) -> bool:
    """True when the resolved adb target is the device's Tailscale ip:5555.

    This test force-stops Tailscale; if adb itself rides the Tailscale tunnel
    the transport drops mid-test (device goes offline, no log output). Require
    a USB or LAN adb path instead.
    """
    row = dev.device_row(alias)
    if not row:
        return False
    _usb, ts_ip, _lan = row
    return bool(ts_ip and ts_ip != "-" and serial == "%s:5555" % ts_ip)


def shell_line(serial: str, cmd: str) -> str:
    result = adb.adb(serial, "shell", cmd)
    return (result.stdout or "").strip()


def log_tail(serial: str, pattern: str) -> str:
    return shell_line(
        serial,
        f"grep -F '{pattern}' {WATCHDOG_LOG} 2>/dev/null | tail -1",
    )


def wait_for_log(serial: str, pattern: str, timeout_s: int) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        line = log_tail(serial, pattern)
        if line:
            return line
        time.sleep(2)
    return ""


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    alias = argv[0] if argv else "s24"
    serial = resolve_serial(alias)
    rc = 0

    if is_tailscale_path(alias, serial):
        print(
            f"ABORT: adb target {serial} rides the Tailscale tunnel this test kills.\n"
            f"       Plug in USB or expose LAN adb (adb tcpip 5555) for {alias}, then rerun.",
            file=sys.stderr,
        )
        return 2

    print(f"=== Phase 1: baseline (USB {serial}) ===")
    adb.adb(serial, "shell", "input keyevent KEYCODE_WAKEUP", check=False)
    print(
        shell_line(
            serial, "ping -c1 -W2 100.100.100.100 >/dev/null && echo baseline_ping=ok || echo baseline_ping=fail"
        )
    )

    print("=== Phase 2: force-stop Tailscale + wait for tunnel blip ===")
    adb.adb(serial, "shell", f"am force-stop {TS_PKG}", check=False)
    blip_s = 0
    for i in range(1, 16):
        time.sleep(1)
        ping = adb.adb(serial, "shell", "ping -c1 -W2 100.100.100.100", check=False)
        if ping.returncode != 0:
            blip_s = i
            print(f"coord ping failed after {i}s")
            break
    if not blip_s:
        print("WARN: coord ping never failed — Tailscale may already be recovering", file=sys.stderr)

    print("=== Phase 3: AutoJs6 probe + relaunch ===")
    adb.start_autojs_file(serial, SCRIPT)

    print("Waiting up to 30s for AutoJs6 probe start...")
    probe_start = wait_for_log(serial, PROBE_START, 30)
    if not probe_start:
        print("FAIL: AutoJs6 test script produced no log output", file=sys.stderr)
        print("--- recent watchdog log ---")
        print(shell_line(serial, f"tail -15 {WATCHDOG_LOG} 2>/dev/null"))
        return 1

    print("Waiting up to 90s for Tailscale recovery log line...")
    recovered = wait_for_log(serial, RECOVERY_MARKER, 90)

    print("--- tailscale-down-test log lines ---")
    print(
        shell_line(
            serial,
            f"grep -E 'tailscale-down-test|tailscale tun=' {WATCHDOG_LOG} 2>/dev/null | tail -10",
        )
    )

    probe_down = log_tail(serial, PROBE_MARKER)
    if "up=false" in probe_down:
        print("PASS: probe detected Tailscale down")
    elif probe_down:
        print(
            f"NOTE: probe saw Tailscale up={probe_down.split('up=')[-1] if 'up=' in probe_down else '?'} (VPN may have restarted before probe)"
        )
    else:
        print(f"WARN: no probe tun line — {probe_down}", file=sys.stderr)
        rc = 1

    if recovered and "up=true" in recovered:
        print("PASS: Tailscale recovered after relaunch")
        return 0 if rc == 0 else 1

    print(f"FAIL: recovery not confirmed — {recovered}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
