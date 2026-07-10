#!/usr/bin/env python3
"""Ensure phone→Mac Eternal Terminal prerequisites on the control node.

- Collect fleet ``id_ed25519_fleet.pub`` from inventory hosts (SSH)
- Cache under ``~/.config/stayturgid/state/et-mac/``
- Rewrite marked block in ``~/.ssh/authorized_keys`` (preserves peer-help)
- Record control Tailscale/LAN facts for device templates
- Optionally verify etserver is listening

Usage::

  python3 control/bin/ensure_et_mac.py
  python3 control/bin/ensure_et_mac.py --hosts s24,p7a,hd8
  python3 control/bin/ensure_et_mac.py --apply-only
  python3 control/bin/ensure_et_mac.py --check

Idempotent. Safe to run from launchd / fleet-health / ``make deploy-mac``.
Never prints or writes private keys.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import et_mac as em  # noqa: E402


def _detect_tailscale_ip() -> str:
    for cmd in (["tailscale", "ip", "-4"], ["tailscale", "ip"]):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if proc.returncode == 0:
                for line in (proc.stdout or "").splitlines():
                    line = line.strip()
                    if line.startswith("100."):
                        return line
        except (OSError, subprocess.TimeoutExpired):
            continue
    return ""


def _detect_lan_ip() -> str:
    # Prefer env / facts; fall back to UDP trick for primary iface.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hosts",
        default="",
        help="Comma-separated inventory aliases (default: devices.conf)",
    )
    ap.add_argument(
        "--apply-only",
        action="store_true",
        help="Only rewrite authorized_keys from cache (no collect)",
    )
    ap.add_argument(
        "--collect-only",
        action="store_true",
        help="Only collect/cache pubkeys (no authorized_keys write)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Check etserver listen + report cache size; exit 1 if down",
    )
    ap.add_argument(
        "--user",
        default=os.environ.get("STAYTURGID_CONTROL_ET_USER")
        or os.environ.get("USER")
        or "djbclark",
    )
    ap.add_argument(
        "--tailscale-ip",
        default=os.environ.get("STAYTURGID_CONTROL_TAILSCALE_IP", ""),
    )
    ap.add_argument(
        "--lan-ip",
        default=os.environ.get("STAYTURGID_CONTROL_LAN_IP", ""),
    )
    ap.add_argument(
        "--et-port",
        type=int,
        default=int(os.environ.get("STAYTURGID_CONTROL_ET_PORT", em.DEFAULT_ET_PORT)),
    )
    ap.add_argument(
        "--authorized-keys",
        default="",
        help="Override path to authorized_keys",
    )
    args = ap.parse_args(argv)

    ts_ip = args.tailscale_ip or _detect_tailscale_ip()
    lan_ip = args.lan_ip or _detect_lan_ip()
    hostname = socket.gethostname().split(".")[0]
    aliases = ["mac", "macbook", hostname]
    if hostname.endswith("s-MacBook-Air"):
        aliases.append(hostname)
    # MagicDNS-style short names often used with et
    full = socket.gethostname()
    if full and full not in aliases:
        aliases.append(full.split(".")[0])

    em.merge_control_facts(
        user=args.user,
        tailscale_ip=ts_ip,
        lan_ip=lan_ip,
        et_port=args.et_port,
        aliases=aliases,
        identity=em.FLEET_IDENTITY,
        hostname=full or hostname,
    )

    rc = 0
    if not args.apply_only and not args.check:
        if args.hosts.strip():
            hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
        else:
            hosts = em.hosts_from_devices_conf()
        if not hosts:
            print("WARN: no hosts in devices.conf and --hosts empty", file=sys.stderr)
        for host in hosts:
            ok, detail = em.collect_fleet_pubkey(host)
            if ok:
                print(f"OK collect {host}: {detail.split()[-1] if detail else 'cached'}")
            else:
                print(f"WARN collect {host}: {detail}", file=sys.stderr)
                # soft-fail collect; still apply what we have

    if not args.collect_only and not args.check:
        ak = Path(args.authorized_keys) if args.authorized_keys else None
        keys = em.list_cached_pubkeys()
        if not keys:
            print(
                "WARN: no cached fleet pubkeys — authorized_keys block empty/minimal",
                file=sys.stderr,
            )
        changed = em.apply_authorized_keys(ak, keys)
        print(
            "OK authorized_keys %s (%d fleet keys)"
            % ("updated" if changed else "unchanged", len(keys))
        )

    # always health-ish report at end unless pure collect
    if not args.collect_only or args.check:
        listening = em.etserver_listening(args.et_port)
        launchd = em.etserver_launchd_running()
        nkeys = len(em.list_cached_pubkeys())
        facts = em.load_control_facts()
        print(
            "etserver port=%s listen=%s launchd=%s keys=%d user=%s ts=%s lan=%s"
            % (
                args.et_port,
                "yes" if listening else "NO",
                "yes" if launchd else ("no" if launchd is False else "?"),
                nkeys,
                facts.get("user", args.user),
                facts.get("tailscale_ip") or ts_ip or "-",
                facts.get("lan_ip") or lan_ip or "-",
            )
        )
        if args.check and not listening:
            rc = 1
        if args.check and nkeys == 0:
            rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
