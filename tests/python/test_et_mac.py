"""Unit tests for phone→Mac Eternal Terminal key/config helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "control" / "lib"))

import et_mac as em
import ssh_marked_block as smb


def test_replace_marked_block_append():
    text = "ssh-ed25519 AAAAhuman human\n"
    new, changed = smb.replace_marked_block(
        text,
        begin=em.AK_BEGIN,
        end=em.AK_END,
        body="ssh-ed25519 AAAAfleet oneui-device-fleet",
    )
    assert changed
    assert em.AK_BEGIN in new
    assert "oneui-device-fleet" in new
    assert "human" in new
    assert new.index("human") < new.index(em.AK_BEGIN)


def test_replace_marked_block_update_preserves_outside():
    text = (
        "ssh-ed25519 AAAAhuman human\n"
        f"{em.AK_BEGIN}\n"
        "ssh-ed25519 AAAAold old-fleet\n"
        f"{em.AK_END}\n"
        'command="/x",no-port-forwarding ssh-ed25519 AAAApeer fireos-device-peerhelp\n'
    )
    new, changed = smb.replace_marked_block(
        text,
        begin=em.AK_BEGIN,
        end=em.AK_END,
        body="ssh-ed25519 AAAAnew oneui-device-fleet",
    )
    assert changed
    assert "AAAAnew" in new
    assert "AAAAold" not in new
    assert "fireos-device-peerhelp" in new
    assert "command=" in new
    assert "human" in new


def test_normalize_pubkey_line():
    line = "ssh-ed25519 AAAATEST comment-here"
    assert em.normalize_pubkey_line(line, comment="oneui-device-fleet").endswith("oneui-device-fleet")
    assert em.normalize_pubkey_line("# comment") is None
    assert em.normalize_pubkey_line("not-a-key") is None


def test_render_device_ssh_config_includes_identity_and_ips():
    cfg = em.render_device_ssh_config(
        user="operator",
        tailscale_ip="100.1.2.3",
        lan_ip="192.0.2.1",
        identity="id_ed25519_fleet",
        aliases=["mac", "macbook"],
    )
    assert "Host mac" in cfg or "Host mac macbook" in cfg
    assert "100.1.2.3" in cfg
    assert "IdentityFile ~/.ssh/id_ed25519_fleet" in cfg
    assert "IdentitiesOnly yes" in cfg
    assert "Host mac-lan" in cfg
    assert "192.0.2.1" in cfg
    assert "StrictHostKeyChecking accept-new" in cfg  # the Tailscale block
    lan = cfg.split("Host mac-lan\n")[1]
    assert "HostKeyAlias mac" in lan and "StrictHostKeyChecking yes" in lan and "accept-new" not in lan
    assert lan.count("StrictHostKeyChecking") == 1


def test_ssh_host_key_pin_env(monkeypatch):
    monkeypatch.setenv("STAYTURGID_SSH_STRICT_HOST_KEY", "yes")
    monkeypatch.setenv("STAYTURGID_SSH_KNOWN_HOSTS", "/tmp/kh")
    assert em.ssh_strict_host_key() == "yes"
    opts = em.ssh_host_key_cli_opts()
    assert "StrictHostKeyChecking=yes" in opts
    assert "UserKnownHostsFile=/tmp/kh" in opts
    cfg = em.render_device_ssh_config(user="u", tailscale_ip="100.0.0.1", lan_ip="", aliases=["mac"])
    assert "StrictHostKeyChecking yes" in cfg
    assert "UserKnownHostsFile /tmp/kh" in cfg


def test_mac_lan_block_is_strict_whatever_the_env_override_says(monkeypatch):
    monkeypatch.setenv("STAYTURGID_SSH_STRICT_HOST_KEY", "no")
    cfg = em.render_device_ssh_config(user="u", tailscale_ip="100.0.0.1", lan_ip="192.0.2.5", aliases=["mac"])
    lan = cfg.split("Host mac-lan\n")[1]
    assert "StrictHostKeyChecking yes" in lan and "StrictHostKeyChecking no" not in lan
    assert "HostKeyAlias %s" % em.MAC_PEER_ALIAS in lan
    assert "StrictHostKeyChecking no" in cfg.split("Host mac-lan")[0]  # the Tailscale block keeps the override


def test_apply_authorized_keys_file(tmp_path, monkeypatch):
    ak = tmp_path / "authorized_keys"
    ak.write_text(
        'command="/help",no-port-forwarding ssh-ed25519 AAAApeer fireos-device-peerhelp\n',
        encoding="utf-8",
    )
    # point cache at tmp
    monkeypatch.setattr(em, "state_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "oneui-device.pub").write_text("ssh-ed25519 AAAAs24 oneui-device-fleet\n", encoding="utf-8")
    changed = em.apply_authorized_keys(ak)
    assert changed
    text = ak.read_text(encoding="utf-8")
    assert "oneui-device-fleet" in text
    assert "fireos-device-peerhelp" in text
    assert "command=" in text
    # second apply idempotent
    assert em.apply_authorized_keys(ak) is False


def test_apply_device_ssh_config_text_roundtrip():
    frag = em.render_device_ssh_config(
        user="u",
        tailscale_ip="100.0.0.1",
        lan_ip="",
        aliases=["mac"],
    )
    new, changed = em.apply_device_ssh_config_text("", frag)
    assert changed
    assert em.SSH_CFG_BEGIN in new
    new2, changed2 = em.apply_device_ssh_config_text(new, frag)
    assert changed2 is False


TERMUX_ROLE = ROOT / "ansible_collections/stayturgid/termux/roles/termux_userland"


def test_template_mac_lan_block_pins_like_the_python_renderer():
    import jinja2

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TERMUX_ROLE / "templates")))
    out = env.get_template("ssh_config_control_et.j2").render(
        stayturgid_mac_peer={"user": "operator", "tailscale": "100.1.2.3", "lan": "192.0.2.1"},
    )
    lan = out.split("Host mac-lan\n")[1]
    assert "HostKeyAlias %s" % em.MAC_PEER_ALIAS in lan
    assert "StrictHostKeyChecking yes" in lan and "accept-new" not in lan
    assert "StrictHostKeyChecking accept-new" in out.split("Host mac-lan")[0]  # the Tailscale block is unchanged
    py = em.render_device_ssh_config(user="operator", tailscale_ip="100.1.2.3", lan_ip="192.0.2.1").split(
        "Host mac-lan\n"
    )[1]
    keys = lambda text: {ln.split()[0] for ln in text.splitlines() if ln.strip()}  # noqa: E731
    assert keys(lan) == keys(py)


def test_deploy_scans_then_pins_the_mac_host_key_under_the_alias():
    import yaml

    tasks = yaml.safe_load((TERMUX_ROLE / "tasks/control_et.yml").read_text())
    names = [t.get("name", "") for t in tasks]
    scan = next(n for n in names if n.startswith("Scan the control node's ssh host key"))
    assert any(n.startswith("Warn when the control node's host key could not be scanned") for n in names)
    pin = next(n for n in names if n.startswith("Pin the control node's host key under the alias mac"))
    assert names.index(scan) < names.index(pin)
    assert tasks[names.index(pin)]["ansible.builtin.known_hosts"]["state"] == "present"  # in place: never empty
    scan_task = tasks[names.index(scan)]
    # Per phone, not run_once: a run_once task takes its `when` from the first host only.
    assert scan_task["delegate_to"] == "localhost" and "run_once" not in scan_task
    assert scan_task["changed_when"] is False
