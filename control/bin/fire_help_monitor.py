#!/usr/bin/env python3
"""Mac launchd: help Fire OS hosts when Shizuku/Handsets look down.

Every 5 minutes: for each host with STAYTURGID_NO_LOCAL_ADB semantics (hd8),
if ADB reachable and shizuku_server / Handsets port look down, run
`control/bin/fire_peer_help.py` via Mac adb (fleet adbkey).

Also re-asserts **wireless debugging** (``adb_wifi_enabled=1``) whenever Mac
has a shell — Fire on-device repair cannot do this (no loopback adb), so the
toggle drifts off until Mac/USB help runs.

Logs: ~/.config/stayturgid/logs/fire-help.log
Disable: STAYTURGID_SKIP_FIRE_HELP=1
"""
from __future__ import annotations

import datetime
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))


import fire_peer_help as fph  # noqa: E402

try:
    import stayturgid_device as dev  # noqa: E402
except Exception:  # noqa: BLE001
    dev = None  # type: ignore

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
HANDSETS_PORT = int(os.environ.get("STAYTURGID_HANDSETS_PORT_HD8", "9012"))
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
        tmp = STATE_DIR / (host + ".tmp")
        tmp.write_text(str(n))
        tmp.rename(STATE_DIR / host)
    except OSError:
        pass


def adb_targets(name: str, ts_ip: str, lan_ip: str) -> list[str]:
    """Ordered adb endpoints: shared resolve_adb first (USB / mDNS wireless-debug),
    then classic LAN/TS :5555. Fire often only has wireless-debugging (random port).
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> None:
        t = (t or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        out.append(t)

    if dev is not None:
        try:
            add(dev.resolve_adb(name))
        except Exception:  # noqa: BLE001
            pass
    if lan_ip and lan_ip != "-":
        add("%s:5555" % lan_ip)
    if ts_ip and ts_ip != "-":
        add("%s:5555" % ts_ip)
    return out


def ensure_wireless_debugging(target: str) -> str:
    """Keep Developer-options wireless debugging on (Mac shell only; Fire self-heal skip)."""
    try:
        fph._ensure_connected(target)
    except SystemExit as e:
        return "skip:%s" % e
    cur = fph._shell(target, "settings get global adb_wifi_enabled", timeout=10)
    val = (cur.stdout or "").strip().replace("\r", "")
    if val in ("1", "true"):
        return "up"
    fph._shell(target, "settings put global adb_wifi_enabled 1", timeout=10)
    time.sleep(1)
    again = fph._shell(target, "settings get global adb_wifi_enabled", timeout=10)
    val2 = (again.stdout or "").strip().replace("\r", "")
    if val2 in ("1", "true"):
        return "repaired"
    return "FAILED:%s" % val2


def needs_help(target: str) -> tuple[bool, bool]:
    """Return (need_shizuku, need_handsets)."""
    try:
        fph._ensure_connected(target)
    except SystemExit as e:
        log("%s connect fail: %s" % (target, e))
        return False, False
    sh = fph._shell(target, "pgrep -f '[s]hizuku_server' >/dev/null && echo up", timeout=10)
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
    # Soft-health path may be SSH-only; still try full adb candidate list for help.
    targets = adb_targets(name, ts_ip, lan_ip)
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
        log("%s adb connect failed all targets (%s)" % (name, ",".join(targets[:4])))
        fails = read_state(name) + 1
        write_state(name, fails)
        return

    wifi = ensure_wireless_debugging(target)
    if wifi not in ("up", "repaired"):
        log("%s wireless-debug %s via %s" % (name, wifi, target))
    elif wifi == "repaired":
        log("%s wireless-debug re-enabled via %s" % (name, target))

    need_sh, need_hs = needs_help(target)
    if not need_sh and not need_hs:
        if read_state(name) >= CONSECUTIVE_LIMIT:
            log("%s RECOVERED (shizuku+handsets up)" % name)
        write_state(name, 0)
        log("%s ok via %s wifi=%s" % (name, target, wifi))
        return

    actions = ["wifi=%s" % wifi]
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
