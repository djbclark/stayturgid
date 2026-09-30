#!/usr/bin/env python3
"""Live LAN-IP discovery for fleet devices.

The site inventory's ``device_lan_ip`` is a static value, but the phones get
their LAN address from DHCP. By 2026-09-29 every one had drifted (s24
.54 -> .61, t2e .63 -> .62, p7a .60 -> .74), so ``ssh <dev>-lan`` and the
``devices.conf`` LAN column pointed at nothing.

This module discovers each device's current address and records it in
``~/.config/stayturgid/state/lan_ips.json``, then rewrites the two generated
artifacts that carry it in place. The control_node role prefers the same state
file over the inventory value when it re-renders them, so a deploy never
reintroduces a stale address. The fleet-health monitor calls ``refresh()`` on
every run (15 min); ``python3 control/lib/lan_ips.py`` runs it by hand.

Sources, most authoritative first:
1. adb over Tailscale: ``ip -4 -o addr show wlan0`` on the device.
2. ``tailscale status --json``: the peer's direct endpoint (``CurAddr``)
   when it is a private LAN address.
Devices neither source can see keep their last known entry.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.expanduser("~"), ".config", "stayturgid")
STATE_PATH = os.path.join(ROOT, "state", "lan_ips.json")
DEVICES_CONF = os.environ.get("STAYTURGID_DEVICES_CONF", os.path.join(ROOT, "devices.conf"))
SSH_FRAGMENT = os.path.join(os.path.expanduser("~"), ".ssh", "config.d", "stayturgid")

_TAILSCALE_CGNAT = ipaddress.IPv4Network("100.64.0.0/10")
_INET_RE = re.compile(r"\binet (\d+\.\d+\.\d+\.\d+)/")


def lan_ipv4(value: str) -> str | None:
    """Return ``value`` if it is a private (RFC 1918) IPv4 LAN address."""
    try:
        ip = ipaddress.IPv4Address(value.strip())
    except ValueError:
        return None
    if ip in _TAILSCALE_CGNAT or ip.is_loopback or ip.is_link_local or not ip.is_private:
        return None
    return str(ip)


def adb_wlan_ip(serial: str, adb: str = "adb", timeout: float = 8) -> str | None:
    try:
        r = subprocess.run(
            [adb, "-s", serial, "shell", "ip -4 -o addr show wlan0"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    m = _INET_RE.search(r.stdout or "")
    return lan_ipv4(m.group(1)) if m else None


def tailscale_lan_endpoints(tailscale: str = "tailscale", timeout: float = 10) -> dict[str, str]:
    """Map each peer's Tailscale IP to its direct LAN endpoint, when it has one."""
    try:
        r = subprocess.run([tailscale, "status", "--json"], capture_output=True, text=True, timeout=timeout)
        peers = json.loads(r.stdout or "{}").get("Peer") or {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    out = {}
    for peer in peers.values():
        host = (peer.get("CurAddr") or "").rsplit(":", 1)[0]
        ip = lan_ipv4(host) if host else None
        for ts_ip in peer.get("TailscaleIPs") or []:
            if ip:
                out[ts_ip] = ip
    return out


def discover(devices, adb: str = "adb") -> dict[str, tuple[str, str]]:
    """Return ``{name: (lan_ip, source)}`` for devices ``[(name, tailscale_ip), ...]``."""
    endpoints = None
    found = {}
    for name, ts_ip in devices:
        ip = adb_wlan_ip("%s:5555" % ts_ip, adb=adb) if ts_ip and ts_ip != "-" else None
        if ip:
            found[name] = (ip, "adb")
            continue
        if endpoints is None:
            endpoints = tailscale_lan_endpoints()
        ip = endpoints.get(ts_ip)
        if ip:
            found[name] = (ip, "tailscale")
    return found


def rewrite_ssh_config(text: str, ips: dict[str, str]) -> str:
    """Point each ``Host <name>-lan`` block's HostName at ``ips[name]``."""
    out = []
    new_ip = None
    for line in text.splitlines(keepends=True):
        m = re.match(r"^Host\s+(\S+)\s*$", line)
        if m:
            alias = m.group(1)
            new_ip = ips.get(alias[: -len("-lan")]) if alias.endswith("-lan") else None
        elif new_ip:
            ip = new_ip
            line = re.sub(r"^(\s*HostName\s+)\S+", lambda mm: mm.group(1) + ip, line)
        out.append(line)
    return "".join(out)


def rewrite_devices_conf(text: str, ips: dict[str, str]) -> str:
    """Set the lan_ip column (4th field) of each device line in ``ips``."""
    out = []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\S+)(\s+\S+\s+\S+\s+)(\S+)", line)
        if m and not line.startswith("#") and m.group(1) in ips:
            line = m.group(1) + m.group(2) + ips[m.group(1)] + line[m.end() :]
        out.append(line)
    return "".join(out)


def _atomic_rewrite(path: str, transform) -> bool:
    try:
        with open(path) as f:
            old = f.read()
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        return False
    new = transform(old)
    if new == old:
        return False
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".lan_ips.")
    with os.fdopen(fd, "w") as f:
        f.write(new)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    return True


def load_state(path: str = STATE_PATH) -> dict[str, dict[str, str]]:
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def refresh(
    devices,
    state_path: str = STATE_PATH,
    ssh_path: str = SSH_FRAGMENT,
    conf_path: str = DEVICES_CONF,
    adb: str = "adb",
) -> dict[str, tuple[str | None, str]]:
    """Discover, persist, and apply; return ``{name: (old_ip, new_ip)}`` for changes."""
    state = load_state(state_path)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    changes = {}
    for name, (ip, source) in discover(devices, adb=adb).items():
        old = (state.get(name) or {}).get("ip")
        if old != ip:
            changes[name] = (old, ip)
        state[name] = {"ip": ip, "source": source, "seen": now}
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(state_path), prefix=".lan_ips.")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, state_path)
    ips = {name: entry["ip"] for name, entry in state.items() if entry.get("ip")}
    _atomic_rewrite(ssh_path, lambda t: rewrite_ssh_config(t, ips))
    _atomic_rewrite(conf_path, lambda t: rewrite_devices_conf(t, ips))
    return changes


def _devices_from_conf(conf_path: str):
    try:
        with open(conf_path) as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and not line.startswith("#"):
                    yield parts[0], parts[2]
    except OSError:
        return


if __name__ == "__main__":
    for name, (old, new) in refresh(list(_devices_from_conf(DEVICES_CONF))).items():
        print("%s: %s -> %s" % (name, old or "-", new))
    sys.exit(0)
