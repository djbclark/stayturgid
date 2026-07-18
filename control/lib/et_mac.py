#!/usr/bin/env python3
"""Phone → Mac Eternal Terminal: keys, SSH config templates, health helpers.

See docs/modules/control.md (Phone → Mac Eternal Terminal).

Marked Mac authorized_keys block::

  # BEGIN STAYTURGID-ET-MAC
  ssh-ed25519 AAAA… oneui-device-fleet
  …
  # END STAYTURGID-ET-MAC

Never touches ForceCommand / peer-help lines outside the block.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

from ssh_marked_block import ensure_marked_file, replace_marked_block

# --- constants ---------------------------------------------------------------

AK_BEGIN = "# BEGIN STAYTURGID-ET-MAC"
AK_END = "# END STAYTURGID-ET-MAC"
SSH_CFG_BEGIN = "# BEGIN STAYTURGID-CONTROL-ET"
SSH_CFG_END = "# END STAYTURGID-CONTROL-ET"

DEFAULT_ET_PORT = 2022
DEFAULT_SSH_PORT = 22
FLEET_IDENTITY = "id_ed25519_fleet"
STATE_SUBDIR = "et-mac"

_PUBKEY_LINE = re.compile(r"^(ssh-(?:ed25519|rsa|dss)|ecdsa-sha2-\S+|sk-ssh-\S+)\s+\S+")


def config_root() -> Path:
    return Path(os.environ.get("STAYTURGID_CONFIG", os.path.expanduser("~/.config/stayturgid")))


def state_dir() -> Path:
    d = config_root() / "state" / STATE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def control_facts_path() -> Path:
    return state_dir() / "control.json"


def pubkey_cache_path(host: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", host.strip()) or "host"
    return state_dir() / f"{safe}.pub"


def default_authorized_keys() -> Path:
    return Path(os.path.expanduser("~/.ssh/authorized_keys"))


def default_devices_conf() -> Path:
    return Path(
        os.environ.get(
            "STAYTURGID_DEVICES_CONF",
            str(config_root() / "devices.conf"),
        )
    )


def ssh_strict_host_key() -> str:
    """StrictHostKeyChecking mode for fleet SSH/ET (default accept-new on Tailscale).

    Set ``STAYTURGID_SSH_STRICT_HOST_KEY=yes`` (or ``ask``) and optionally
    ``STAYTURGID_SSH_KNOWN_HOSTS=/path/to/known_hosts`` to pin keys (review L6).
    """
    raw = (
        os.environ.get("STAYTURGID_SSH_STRICT_HOST_KEY")
        or os.environ.get("STAYTURGID_SSH_STRICTHOSTKEYCHECKING")
        or "accept-new"
    ).strip()
    return raw or "accept-new"


def ssh_host_key_cli_opts() -> list[str]:
    """``-o`` options for subprocess ssh regarding host keys."""
    opts = [f"StrictHostKeyChecking={ssh_strict_host_key()}"]
    known = os.environ.get("STAYTURGID_SSH_KNOWN_HOSTS", "").strip()
    if known:
        opts.append(f"UserKnownHostsFile={known}")
    return opts


def ssh_host_key_config_lines(indent: str = "    ") -> list[str]:
    """Lines for an OpenSSH config Host block."""
    lines = [f"{indent}StrictHostKeyChecking {ssh_strict_host_key()}"]
    known = os.environ.get("STAYTURGID_SSH_KNOWN_HOSTS", "").strip()
    if known:
        lines.append(f"{indent}UserKnownHostsFile {known}")
    return lines


# --- control facts -----------------------------------------------------------


def load_control_facts() -> dict[str, Any]:
    path = control_facts_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_control_facts(facts: dict[str, Any]) -> None:
    path = control_facts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o644)


def merge_control_facts(
    *,
    user: str | None = None,
    tailscale_ip: str | None = None,
    lan_ip: str | None = None,
    et_port: int | None = None,
    ssh_port: int | None = None,
    aliases: list[str] | None = None,
    identity: str | None = None,
    hostname: str | None = None,
) -> dict[str, Any]:
    facts = load_control_facts()
    if user:
        facts["user"] = user
    if tailscale_ip:
        facts["tailscale_ip"] = tailscale_ip
    if lan_ip is not None:
        facts["lan_ip"] = lan_ip or ""
    if et_port is not None:
        facts["et_port"] = int(et_port)
    if ssh_port is not None:
        facts["ssh_port"] = int(ssh_port)
    if aliases is not None:
        facts["aliases"] = list(aliases)
    if identity:
        facts["identity"] = identity
    if hostname:
        facts["hostname"] = hostname
    facts.setdefault("user", os.environ.get("USER") or "operator")
    facts.setdefault("et_port", DEFAULT_ET_PORT)
    facts.setdefault("ssh_port", DEFAULT_SSH_PORT)
    facts.setdefault("identity", FLEET_IDENTITY)
    save_control_facts(facts)
    return facts


# --- pubkey cache ------------------------------------------------------------


def normalize_pubkey_line(line: str, *, comment: str | None = None) -> str | None:
    line = (line or "").strip()
    if not line or line.startswith("#"):
        return None
    if not _PUBKEY_LINE.match(line):
        return None
    parts = line.split()
    if len(parts) < 2:
        return None
    key_type, key_body = parts[0], parts[1]
    cmt = comment if comment is not None else (" ".join(parts[2:]) if len(parts) > 2 else "")
    if cmt:
        return f"{key_type} {key_body} {cmt}"
    return f"{key_type} {key_body}"


def cache_pubkey(host: str, line: str) -> str | None:
    norm = normalize_pubkey_line(line, comment=f"{host}-fleet")
    if not norm:
        # keep original comment if valid key
        norm = normalize_pubkey_line(line)
    if not norm:
        return None
    path = pubkey_cache_path(host)
    path.write_text(norm + "\n", encoding="utf-8")
    path.chmod(0o644)
    return norm


def list_cached_pubkeys() -> list[str]:
    lines: list[str] = []
    for path in sorted(state_dir().glob("*.pub")):
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        norm = normalize_pubkey_line(raw)
        if norm:
            lines.append(norm)
    # stable unique by key body
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        parts = line.split()
        body = parts[1] if len(parts) > 1 else line
        if body in seen:
            continue
        seen.add(body)
        out.append(line)
    return out


def collect_fleet_pubkey(host: str, *, timeout: int = 12) -> tuple[bool, str]:
    """SSH to inventory host and slurp id_ed25519_fleet.pub."""
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={min(timeout, 15)}",
    ]
    for opt in ssh_host_key_cli_opts():
        cmd.extend(["-o", opt])
    cmd.extend(
        [
            host,
            f"cat ~/.ssh/{FLEET_IDENTITY}.pub 2>/dev/null || "
            f"cat /data/data/com.termux/files/home/.ssh/{FLEET_IDENTITY}.pub",
        ]
    )
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)[:200]
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ssh failed").strip()[:200]
        return False, err
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return False, "empty pubkey"
    cached = cache_pubkey(host, line[0])
    if not cached:
        return False, "invalid pubkey"
    return True, cached


def hosts_from_devices_conf(path: Path | None = None) -> list[str]:
    conf = path or default_devices_conf()
    try:
        from stayturgid_device import iter_devices_conf

        return [name for name, *_ in iter_devices_conf(str(conf))]
    except (ImportError, AttributeError):  # noqa: BLE001
        pass
    hosts: list[str] = []
    try:
        text = conf.read_text(encoding="utf-8")
    except OSError:
        return hosts
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts:
            hosts.append(parts[0])
    return hosts


# --- authorized_keys ---------------------------------------------------------


def render_ak_block_body(pubkeys: list[str] | None = None) -> str:
    keys = pubkeys if pubkeys is not None else list_cached_pubkeys()
    lines = [
        "# Fleet id_ed25519_fleet pubkeys — phone→Mac SSH bootstrap for et.",
        "# Managed by control/bin/ensure_et_mac.py / control_node agents.",
        "# Do not edit inside markers; peer-help ForceCommand keys stay outside.",
    ]
    lines.extend(keys)
    return "\n".join(lines)


def apply_authorized_keys(
    path: Path | None = None,
    pubkeys: list[str] | None = None,
) -> bool:
    """Rewrite STAYTURGID-ET-MAC block. Returns True if file changed."""
    ak = path or default_authorized_keys()
    body = render_ak_block_body(pubkeys)
    return ensure_marked_file(ak, begin=AK_BEGIN, end=AK_END, body=body, mode=0o600)


# --- device SSH config -------------------------------------------------------


def render_device_ssh_config(
    *,
    user: str,
    tailscale_ip: str,
    lan_ip: str = "",
    identity: str = FLEET_IDENTITY,
    aliases: list[str] | None = None,
    hostname_aliases: list[str] | None = None,
) -> str:
    """Render Host block for Termux → Mac (et bootstrap + plain ssh)."""
    host_tokens: list[str] = []
    for a in aliases or ["mac", "macbook"]:
        if a and a not in host_tokens:
            host_tokens.append(a)
    for a in hostname_aliases or []:
        if a and a not in host_tokens:
            host_tokens.append(a)
    if tailscale_ip and tailscale_ip not in host_tokens:
        host_tokens.append(tailscale_ip)
    if lan_ip and lan_ip not in host_tokens:
        host_tokens.append(lan_ip)

    hosts_line = " ".join(host_tokens)
    hk = ssh_host_key_config_lines()
    lines = [
        f"Host {hosts_line}",
        f"    HostName {tailscale_ip}",
        f"    User {user}",
        f"    IdentityFile ~/.ssh/{identity}",
        "    IdentitiesOnly yes",
        "    PreferredAuthentications publickey",
        *hk,
    ]
    if lan_ip and lan_ip != tailscale_ip:
        lines += [
            "",
            "Host mac-lan",
            f"    HostName {lan_ip}",
            f"    User {user}",
            f"    IdentityFile ~/.ssh/{identity}",
            "    IdentitiesOnly yes",
            "    PreferredAuthentications publickey",
            *hk,
        ]
    return "\n".join(lines)


def apply_device_ssh_config_text(existing: str, fragment: str) -> tuple[str, bool]:
    return replace_marked_block(
        existing,
        begin=SSH_CFG_BEGIN,
        end=SSH_CFG_END,
        body=fragment,
    )


# --- health ------------------------------------------------------------------


def etserver_listening(port: int = DEFAULT_ET_PORT, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return True
    except OSError:
        return False


def etserver_launchd_running() -> bool | None:
    """True/False if launchctl known; None if not macOS / not queryable."""
    try:
        proc = subprocess.run(
            ["launchctl", "print", "system/homebrew.mxcl.et"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return False
    out = proc.stdout or ""
    if "state = running" in out:
        return True
    if "state = " in out:
        return False
    return None


def probe_control_ssh(
    *,
    host_token: str = "mac",
    user: str | None = None,
    identity: str | None = None,
    timeout: int = 10,
) -> tuple[bool, str]:
    """BatchMode ssh to control node (from a device, or Mac loopback)."""
    facts = load_control_facts()
    target = host_token
    if user or facts.get("user"):
        u = user or facts.get("user")
        # if host_token is bare IP, prefix user
        if "@" not in target and u:
            target = f"{u}@{target}" if re.match(r"^[\d.]+$", host_token) else target
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "PreferredAuthentications=publickey",
    ]
    for opt in ssh_host_key_cli_opts():
        cmd.extend(["-o", opt])
    ident = identity or facts.get("identity") or FLEET_IDENTITY
    # only force -i when path exists (device) or absolute
    id_path = Path(os.path.expanduser(f"~/.ssh/{ident}"))
    if id_path.is_file():
        cmd.extend(["-i", str(id_path)])
    cmd.extend([target, "true"])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)[:200]
    if proc.returncode == 0:
        return True, "ok"
    return False, (proc.stderr or proc.stdout or "fail").strip()[:200]
