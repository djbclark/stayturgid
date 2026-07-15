#!/usr/bin/env python3
"""Typed interface to the stayturgid Ansible site inventory.

Single source of truth for all non-secret, declared site identity.
Replaces ad-hoc parsing of ``devices.conf`` in individual scripts.

Usage::

    from site_identity import load_site_identity

    site = load_site_identity()
    for alias, device in site.devices.items():
        print(alias, device.ansible_host)

The module calls ``ansible-inventory --list`` to export the inventory as JSON,
validates the schema, and caches the result to
``~/.config/stayturgid/.identity_cache.json``.  The cache is invalidated
whenever ``ansible/inventory/hosts.yml`` is newer than the cache file.

Uses only the Python standard library: ``dataclasses``, ``ipaddress``,
``json``, ``pathlib``, ``re``, ``subprocess``.
"""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Cache location
# ---------------------------------------------------------------------------

_CACHE_DIR = Path.home() / ".config" / "stayturgid"
_CACHE_FILE = _CACHE_DIR / ".identity_cache.json"


# ---------------------------------------------------------------------------
# Public dataclasses (frozen / immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Device:
    """Declared identity for a single fleet device."""

    alias: str
    ansible_host: str
    device_usb_serial: str
    device_lan_ip: str
    device_label: str
    ansible_port: int
    ansible_user: str
    stayturgid_automation_mode: str


@dataclass(frozen=True)
class ControlNode:
    """Mac control-node network identity (from ``stayturgid_mac_peer``)."""

    ssh_user: str
    lan_ip: str
    tailscale_ip: str


@dataclass(frozen=True)
class Site:
    """Complete declared site identity parsed from the Ansible inventory."""

    telegram_allowed_users: tuple[str, ...]
    telegram_home_channel: str
    devices: dict[str, Device]
    control_node: ControlNode

    def device_order(self) -> list[str]:
        """Return device aliases in deterministic inventory order."""
        return sorted(self.devices.keys())


# ---------------------------------------------------------------------------
# Repository-root discovery
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Walk up from this file until ``device/termux/`` and ``control/lib/`` exist."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "device" / "termux").is_dir() and (p / "control" / "lib").is_dir():
            return p
        p = p.parent
    raise RuntimeError(f"Could not determine stayturgid repository root (walked up from {__file__})")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _valid_ip(address: str) -> bool:
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


def _valid_hostname(name: str) -> bool:
    """Accept DNS labels and MagicDNS names (non-IP ansible_host values)."""
    if not name or len(name) > 255:
        return False
    name = name.rstrip(".")
    label = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
    return all(label.match(part) for part in name.split("."))


def _require(host: str, key: str, hostvars: dict) -> object:
    value = hostvars.get(key)
    if not value:
        raise ValueError(f"Host '{host}' missing required variable: '{key}'")
    return value


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------


