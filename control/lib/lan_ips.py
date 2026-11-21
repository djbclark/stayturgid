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
Devices neither source can see keep their last known entry for ``STALE_AFTER``
(7 days); after that the entry is dropped and the inventory's ``device_lan_ip``
applies again. A device with a live address but no ``<name>-lan`` SSH block
gets one cloned from its ``Host <name>`` block. Fixing the address itself is a
router DHCP reservation (MAC-keyed), not code.

An address is only ever trusted for one device. When another device's live
entry holds an address (DHCP handed it over), the older claim is dropped: the
state entry, the ``<name>-lan`` ssh block and the ``devices.conf`` column of
the device that lost it (a stale hd8 address now held by m11, 2026-11-21).
Every ``<name>-lan`` block also pins the host key under ``HostKeyAlias <name>``
with ``StrictHostKeyChecking yes``; ``pin_known_hosts`` copies the keys the
Tailscale entry already trusts onto that alias, so a reassigned LAN address
fails the key check instead of trusting whatever answers.
"""

from __future__ import annotations

import base64
import datetime
import fnmatch
import hashlib
import hmac
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
KNOWN_HOSTS = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")

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


def _host_blocks(text: str) -> list[tuple[list[str], list[str]]]:
    """Split an ssh config fragment into ``(patterns, body lines)`` per ``Host`` line."""
    blocks: list[tuple[list[str], list[str]]] = []
    for line in text.splitlines():
        m = re.match(r"^Host\s+(.+?)\s*$", line)
        if m:
            blocks.append((m.group(1).split(), []))
        elif blocks and line[:1] in (" ", "\t"):
            blocks[-1][1].append(line)
    return blocks


def held_by_others(ips: dict[str, str], name: str) -> set[str]:
    """Addresses that a device other than ``name`` currently holds."""
    return {ip for other, ip in ips.items() if other != name}


def _strict_lines(body: list[str]) -> list[str]:
    """Body lines with one ``StrictHostKeyChecking yes`` (replacing any other value)."""
    kept = [b for b in body if not re.match(r"^\s*StrictHostKeyChecking(\s|=)", b, re.I)]
    return [*kept, "  StrictHostKeyChecking yes"]


def rewrite_ssh_config(text: str, ips: dict[str, str]) -> str:
    """Point each ``Host <name>-lan`` block's HostName at ``ips[name]``.

    A device with a live address but no ``<name>-lan`` block (added to the
    fleet, or its inventory had no LAN address at deploy time) gets one,
    cloned from its ``Host <name>`` block with ``HostKeyAlias <name>`` so the
    CA host certificate still validates whatever the current IP is. Every
    ``-lan`` block is held to ``StrictHostKeyChecking yes`` (a changed or
    unknown key fails instead of being trusted). A block for a device with no
    live address is removed when its HostName is an address another device's
    live entry holds.
    """
    out: list[str] = []
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^Host\s+(\S+)\s*$", line)
        if not (m and m.group(1).endswith("-lan")):
            out.append(line)
            i += 1
            continue
        name = m.group(1)[: -len("-lan")]
        j = i + 1
        while j < len(lines) and (lines[j][:1] in (" ", "\t") or not lines[j].strip()):
            j += 1
        block = lines[i + 1 : j]
        trailing: list[str] = []
        while block and not block[-1].strip():
            trailing.insert(0, block.pop())
        ip = ips.get(name)
        if ip is None:
            current = next(
                (
                    re.match(r"^\s*HostName(?:\s+|\s*=\s*)(\S+)", b, re.I)
                    for b in block
                    if re.match(r"^\s*HostName(\s|=)", b, re.I)
                ),
                None,
            )
            if current and current.group(1) in held_by_others(ips, name):
                i = j
                continue
        body = block
        if ip:
            new_ip = ip
            body = [
                re.sub(r"^(\s*HostName(?:\s+|\s*=\s*))\S+", lambda mm: mm.group(1) + new_ip, b, flags=re.I)
                for b in block
            ]
        has_alias = any(re.match(r"^\s*HostKeyAlias(\s|=)", b, re.I) for b in body)
        if not has_alias:
            body = [*body, "  HostKeyAlias %s" % name]
        out.append(line)
        out.extend(b if b.endswith("\n") else b + "\n" for b in _strict_lines([b.rstrip("\n") for b in body]))
        out.extend(trailing)
        i = j
    result = "".join(out)
    blocks = _host_blocks(result)
    have = {p for patterns, _ in blocks for p in patterns}
    extra = []
    for name, ip in sorted(ips.items()):
        if "%s-lan" % name in have:
            continue
        source = next((body for patterns, body in blocks if name in patterns), None)
        if source is None:
            continue
        keep = [b for b in source if not re.match(r"^\s*(HostName|HostKeyAlias)(\s|=)", b, re.I)]
        body = ["  HostName %s" % ip, "  HostKeyAlias %s" % name, *keep]
        extra.append("\n".join(["Host %s-lan" % name, *_strict_lines(body)]) + "\n")
    if extra:
        result += ("" if result.endswith("\n") or not result else "\n") + "".join(extra)
    return result


def rewrite_devices_conf(text: str, ips: dict[str, str]) -> str:
    """Set the lan_ip column (4th field) of each device line in ``ips``.

    A device with no live address whose column holds an address another
    device's live entry holds gets ``-`` (unknown) instead.
    """
    out = []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\S+)(\s+\S+\s+\S+\s+)(\S+)", line)
        if m and not line.startswith("#"):
            name = m.group(1)
            if name in ips:
                line = name + m.group(2) + ips[name] + line[m.end() :]
            elif m.group(3) in held_by_others(ips, name):
                line = name + m.group(2) + "-" + line[m.end() :]
        out.append(line)
    return "".join(out)


_KEY_LINE = re.compile(r"^\s*(?P<hosts>\S+)\s+(?P<type>(?:ssh|ecdsa|sk)-\S+)\s+(?P<key>\S+)")


def _names_host(hosts: str, name: str) -> bool:
    """Whether a known_hosts host field names ``name`` (plain list entry or ``|1|`` hash)."""
    if hosts.startswith("|1|"):
        try:
            _, _, salt, digest = hosts.split("|")
            mac = hmac.new(base64.b64decode(salt), name.encode(), hashlib.sha1).digest()
            return hmac.compare_digest(mac, base64.b64decode(digest))
        except (ValueError, TypeError):
            return False
    wanted = name.lower()
    entries = [h.lower() for h in hosts.split(",")]
    if any(h.startswith("!") and fnmatch.fnmatchcase(wanted, h[1:]) for h in entries):
        return False
    return any(not h.startswith("!") and fnmatch.fnmatchcase(wanted, h) for h in entries)


def _without_name(line: str, name: str) -> str | None:
    """``line`` minus ``name``: None when nothing else is left on the line."""
    km = _KEY_LINE.match(line)
    if not km or "|" in km.group("hosts")[:1]:
        return None
    rest = [h for h in km.group("hosts").split(",") if not _names_host(h, name)]
    return line[: km.start("hosts")] + ",".join(rest) + line[km.end("hosts") :] if rest else None


def pin_known_hosts(ssh_text: str, known_hosts_path: str | None = None, report=None) -> list[str]:
    """Make each ``<name>-lan`` HostKeyAlias trust exactly the keys trusted for the device.

    The ``Host <name> <ip>`` block says which ``[ip]:port`` entry in
    ``known_hosts`` the Tailscale deploy scanned and trusted. The ``<name>``
    alias (what ``HostKeyAlias <name>`` looks up) is made to hold those keys and
    nothing else: every other line naming the alias is removed whatever its key
    type and also when hashed (an address DHCP handed to another phone left
    that phone's keys there under the old accept-new setting), then the trusted
    keys are appended. With no trusted entry to copy (missing or hashed) the
    alias entries are removed too, so the strict check fails closed; the CA host
    certificate (principal ``<name>``) still validates. Marker lines
    (``@cert-authority``, ``@revoked``) are never touched. Returns the aliases
    changed.
    """
    changed: set[str] = set()

    def transform(old: str) -> str:
        lines = old.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        plain = [(line, _KEY_LINE.match(line)) for line in lines]
        trusted: dict[str, dict[str, str]] = {}
        for patterns, body in _host_blocks(ssh_text):
            if len(patterns) != 2 or patterns[0].endswith(("-lan", "-firerpa")):
                continue
            name, ip = patterns
            port = next((m.group(1) for b in body if (m := re.match(r"^\s*Port(?:\s+|\s*=\s*)(\d+)", b, re.I))), "22")
            source = "[%s]:%s" % (ip, port) if port != "22" else ip
            keys = trusted.setdefault(name, {})
            for _line, km in plain:
                if km and source in km.group("hosts").split(","):
                    keys.setdefault(km.group("type"), km.group("key"))
        for name, keys in sorted(trusted.items()):
            kept: list[str] = []
            have: set[tuple[str, str]] = set()
            for line, km in [(ln, _KEY_LINE.match(ln)) for ln in lines]:
                if not km or not _names_host(km.group("hosts"), name):
                    kept.append(line)
                    continue
                if keys.get(km.group("type")) == km.group("key") and km.group("hosts") == name:
                    kept.append(line)  # already the trusted key under the bare alias
                    have.add((km.group("type"), km.group("key")))
                    continue
                rest = _without_name(line, name)
                if rest is not None:
                    kept.append(rest)
                changed.add(name)
                if report:
                    report(
                        "host key under alias %s (%s) removed: not the Tailscale-trusted key" % (name, km.group("type"))
                    )
            for ktype, key in sorted(keys.items()):
                if (ktype, key) not in have:
                    kept.append("%s %s %s" % (name, ktype, key))
                    changed.add(name)
                    if report:
                        report("host key pinned for %s (%s)" % (name, ktype))
            lines = kept
        return "\n".join(lines) + "\n" if changed else old

    _atomic_rewrite(known_hosts_path or KNOWN_HOSTS, transform)
    return sorted(changed)


def _atomic_rewrite(path: str, transform) -> bool:
    path = os.path.realpath(path)  # keep a symlinked file (dotfiles) a symlink
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


# An offline phone's last address is kept this long, then dropped so the
# inventory value (the deploy-time fallback) wins again instead of a
# months-old DHCP lease overriding it forever.
STALE_AFTER = datetime.timedelta(days=7)


def prune_stale(state: dict[str, dict[str, str]], now: datetime.datetime) -> dict[str, str]:
    """Remove entries not seen within ``STALE_AFTER`` (or with no readable ``seen``); return ``{name: old_ip}``."""
    dropped = {}
    for name, entry in list(state.items()):
        try:
            seen = datetime.datetime.fromisoformat(entry["seen"])
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=datetime.timezone.utc)
            stale = now - seen > STALE_AFTER
        except (KeyError, TypeError, ValueError):
            stale = True
        if stale:
            dropped[name] = (entry or {}).get("ip", "") if isinstance(entry, dict) else ""
            del state[name]
    return dropped


def _seen(entry) -> datetime.datetime:
    try:
        seen = datetime.datetime.fromisoformat(entry["seen"])
    except (KeyError, TypeError, ValueError):
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    return seen if seen.tzinfo else seen.replace(tzinfo=datetime.timezone.utc)


def dedupe_state(state: dict[str, dict[str, str]]) -> dict[str, str]:
    """One address, one device: drop the older claim to a shared address; return ``{name: old_ip}``.

    The device seen most recently keeps it (adb reading beats the Tailscale
    endpoint on a tie, then the name decides). A phone that lost its address to
    another device falls back to the inventory value only if that is not held
    by yet another live entry (see ``rewrite_ssh_config``).
    """
    by_ip: dict[str, list[str]] = {}
    for name, entry in state.items():
        ip = entry.get("ip") if isinstance(entry, dict) else None
        if ip:
            by_ip.setdefault(ip, []).append(name)
    dropped = {}
    for ip, names in by_ip.items():
        if len(names) < 2:
            continue
        names.sort(key=lambda n: (_seen(state[n]), state[n].get("source") == "adb", n))
        for loser in names[:-1]:
            dropped[loser] = ip
            del state[loser]
    return dropped


def refresh(
    devices,
    state_path: str = STATE_PATH,
    ssh_path: str = SSH_FRAGMENT,
    conf_path: str = DEVICES_CONF,
    adb: str = "adb",
    known_hosts_path: str | None = None,
    report=None,
) -> dict[str, tuple[str | None, str | None]]:
    """Discover, persist, and apply; return ``{name: (old_ip, new_ip)}`` for changes."""
    state = load_state(state_path)
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.isoformat(timespec="seconds")
    changes: dict[str, tuple[str | None, str | None]] = {}
    for name, (ip, source) in discover(devices, adb=adb).items():
        old = (state.get(name) or {}).get("ip")
        if old != ip:
            changes[name] = (old, ip)
        state[name] = {"ip": ip, "source": source, "seen": now}
    for dropper in (prune_stale, lambda st, _now: dedupe_state(st)):
        for name, old_ip in dropper(state, now_dt).items():
            if old_ip:
                changes[name] = (old_ip, None)
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(state_path), prefix=".lan_ips.")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, state_path)
    ips = {name: entry["ip"] for name, entry in state.items() if entry.get("ip")}
    _atomic_rewrite(ssh_path, lambda t: rewrite_ssh_config(t, ips))
    _atomic_rewrite(conf_path, lambda t: rewrite_devices_conf(t, ips))
    try:
        with open(ssh_path) as f:
            pin_known_hosts(f.read(), known_hosts_path or KNOWN_HOSTS, report=report)
    except OSError:
        pass
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


def devices_from_env(value: str) -> list[tuple[str, str]]:
    """Parse ``STAYTURGID_LAN_DEVICES`` (``name=tailscale_ip`` pairs, whitespace separated)."""
    pairs = []
    for item in value.split():
        name, sep, ts_ip = item.partition("=")
        if sep and name and ts_ip:
            pairs.append((name, ts_ip))
    return pairs


if __name__ == "__main__":
    # The role passes the inventory's devices in STAYTURGID_LAN_DEVICES so the
    # first deploy (no devices.conf yet) and newly added phones are discovered
    # too; by hand or from fleet-health the rendered devices.conf is the source.
    devs = devices_from_env(os.environ.get("STAYTURGID_LAN_DEVICES", "")) or list(_devices_from_conf(DEVICES_CONF))
    for name, (old, new) in refresh(devs).items():
        print("%s: %s -> %s" % (name, old or "-", new or "-"))
    sys.exit(0)
