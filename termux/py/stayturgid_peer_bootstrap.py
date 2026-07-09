#!/usr/bin/env python3
"""Ask a fleet peer to start Handsets on this device (Fire OS / no local ADB).

Reads ``~/.stayturgid/peers`` (Ansible-rendered). For each peer: TCP probe
sshd, SSH invoke ``stayturgid_peer_help.py handsets-start``, then local wire
``ping`` to the Handsets daemon.

Usage:
  stayturgid_peer_bootstrap.py              # start Handsets via first peer
  stayturgid_peer_bootstrap.py --port 9008
  stayturgid_peer_bootstrap.py --list
  stayturgid_peer_bootstrap.py shizuku      # start Shizuku via peer instead

Env:
  STAYTURGID_PEER_BOOTSTRAP=0   disable
  STAYTURGID_HANDSETS_PORT      daemon port (default from peers file / 9008)
"""
from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
from typing import Any

HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
STG = os.path.join(HOME, ".stayturgid")
PEERS_PATH = os.path.join(STG, "peers")
FLEET_KEY = os.path.join(HOME, ".ssh", "id_ed25519_fleet")
SSH_PORT = 8022


def enabled() -> bool:
    return os.environ.get("STAYTURGID_PEER_BOOTSTRAP", "1") != "0"


def load_peers(path: str = PEERS_PATH) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def _tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wire_ping(port: int, timeout: float = 3.0) -> bool:
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    except OSError:
        return False
    try:
        body = b"ping"
        sock.sendall(struct.pack(">I", len(body)) + body)
        sock.settimeout(timeout)
        hdr = b""
        while len(hdr) < 4:
            chunk = sock.recv(4 - len(hdr))
            if not chunk:
                return False
            hdr += chunk
        (n,) = struct.unpack(">I", hdr)
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data == b"pong"
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _ssh_help(
    peer_host: str,
    *,
    verb: str,
    target: str,
    port: int,
    identity: str = FLEET_KEY,
    user: str = "djbclark",
    timeout: float = 45,
) -> subprocess.CompletedProcess:
    remote = (
        "export PATH=$PREFIX/bin:$PATH; "
        "python3 $HOME/.stayturgid/bin/stayturgid_peer_help.py %s "
        "--target %s --port %d"
        % (verb, target, port)
    )
    return subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "StrictHostKeyChecking=yes",
            "-p",
            str(SSH_PORT),
            "-i",
            identity,
            "%s@%s" % (user, peer_host),
            remote,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def peer_endpoints(peer: dict[str, Any]) -> list[str]:
    """Prefer LAN then Tailscale for SSH reachability."""
    out: list[str] = []
    for key in ("lan", "tailscale"):
        val = peer.get(key)
        if val and val not in out and val != "-":
            out.append(val)
    return out


def self_adb_targets(cfg: dict[str, Any]) -> list[str]:
    """Addresses the helper should ``adb connect`` to reach *this* device."""
    me = cfg.get("self") or {}
    out: list[str] = []
    for key in ("lan", "tailscale"):
        val = me.get(key)
        if val and val != "-":
            out.append("%s:5555" % val)
    return out


def bootstrap_handsets(
    *,
    port: int | None = None,
    peers_path: str = PEERS_PATH,
) -> tuple[bool, str]:
    """Return (ok, detail). No-op success if daemon already answering."""
    if not enabled():
        return False, "peer bootstrap disabled"
    if not os.path.isfile(peers_path):
        return False, "no peers file (%s)" % peers_path
    cfg = load_peers(peers_path)
    port = int(
        port
        or os.environ.get("STAYTURGID_HANDSETS_PORT")
        or cfg.get("handsets_port")
        or 9008
    )
    if _wire_ping(port):
        return True, "already up port=%d" % port
    if not os.path.isfile(FLEET_KEY):
        return False, "missing fleet SSH key %s" % FLEET_KEY
    targets = self_adb_targets(cfg)
    if not targets:
        return False, "self has no lan/tailscale in peers file"
    errors: list[str] = []
    for peer in cfg.get("peers") or []:
        if peer.get("can_help") is False:
            continue
        name = peer.get("name") or "?"
        for ssh_host in peer_endpoints(peer):
            if not _tcp_open(ssh_host, SSH_PORT, timeout=2.0):
                errors.append("%s(%s): sshd closed" % (name, ssh_host))
                continue
            for adb_target in targets:
                r = _ssh_help(
                    ssh_host,
                    verb="handsets-start",
                    target=adb_target,
                    port=port,
                )
                detail = ((r.stdout or "") + (r.stderr or "")).strip()
                if r.returncode == 0 and _wire_ping(port):
                    return True, "via %s → %s: %s" % (name, adb_target, detail)
                errors.append(
                    "%s→%s rc=%s %s"
                    % (name, adb_target, r.returncode, detail[:200])
                )
                # unauthorized: try next self address / peer
    return False, "; ".join(errors[:6]) or "no peers reachable"


def bootstrap_shizuku(peers_path: str = PEERS_PATH) -> tuple[bool, str]:
    if not enabled() or not os.path.isfile(peers_path):
        return False, "unavailable"
    cfg = load_peers(peers_path)
    targets = self_adb_targets(cfg)
    if not targets:
        return False, "no self addresses"
    for peer in cfg.get("peers") or []:
        if peer.get("can_help") is False:
            continue
        name = peer.get("name") or "?"
        for ssh_host in peer_endpoints(peer):
            if not _tcp_open(ssh_host, SSH_PORT, timeout=2.0):
                continue
            for adb_target in targets:
                r = _ssh_help(
                    ssh_host,
                    verb="shizuku-start",
                    target=adb_target,
                    port=int(cfg.get("handsets_port") or 9008),
                )
                if r.returncode == 0:
                    return True, "via %s: %s" % (
                        name,
                        (r.stdout or "").strip(),
                    )
    return False, "all peers failed"


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        sys.stderr.write(
            "usage: stayturgid_peer_bootstrap.py [--list] [--port N] [handsets|shizuku]\n"
        )
        return 2
    if argv and argv[0] == "--list":
        if not os.path.isfile(PEERS_PATH):
            print("no peers file", file=sys.stderr)
            return 1
        print(json.dumps(load_peers(), indent=2))
        return 0
    port = None
    verb = "handsets"
    args = list(argv)
    while args:
        if args[0] == "--port" and len(args) > 1:
            port = int(args[1])
            args = args[2:]
            continue
        if args[0] in ("handsets", "shizuku"):
            verb = args[0]
            args = args[1:]
            continue
        sys.stderr.write("unknown arg %r\n" % args[0])
        return 2
    if verb == "shizuku":
        ok, detail = bootstrap_shizuku()
    else:
        ok, detail = bootstrap_handsets(port=port)
    print(("OK" if ok else "FAIL") + ": " + detail)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
