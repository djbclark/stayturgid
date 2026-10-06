#!/usr/bin/env python3
"""Battery watch on the Mac hub: tell the operator before a device dies where it lies.

A phone lost in a messy room is findable (Find Hub, the locate sound) only while it has
battery. Called at the end of every fleet_health_monitor pass (launchd, ~15 min); also
runnable by hand. Reads each phone's ~/.stayturgid/state/batt_status.json (written by
stayturgid_battery_alarm.py) over ssh, and this Mac's own battery from pmset. Sends to
the Hermes Telegram Inbox, and to ntfy.sh when ~/.config/stayturgid/ntfy_topic exists.

Alerts, each once until that device next charges:
  - phone: under 2 h left at its measured drain, or at/below 15%
  - this Mac: under 30 min left (pmset's own estimate)
  - phone: not on a charger for 24 h
Plus a 21:00 roll call of everything unplugged and under 50%, or unreachable.

    control/lib/battery_watch.py            one pass over devices.conf
    control/lib/battery_watch.py --dry-run  print what would be sent; send nothing
    control/lib/battery_watch.py --test     send a test notice to every channel
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hermes_notify  # noqa: E402

ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
STATE_FILE = os.path.join(ROOT, "state", "battery-watch.json")
NTFY_TOPIC_FILE = os.path.join(ROOT, "ntfy_topic")
DEVICE_STATUS = "~/.stayturgid/state/batt_status.json"
PHONE_ETA_MIN, PHONE_PCT = 120, 15
MAC_ETA_MIN = 30
NO_CHARGE_H = 24
ROLLCALL_H, ROLLCALL_PCT = 21, 50
Status = dict[str, Any]
STALE_MIN = 45  # a status older than this is "last seen", not current


def device_status(host: str) -> Status | None:
    try:
        r = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                "LogLevel=ERROR",
                host,
                "cat " + DEVICE_STATUS,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def parse_pmset(out: str, now: float) -> Status | None:
    """pmset -g batt -> the same shape as a phone's batt_status.json."""
    m = re.search(r"(\d+)%; ([^;]+);\s*(?:(\d+):(\d+) remaining)?", out)
    if not m or "InternalBattery" not in out:
        return None
    on_charger = "AC Power" in out or m.group(2).strip() in ("charging", "charged", "finishing charge")
    eta = int(m.group(3)) * 60 + int(m.group(4)) if m.group(3) and not on_charger else None
    return {
        "ts": int(now),
        "pct": int(m.group(1)),
        "status": m.group(2).strip(),
        "on_charger": on_charger,
        "eta_min": eta,
    }


def mac_status(now: float) -> Status | None:
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_pmset(out, now)


def on_charger(st: Status) -> bool:
    if "on_charger" in st:
        return bool(st["on_charger"])
    return st.get("status") in ("CHARGING", "FULL") or st.get("plugged", "UNPLUGGED") not in ("UNPLUGGED", "")


def _hm(minutes: float) -> str:
    minutes = max(0, int(minutes))
    return "%dh%02dm" % divmod(minutes, 60) if minutes >= 60 else "%dm" % minutes


def evaluate(name: str, st: Status, mem: dict[str, Any], now: float, *, computer: bool = False) -> list[str]:
    """Messages due for one device; updates its slot in mem (the persisted state)."""
    if now - st.get("ts", 0) > STALE_MIN * 60:
        return []
    if on_charger(st):
        mem.pop(name, None)
        return []
    seen = mem.setdefault(name, {})
    msgs = []
    eta = st.get("eta_min")
    if eta is not None:
        eta -= (now - st["ts"]) / 60
    pct = st.get("pct", 100)
    if computer:
        low = eta is not None and eta <= MAC_ETA_MIN
    else:
        low = (eta is not None and eta <= PHONE_ETA_MIN) or pct <= PHONE_PCT
    if low and not seen.get("low"):
        seen["low"] = True
        left = ", ~%s left" % _hm(eta) if eta is not None else ""
        msgs.append("%s battery %d%%%s, not charging. Plug it in while it can still be found." % (name, pct, left))
    last = st.get("last_charged")
    if not computer and last and now - last > NO_CHARGE_H * 3600 and not seen.get("nocharge"):
        seen["nocharge"] = True
        msgs.append(
            "%s has not been on a charger for %dh (battery %d%%). Is it lost?" % (name, (now - last) // 3600, pct)
        )
    return msgs


def rollcall(statuses: dict[str, Status | None], mem: dict[str, Any], now: float) -> str | None:
    """21:00 roll call (once a day, skipped if the Mac slept through the 21:00 hour)."""
    t = datetime.datetime.fromtimestamp(now)
    today = t.strftime("%Y-%m-%d")
    if t.hour != ROLLCALL_H or mem.get("rollcall") == today:
        return None
    mem["rollcall"] = today
    lines = []
    for name, st in statuses.items():
        if st is None:
            lines.append("%s: unreachable" % name)
        elif now - st.get("ts", 0) > STALE_MIN * 60:
            seen = datetime.datetime.fromtimestamp(st["ts"]).strftime("%a %H:%M")
            lines.append("%s: %d%% when last seen %s" % (name, st.get("pct", 0), seen))
        elif not on_charger(st) and st.get("pct", 100) < ROLLCALL_PCT:
            lines.append("%s: %d%%, unplugged" % (name, st["pct"]))
    return ("Bedtime charger roll call: " + "; ".join(lines)) if lines else None


def ntfy(msg: str) -> None:
    try:
        with open(NTFY_TOPIC_FILE) as f:
            topic = f.read().strip()
    except OSError:
        return
    if not topic:
        return
    req = urllib.request.Request(
        "https://ntfy.sh/" + topic,
        data=msg.encode(),
        headers={"Title": "stayturgid battery", "Priority": "high", "Tags": "battery"},
    )
    try:
        urllib.request.urlopen(req, timeout=15).close()  # nosec B310 - fixed https://ntfy.sh URL
    except OSError:
        pass


def send(msg: str) -> None:
    hermes_notify.notify("battery", msg)
    ntfy(msg)


def _load() -> dict[str, Any]:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(mem: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(mem, f)


def run(hosts: list[str], now: float | None = None, *, dry: bool = False) -> list[str]:
    now = now if now is not None else datetime.datetime.now().timestamp()
    mem = _load()
    devices = mem.setdefault("devices", {})
    statuses: dict[str, Status | None] = {}
    msgs: list[str] = []
    for host in hosts:
        st = statuses[host] = device_status(host)
        if st is None:
            continue
        devices.setdefault("_last", {})[host] = st  # last known, for the roll call
        msgs += evaluate(host, st, devices, now)
    mac = mac_status(now)
    if mac:
        statuses["mac"] = mac
        msgs += evaluate("mac", mac, devices, now, computer=True)
    for host in hosts:  # unreachable: report the last status seen, if any
        if statuses[host] is None:
            statuses[host] = devices.get("_last", {}).get(host)
    call = rollcall(statuses, mem, now)
    if call:
        msgs.append(call)
    if not dry:
        for m in msgs:
            send(m)
        _save(mem)
    return msgs


def main(argv: list[str]) -> int:
    if argv[:1] == ["--test"]:
        send("test notice from control/lib/battery_watch.py")
        return 0
    import stayturgid_device as dev

    hosts = [row[0] for row in dev.iter_devices_conf()]
    for m in run(hosts, dry=argv[:1] == ["--dry-run"]):
        print(m)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
