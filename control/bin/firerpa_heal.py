#!/usr/bin/env python3
# @heals: SSHD-RUNNING SHIZUKU-HEADLESS BOOTLOOP-ALIVE
"""FIRERPA self-heal: repair stayturgid services via FIRERPA gRPC API.

Runs on the Mac control node. Connects to FIRERPA on each device via
Tailscale IP:65000. Uses FIRERPA's gRPC API (which works without SSH or
ADB) to repair stayturgid when primary channels are down.

Usage:
  python3 control/bin/firerpa_heal.py [--host s24] [--all]

Requirements: pip install lamda-client (from firerpa-binaries or fork release)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT / "control" / "lib", REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.append(str(_p))
from control.lib.firerpa_auth import certificate_path  # noqa: E402
from control.lib.logging import (  # noqa: E402
    ERR,
    INFO,
    NOTICE,
    WARNING,
    log,
    trim_log,
)

try:
    from lamda.client import Device
except ImportError:
    print("ERROR: lamda-client not installed.", file=sys.stderr)
    print("  pip install ~/src/firerpa-binaries/lamda-client-py-10.0.tar.gz", file=sys.stderr)
    sys.exit(1)

SSHD_DOWN = "/data/data/com.termux/files/usr/var/service/sshd/down"
SSHD_BIN = "/data/data/com.termux/files/usr/bin/sshd"
BOOTLOOP_PID = "/data/data/com.termux/files/home/.stayturgid/run/bootloop.pid"
BOOTLAUNCH = (
    "setsid /data/data/com.termux/files/usr/bin/python3 "
    "/data/data/com.termux/files/home/.stayturgid/bin/start_adb.py "
    ">/dev/null 2>&1 < /dev/null &"
)
LOG_ROOT = os.path.expanduser("~/.config/stayturgid")
LOG_NAME = "firerpa-heal.log"


def _log(level: int, msg: str) -> None:
    log(LOG_NAME, level, msg, also_print=True)


def _exec_stdout(device: Device, cmd: str, timeout: int = 5) -> str:
    try:
        result = device.execute_script(cmd, timeout=timeout)
        if hasattr(result, 'stdout'):
            out = result.stdout
            if isinstance(out, bytes):
                return out.decode(errors='replace').strip()
            return (out or '').strip()
        out = str(result or '')
        return out
    except Exception:
        return ''


def is_sshd_alive(device: Device) -> bool:
    out = _exec_stdout(device, "ss -tlnp 2>/dev/null | grep ':8022 '")
    return ':8022' in out


def is_port_5555_alive(device: Device) -> bool:
    out = _exec_stdout(device, "ss -tlnp 2>/dev/null | grep ':5555 '")
    return ':5555' in out


def is_shizuku_alive(device: Device) -> bool:
    out = _exec_stdout(device, "pgrep -f '[s]hizuku_server' 2>/dev/null")
    return bool(out)


def is_bootloop_alive(device: Device) -> bool:
    out = _exec_stdout(device, "pgrep -f start_adb\\.py")
    return bool(out)


def remove_sshd_down(device: Device) -> str:
    out = _exec_stdout(device,
        f"run-as com.termux rm -f {SSHD_DOWN} 2>/dev/null && echo REMOVED || echo ABSENT")
    if "REMOVED" in out:
        _log(NOTICE, "removed sshd down file")
        return "repaired"
    return "up"


def restart_sshd(device: Device) -> str:
    _exec_stdout(device,
        "am start -n com.termux/.app.TermuxActivity 2>/dev/null")
    time.sleep(3)
    if is_sshd_alive(device):
        _log(NOTICE, "sshd alive after activity trigger")
        return "up"
    _log(WARNING, "sshd restart via TermuxActivity FAILED")
    return "FAILED"


def restart_bootloop(device: Device) -> str:
    _exec_stdout(device,
        "am start -n com.termux/.app.TermuxActivity 2>/dev/null")
    time.sleep(5)
    if is_bootloop_alive(device):
        _log(NOTICE, "boot loop alive after activity trigger")
        return "up"
    _log(WARNING, "boot loop restart via TermuxActivity FAILED")
    return "FAILED"


def restart_shizuku(device: Device) -> str:
    try:
        if is_shizuku_alive(device):
            return "up"
        device.execute_script("am broadcast -a moe.shizuku.privileged.api.HEADLESS_START", timeout=5)
        time.sleep(3)
        if is_shizuku_alive(device):
            _log(NOTICE, "Shizuku started via HEADLESS_START")
            return "repaired"
        if is_port_5555_alive(device):
            _log(WARNING, "Shizuku: port 5555 up but shizuku_server not found via pgrep")
            return "port_only"
        _log(ERR, "Shizuku restart FAILED")
        return "FAILED"
    except Exception as e:
        _log(ERR, "Shizuku restart error: %s" % e)
        return "FAILED"


def heal_device(host: str, port: int = 65000) -> dict[str, str]:
    results = {}
    try:
        d = Device(host, port=port, certificate=certificate_path())
    except Exception as e:
        err = str(e)[:80]
        _log(ERR, "Cannot connect to FIRERPA on %s:%s: %s" % (host, port, err))
        return {"firerpa": "unreachable", "error": err}

    server_info = d.server_info()
    _log(INFO, "%s: FIRERPA v%s uptime=%ss" % (host, server_info.version, server_info.uptime))

    sshd_alive = is_sshd_alive(d)
    port5555_alive = is_port_5555_alive(d)
    bootloop_alive = is_bootloop_alive(d)

    results["sshd"] = "up" if sshd_alive else "down"
    results["shizuku"] = "up" if port5555_alive else "down"
    results["bootloop"] = "up" if bootloop_alive else "down"

    if not sshd_alive:
        dn = remove_sshd_down(d)
        results["sshd_down_file"] = dn
        if not is_sshd_alive(d):
            r = restart_sshd(d)
            results["sshd_restart"] = r

    if not port5555_alive:
        r = restart_shizuku(d)
        results["shizuku_restart"] = r

    if not bootloop_alive:
        r = restart_bootloop(d)
        results["bootloop_restart"] = r

    results["sshd_final"] = "up" if is_sshd_alive(d) else "down"
    results["shizuku_final"] = "up" if is_port_5555_alive(d) else "down"

    status = " ".join(f"{k}={v}" for k, v in results.items())
    _log(INFO, "%s: %s" % (host, status))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair stayturgid via FIRERPA gRPC API.")
    parser.add_argument("--host", help="Target host alias (s24, p7a, hd8)")
    parser.add_argument("--all", action="store_true", help="Heal all fleet devices")
    parser.add_argument("--port", type=int, default=65000)
    args = parser.parse_args(argv)

    fleet = {
        "s24": "100.123.218.30",
        "p7a": "100.65.230.108",
        "hd8": "100.124.55.39",
    }

    if args.host:
        if args.host not in fleet:
            print(f"Unknown host: {args.host}. Known: {sorted(fleet)}", file=sys.stderr)
            return 1
        targets = {args.host: fleet[args.host]}
    elif args.all:
        targets = fleet
    else:
        print("Specify --host <alias> or --all", file=sys.stderr)
        return 1

    trim_log(os.path.join(LOG_ROOT, "logs", LOG_NAME), max_age_days=30, max_lines=2000)
    rc = 0
    for alias, ip in targets.items():
        try:
            results = heal_device(ip, args.port)
            if results.get("firerpa") == "unreachable":
                if alias == "hd8":
                    _log(INFO, "%s: FIRERPA not running (expected)" % alias)
                rc = 1
        except Exception as e:
            _log(ERR, "%s (%s): heal error: %s" % (alias, ip, e))
            rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
