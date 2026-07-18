"""Unit tests for phone→Mac Eternal Terminal key/config helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "control" / "lib"))

import et_mac as em  # noqa: E402
import ssh_marked_block as smb  # noqa: E402


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
        lan_ip="192.168.1.1",
        identity="id_ed25519_fleet",
        aliases=["mac", "macbook"],
    )
    assert "Host mac" in cfg or "Host mac macbook" in cfg
    assert "100.1.2.3" in cfg
    assert "IdentityFile ~/.ssh/id_ed25519_fleet" in cfg
    assert "IdentitiesOnly yes" in cfg
    assert "Host mac-lan" in cfg
    assert "192.168.1.1" in cfg
    assert "StrictHostKeyChecking accept-new" in cfg


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
