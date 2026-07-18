"""Unit tests for peer bootstrap / rish helpers (no device required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import stayturgid_handsets as th  # noqa: E402
import stayturgid_peer_bootstrap as pb  # noqa: E402


def test_peer_endpoints_prefer_lan():
    assert pb.peer_endpoints({"lan": "192.168.1.1", "tailscale": "100.1.2.3"}) == [
        "192.168.1.1",
        "100.1.2.3",
    ]
    assert pb.peer_endpoints({"lan": "-", "tailscale": "100.1.2.3"}) == ["100.1.2.3"]


def test_self_adb_targets(tmp_path):
    cfg = {
        "self": {"lan": "192.0.2.13", "tailscale": "100.0.0.13"},
        "peers": [],
    }
    assert pb.self_adb_targets(cfg) == [
        "192.0.2.13:5555",
        "100.0.0.13:5555",
    ]


def test_bootstrap_skips_can_help_false(monkeypatch, tmp_path):
    peers = {
        "self": {"lan": "1.2.3.4", "tailscale": "100.1.1.1"},
        "handsets_port": 9012,
        "peers": [
            {
                "name": "fireos-device",
                "lan": "9.9.9.9",
                "tailscale": "100.9.9.9",
                "can_help": False,
            }
        ],
    }
    path = tmp_path / "peers"
    path.write_text(json.dumps(peers))
    monkeypatch.setattr(pb, "FLEET_KEY", str(tmp_path / "key"))
    monkeypatch.setattr(pb, "PEERHELP_KEY", str(tmp_path / "missing-peerhelp"))
    (tmp_path / "key").write_text("x")
    monkeypatch.setattr(pb, "_wire_ping", lambda port: False)
    monkeypatch.setattr(pb, "_tcp_open", lambda *a, **k: True)

    called = []

    def boom(*a, **k):
        called.append(1)
        raise AssertionError("should not SSH to can_help=false")

    monkeypatch.setattr(pb, "_ssh_help", boom)
    ok, detail = pb.bootstrap_handsets(peers_path=str(path))
    assert ok is False
    assert called == []
    assert "no peers" in detail or detail == "no peers reachable"


def test_peer_ssh_port_mac():
    assert pb._peer_ssh_port({"ssh_port": 22, "kind": "mac"}) == 22
    assert pb._peer_ssh_port({}) == 8022


def test_identity_prefers_peerhelp(tmp_path, monkeypatch):
    ph = tmp_path / "id_ed25519_peerhelp"
    ph.write_text("x")
    monkeypatch.setattr(pb, "PEERHELP_KEY", str(ph))
    monkeypatch.setattr(pb, "FLEET_KEY", str(tmp_path / "fleet"))
    assert pb._identity_for_peer({"kind": "termux"}) == str(ph)


def test_remote_help_cmd_force_vs_fleet(tmp_path, monkeypatch):
    ph = str(tmp_path / "id_ed25519_peerhelp")
    fleet = str(tmp_path / "id_ed25519_fleet")
    short = pb._remote_help_cmd(
        {"kind": "termux"},
        verb="handsets-start",
        target="1.2.3.4:5555",
        port=9012,
        identity=ph,
    )
    assert short == "handsets-start --target 1.2.3.4:5555 --port 9012"
    mac = pb._remote_help_cmd(
        {
            "kind": "mac",
            "help_cmd": "python3 /Users/x/stayturgid/control/bin/fire_peer_help.py",
        },
        verb="shizuku-start",
        target="1.2.3.4:5555",
        port=9012,
        identity=fleet,
    )
    assert mac.startswith("python3 /Users/x/stayturgid/control/bin/fire_peer_help.py")
    assert "shizuku-start" in mac
    termux = pb._remote_help_cmd(
        {"kind": "termux"},
        verb="ping",
        target="1.2.3.4:5555",
        port=9012,
        identity=fleet,
    )
    assert "stayturgid_peer_help.py" in termux
    assert termux.startswith("export PATH=")


def test_handsets_enabled_with_peer_on_fire(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_HANDSETS", "1")
    monkeypatch.setenv("STAYTURGID_NO_LOCAL_ADB", "1")
    monkeypatch.setenv("STAYTURGID_PEER_BOOTSTRAP", "1")
    peers = tmp_path / "peers"
    peers.write_text("{}")
    monkeypatch.setattr(th, "_PEERS_PATH", str(peers))
    monkeypatch.setattr(th.sh, "privileged_shell_expected", lambda: False)
    assert th.enabled() is True
    assert th._peer_bootstrap_enabled() is True


def test_handsets_disabled_without_peers_on_fire(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_HANDSETS", "1")
    monkeypatch.setenv("STAYTURGID_NO_LOCAL_ADB", "1")
    monkeypatch.setattr(th, "_PEERS_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(th.sh, "privileged_shell_expected", lambda: False)
    assert th.enabled() is False


def test_bootstrap_ssh_user_arg(monkeypatch):
    monkeypatch.setattr(pb, "DEFAULT_SSH_USER", "original-user")
    pb.main(["--ssh-user", "custom-user", "--port", "9012"])
    assert pb.DEFAULT_SSH_USER == "custom-user"
