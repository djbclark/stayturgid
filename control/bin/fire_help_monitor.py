#!/usr/bin/env python3
"""Mac launchd: help Fire OS hosts when Shizuku/Handsets look down.

Every 5 minutes: for each host with STAYTURGID_NO_LOCAL_ADB semantics (hd8),
if ADB reachable and shizuku_server / Handsets port look down, run
`control/bin/fire_peer_help.py` via Mac adb (fleet adbkey).

Logs: ~/.config/stayturgid/logs/fire-help.log
Disable: STAYTURGID_SKIP_FIRE_HELP=1
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))


import fleet_health as fh  # noqa: E402
import fire_peer_help as fph  # noqa: E402

ROOT = Path.home() / ".config" / "stayturgid"
CONF = Path(os.environ.get("STAYTURGID_DEVICES_CONF", ROOT / "devices.conf"))
# Hosts that need peer/Mac help (no Termux→5555). Override via env CSV.
FIRE_HOSTS = [
    h.strip()
    for h in os.environ.get("STAYTURGID_FIRE_HELP_HOSTS", "hd8").split(",")
    if h.strip()
]
LOG = ROOT / "logs" / "fire-help.log"
STATE_DIR = ROOT / "state" / "fire-help"
SKIP = os.environ.get("STAYTURGID_SKIP_FIRE_HELP") == "1"
HANDSETS_PORT = int(os.environ.get("STAYTURGID_HANDSETS_PORT_HD8", "9008"))
CONSECUTIVE_LIMIT = 2


def ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write("%s  %s\n" % (ts(), msg))
    except OSError:
        pass


def read_devices():
    if not CONF.is_file():
        return
    try:
        from stayturgid_device import iter_monitor_hosts

        yield from iter_monitor_hosts(str(CONF))
        return
    except Exception:  # noqa: BLE001
        pass
    for line in CONF.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3:
            name, _usb, ts_ip = parts[0], parts[1], parts[2]
            lan = parts[3] if len(parts) > 3 else "-"
            yield name, ts_ip, lan


def read_state(host: str) -> int:
    p = STATE_DIR / host
    try:
        return int(p.read_text().strip() or "0")
    except (OSError, ValueError):
        return 0


def write_state(host: str, n: int) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / host).write_text(str(n))
    except OSError:
        pass


def adb_targets(ts_ip: str, lan_ip: str) -> list[str]:
    out = []
    if lan_ip and lan_ip != "-":
        out.append("%s:5555" % lan_ip)
    if ts_ip and ts_ip != "-":
        out.append("%s:5555" % ts_ip)
    return out


def needs_help(target: str) -> tuple[bool, bool]:
    """Return (need_shizuku, need_handsets)."""
    try:
        fph._ensure_connected(target)
    except SystemExit as e:
        log("%s connect fail: %s" % (target, e))
        return False, False
    sh = fph._shell(target, "pgrep -f shizuku_server >/dev/null && echo up", timeout=10)
    need_sh = "up" not in (sh.stdout or "")
    hs = fph._shell(
        target,
        "toybox nc -z 127.0.0.1 %d >/dev/null 2>&1 && echo up || echo down"
        % HANDSETS_PORT,
        timeout=10,
    )
    need_hs = "up" not in (hs.stdout or "")
    return need_sh, need_hs


def help_host(name: str, ts_ip: str, lan_ip: str) -> None:
    path = fh.resolve_path(name, ts_ip, lan_ip)
    if not path:
        log("%s unreachable — skip" % name)
        return
    # Prefer adb path for Mac help
    targets = adb_targets(ts_ip, lan_ip)
    if not targets:
        log("%s no adb targets" % name)
        return
    target = None
    for t in targets:
        try:
            fph._ensure_connected(t)
            target = t
            break
        except SystemExit:
            continue
    if not target:
        log("%s adb connect failed all targets" % name)
        fails = read_state(name) + 1
        write_state(name, fails)
        return

    need_sh, need_hs = needs_help(target)
    if not need_sh and not need_hs:
        if read_state(name) >= CONSECUTIVE_LIMIT:
            log("%s RECOVERED (shizuku+handsets up)" % name)
        write_state(name, 0)
        log("%s ok via %s" % (name, target))
        return

    actions = []
    if need_sh:
        rc = fph.cmd_shizuku_start(target)
        actions.append("shizuku=%s" % ("ok" if rc == 0 else "fail"))
    if need_hs:
        rc = fph.cmd_handsets_start(target, HANDSETS_PORT)
        actions.append("handsets=%s" % ("ok" if rc == 0 else "fail"))
    log("%s help via %s: %s" % (name, target, " ".join(actions)))
    # Re-check
    need_sh2, need_hs2 = needs_help(target)
    if need_sh2 or need_hs2:
        write_state(name, read_state(name) + 1)
    else:
        write_state(name, 0)


def main() -> int:
    if SKIP:
        return 0
    if not CONF.is_file():
        return 0
    for name, ts_ip, lan_ip in read_devices():
        if name not in FIRE_HOSTS:
            continue
        try:
            help_host(name, ts_ip, lan_ip)
        except Exception as e:  # noqa: BLE001
            log("%s error: %s" % (name, e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