def _parse_inventory(data: dict) -> Site:
    """Parse and validate ``ansible-inventory --list`` JSON into a ``Site``."""
    stayturgid_group = data.get("stayturgid", {})
    host_list: list[str] = stayturgid_group.get("hosts", [])
    if not host_list:
        raise ValueError("Inventory is missing a 'stayturgid' group or it has no hosts")

    hostvars: dict[str, dict] = data.get("_meta", {}).get("hostvars", {})

    devices: dict[str, Device] = {}
    serials_seen: set[str] = set()
    mgmt_ips_seen: set[str] = set()
    lan_ips_seen: set[str] = set()

    for host in host_list:
        if host not in hostvars:
            raise ValueError(f"Host '{host}' is in 'stayturgid' group but missing from _meta.hostvars")
        hvars = hostvars[host]

        # Alias format
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", host):
            raise ValueError(
                f"Host alias '{host}' must start with a lowercase letter and contain "
                "only lowercase letters, digits, hyphens, or underscores"
            )

        # ansible_host — IP or DNS name
        ansible_host = str(_require(host, "ansible_host", hvars))
        if not (_valid_ip(ansible_host) or _valid_hostname(ansible_host)):
            raise ValueError(f"Host '{host}' has invalid 'ansible_host' value: '{ansible_host}'")
        if _valid_ip(ansible_host):
            if ansible_host in mgmt_ips_seen:
                raise ValueError(f"Duplicate ansible_host '{ansible_host}' on host '{host}'")
            mgmt_ips_seen.add(ansible_host)

        # device_usb_serial (optional — '-' means no USB route)
        usb_serial: str = hvars.get("device_usb_serial", "-") or "-"
        if usb_serial != "-":
            if usb_serial in serials_seen:
                raise ValueError(f"Duplicate device_usb_serial '{usb_serial}' on host '{host}'")
            serials_seen.add(usb_serial)

        # device_lan_ip (optional — '-' means unknown)
        lan_ip: str = hvars.get("device_lan_ip", "-") or "-"
        if lan_ip != "-":
            if not _valid_ip(lan_ip):
                raise ValueError(f"Host '{host}' has invalid 'device_lan_ip' value: '{lan_ip}'")
            if lan_ip in lan_ips_seen:
                raise ValueError(f"Duplicate device_lan_ip '{lan_ip}' on host '{host}'")
            lan_ips_seen.add(lan_ip)

        device_label = str(_require(host, "device_label", hvars))

        try:
            port = int(hvars.get("ansible_port", 8022))
        except (TypeError, ValueError):
            raise ValueError(f"Host '{host}' has non-integer 'ansible_port': '{hvars.get('ansible_port')}'")

        ansible_user = str(_require(host, "ansible_user", hvars))
        auto_mode: str = hvars.get("stayturgid_automation_mode", "none") or "none"

        devices[host] = Device(
            alias=host,
            ansible_host=ansible_host,
            device_usb_serial=usb_serial,
            device_lan_ip=lan_ip,
            device_label=device_label,
            ansible_port=port,
            ansible_user=ansible_user,
            stayturgid_automation_mode=auto_mode,
        )

    # Control node — derived from first host's stayturgid_mac_peer / stayturgid_control_*
    first_hvars = hostvars[host_list[0]]
    mac_peer: dict = first_hvars.get("stayturgid_mac_peer") or {}

    ssh_user: str = first_hvars.get("stayturgid_control_ssh_user") or mac_peer.get("user", "")
    lan_ip_ctrl: str = mac_peer.get("lan", "")
    tailscale_ip_ctrl: str = mac_peer.get("tailscale", "")

    # Resolve Jinja2 template references at runtime (ansible-inventory expands them)
    for key, value in [
        ("ssh_user", ssh_user),
        ("lan_ip", lan_ip_ctrl),
        ("tailscale_ip", tailscale_ip_ctrl),
    ]:
        if not value:
            raise ValueError(
                f"Control node missing required identity variable: '{key}'. "
                "Check 'stayturgid_mac_peer' in group_vars/stayturgid.yml."
            )

    control_node = ControlNode(
        ssh_user=ssh_user,
        lan_ip=lan_ip_ctrl,
        tailscale_ip=tailscale_ip_ctrl,
    )

    # Site-level variables (telegram, etc.)
    first_vars = hostvars[host_list[0]]
    raw_users = str(first_vars.get("stayturgid_hermes_telegram_allowed_users", ""))
    allowed_users = tuple(u.strip() for u in raw_users.split(",") if u.strip())
    home_channel = str(first_vars.get("stayturgid_hermes_telegram_home_channel", ""))

    return Site(
        telegram_allowed_users=allowed_users,
        telegram_home_channel=home_channel,
        devices=devices,
        control_node=control_node,
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _write_cache(site: Site) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "telegram_allowed_users": list(site.telegram_allowed_users),
            "telegram_home_channel": site.telegram_home_channel,
            "devices": {alias: asdict(dev) for alias, dev in site.devices.items()},
            "control_node": asdict(site.control_node),
        }
        _CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Cache write failures must never abort the caller.
        pass


def _read_cache() -> Site | None:
    try:
        payload = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        devices = {alias: Device(**dev) for alias, dev in payload["devices"].items()}
        control_node = ControlNode(**payload["control_node"])
        return Site(
            telegram_allowed_users=tuple(payload["telegram_allowed_users"]),
            telegram_home_channel=payload["telegram_home_channel"],
            devices=devices,
            control_node=control_node,
        )
    except Exception:
        return None


def _cache_fresh(hosts_yml: Path) -> bool:
    """Return True if the cache is newer than the inventory source file."""
    if not _CACHE_FILE.is_file():
        return False
    return _CACHE_FILE.stat().st_mtime > hosts_yml.stat().st_mtime


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_site_identity(
    force_refresh: bool = False,
    inventory_path: Path | None = None,
) -> Site:
    """Return the current site identity from the Ansible inventory.

    Args:
        force_refresh: Skip the cache and re-run ``ansible-inventory``.
        inventory_path: Override the default inventory path (for testing).

    Returns:
        A validated, immutable :class:`Site` dataclass.

    Raises:
        FileNotFoundError: If the inventory file does not exist.
        RuntimeError: If ``ansible-inventory`` fails or returns invalid JSON.
        ValueError: If the inventory fails schema validation.
    """
    if inventory_path is None:
        root = _find_repo_root()
        inventory_path = root / "ansible" / "inventory" / "hosts.yml"

    if not inventory_path.is_file():
        raise FileNotFoundError(f"Authoritative inventory not found at: {inventory_path}")

    # Serve from cache when fresh
    if not force_refresh and _cache_fresh(inventory_path):
        cached = _read_cache()
        if cached is not None:
            return cached

    # Export inventory to JSON via ansible-inventory
    result = subprocess.run(
        ["ansible-inventory", "-i", str(inventory_path), "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ansible-inventory failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")

    try:
        inventory_data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Could not parse ansible-inventory JSON output: {exc}\nRaw output: {result.stdout[:500]}"
        ) from exc

    site = _parse_inventory(inventory_data)
    _write_cache(site)
    return site
