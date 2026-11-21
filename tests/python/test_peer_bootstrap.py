"""Unit tests for peer bootstrap / rish helpers (no device required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import stayturgid_handsets as th
import stayturgid_peer_bootstrap as pb


def test_peer_endpoints_prefer_lan():
    assert pb.peer_endpoints({"lan": "192.0.2.1", "tailscale": "100.1.2.3"}) == [
        "192.0.2.1",
        "100.1.2.3",
    ]
    assert pb.peer_endpoints({"lan": "-", "tailscale": "100.1.2.3"}) == ["100.1.2.3"]


def test_self_adb_targets(tmp_path):
    cfg = {
        "self": {"lan": "192.0.2.13", "tailscale": "100.0.0.13", "usb_serial": "HD8SERIAL1"},
        "peers": [],
    }
    assert pb.self_adb_targets(cfg) == [
        "192.0.2.13:5555",
        "100.0.0.13:5555",
    ]


def test_bootstrap_skips_can_help_false(monkeypatch, tmp_path):
    peers = {
        "self": {"lan": "1.2.3.4", "tailscale": "100.0.0.11", "usb_serial": "HD8SERIAL1"},
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
        serial="HD8SERIAL1",
    )
    assert short == "handsets-start --target 1.2.3.4:5555 --serial HD8SERIAL1 --port 9012"
    mac = pb._remote_help_cmd(
        {
            "kind": "mac",
            "help_cmd": "python3 /Users/x/stayturgid/control/bin/fire_peer_help.py",
        },
        verb="shizuku-start",
        target="1.2.3.4:5555",
        port=9012,
        identity=fleet,
        serial="HD8SERIAL1",
    )
    assert mac.startswith("python3 /Users/x/stayturgid/control/bin/fire_peer_help.py")
    assert "shizuku-start" in mac
    termux = pb._remote_help_cmd(
        {"kind": "termux"},
        verb="ping",
        target="1.2.3.4:5555",
        port=9012,
        identity=fleet,
        serial="HD8SERIAL1",
    )
    assert "--serial HD8SERIAL1" in mac and "--serial HD8SERIAL1" in termux
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


def _captured_ssh_argv(monkeypatch, tmp_path, peer, host):
    monkeypatch.setattr(pb, "FLEET_KEY", str(tmp_path / "fleet"))
    monkeypatch.setattr(pb, "PEERHELP_KEY", str(tmp_path / "missing-peerhelp"))
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(pb.subprocess, "run", fake_run)
    pb._ssh_help(host, verb="handsets-start", target="192.0.2.13:5555", port=9012, serial="HD8SERIAL1", peer=peer)
    return seen["argv"]


def _opts(argv):
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-o"]


def test_peer_ssh_pins_the_host_key_to_the_peer_name_on_both_endpoints(monkeypatch, tmp_path):
    peer = {"name": "s24", "ssh_port": 8022, "ssh_user": "termux"}
    for host in ("192.168.68.56", "100.123.218.30"):  # LAN (DHCP) and Tailscale share one alias
        opts = _opts(_captured_ssh_argv(monkeypatch, tmp_path, peer, host))
        assert "HostKeyAlias=s24" in opts
        assert "StrictHostKeyChecking=yes" in opts
        assert not any("accept-new" in o or o.endswith("=no") for o in opts)


def test_peer_ssh_without_a_name_still_fails_closed(monkeypatch, tmp_path):
    opts = _opts(_captured_ssh_argv(monkeypatch, tmp_path, {"ssh_port": 8022}, "192.0.2.7"))
    assert "StrictHostKeyChecking=yes" in opts and "HostKeyAlias=192.0.2.7" in opts


def test_peer_ssh_alias_matches_the_known_hosts_names_the_deploy_writes():
    """The mesh writes `[<inventory name>]:<port>` and the control-ET tasks `mac`: the alias must be the peer `name`."""
    import yaml

    tpl = (REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/templates/peers.json.j2").read_text()
    assert "'name': h," in tpl and "'name': 'mac'," in tpl
    tasks = yaml.safe_load(
        (REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/tasks/control_et.yml").read_text()
    )
    pin = next(t for t in tasks if t.get("name", "").startswith("Pin the control node's host key under the alias mac"))
    args = pin["ansible.builtin.known_hosts"]
    # HostKeyAlias is looked up bare (no [alias]:port form), whatever the Mac's ssh port.
    assert args["state"] == "present" and args["name"] == "mac" and args["key"].startswith("mac ")


def test_mesh_known_hosts_carry_a_bare_line_per_peer_for_hostkeyalias():
    import json
    import re

    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            str(REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/templates")
        )
    )
    env.filters["to_json"] = json.dumps
    env.filters["split"] = lambda v, sep=None: v.split(sep)
    env.tests["file"] = lambda path: False
    out = env.get_template("known_hosts_mesh.j2").render(
        groups={"stayturgid": ["s24", "t2e"]},
        inventory_hostname="s24",
        stayturgid_ssh_mesh_group="stayturgid",
        stayturgid_ssh_mesh_host_keys_dir="/nonexistent",
        hostvars={
            "t2e": {
                "inventory_hostname": "t2e",
                "ansible_host": "100.73.253.10",
                "ansible_port": 8022,
                "device_lan_ip": "192.168.68.62",
                "stayturgid_sshd_host_pubkey": "ssh-ed25519 AAAAKEY comment",
                "stayturgid_ssh_known_host_aliases": ["t2e", "100.73.253.10", "192.168.68.62"],
            }
        },
    )
    names = [e["name"] for e in json.loads(out)]
    assert "t2e" in names  # what `HostKeyAlias=t2e` looks up
    assert "[t2e]:8022" in names and "[192.168.68.62]:8022" in names  # the host-name forms stay
    assert all(re.match(r"^t2e ssh-ed25519 AAAAKEY$", e["key"]) for e in json.loads(out) if e["name"] == "t2e")


# --- #328: the helper identity-checks the adb target against self.usb_serial -------------------


def _peers_cfg(tmp_path, usb_serial):
    cfg = {
        "self": {"lan": "192.0.2.13", "tailscale": "100.0.0.13", "usb_serial": usb_serial},
        "handsets_port": 9012,
        "peers": [{"name": "s24", "lan": "192.0.2.7", "tailscale": "100.0.0.7", "can_help": True}],
    }
    path = tmp_path / "peers"
    path.write_text(json.dumps(cfg))
    return str(path)


def _arm(monkeypatch, tmp_path):
    (tmp_path / "key").write_text("x")
    monkeypatch.setattr(pb, "FLEET_KEY", str(tmp_path / "key"))
    monkeypatch.setattr(pb, "PEERHELP_KEY", str(tmp_path / "missing-peerhelp"))
    monkeypatch.setattr(pb, "_wire_ping", lambda port: False)
    monkeypatch.setattr(pb, "_tcp_open", lambda *a, **k: True)


@pytest.mark.parametrize("serial", ["", "-", None, "a b", "x;rm -rf", "--version", "a" * 80])
def test_self_usb_serial_rejects_unusable_values(serial):
    assert pb.self_usb_serial({"self": {"usb_serial": serial}}) is None


def test_self_usb_serial_accepts_a_real_serial():
    assert pb.self_usb_serial({"self": {"usb_serial": " 4HW0123456789 "}}) == "4HW0123456789"


@pytest.mark.parametrize("serial", ["", "-", "a b"])
@pytest.mark.parametrize("verb", ["handsets", "shizuku"])
def test_bootstrap_refuses_to_ask_a_helper_without_a_usable_serial(monkeypatch, tmp_path, serial, verb):
    _arm(monkeypatch, tmp_path)
    monkeypatch.setattr(pb, "_ssh_help", lambda *a, **k: pytest.fail("no helper may be asked without a serial"))
    path = _peers_cfg(tmp_path, serial)
    ok, detail = (pb.bootstrap_handsets if verb == "handsets" else pb.bootstrap_shizuku)(peers_path=path)
    assert ok is False and "usb_serial" in detail


@pytest.mark.parametrize("verb", ["handsets", "shizuku"])
def test_bootstrap_passes_the_serial_to_every_helper_request(monkeypatch, tmp_path, verb):
    _arm(monkeypatch, tmp_path)
    seen = []

    def fake(host, **kwargs):
        seen.append(kwargs)
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "refused"})()

    monkeypatch.setattr(pb, "_ssh_help", fake)
    path = _peers_cfg(tmp_path, "HD8SERIAL1")
    (pb.bootstrap_handsets if verb == "handsets" else pb.bootstrap_shizuku)(peers_path=path)
    assert seen and all(k["serial"] == "HD8SERIAL1" for k in seen)
