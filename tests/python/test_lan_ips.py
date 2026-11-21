"""Live LAN-IP discovery (control/lib/lan_ips.py) and the templates that use it."""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import sys
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import lan_ips  # noqa: E402

SSH_FRAGMENT = """\
Host t2e
  HostName 100.73.253.10
  Port 8022
Host t2e-lan
  HostName 192.168.68.63
  HostKeyAlias t2e
  Port 8022
Host t2e-firerpa
  HostName 100.73.253.10
Host s24-lan
  HostName 192.168.68.54
"""

DEVICES_CONF = """\
# alias usb_serial tailscale_ip lan_ip device_label phone_number
s24 RFCX219CHKA 100.123.218.30 192.168.68.54 Galaxy S24 -
t2e TITAN20000040244 100.73.253.10 192.168.68.63 Unihertz Titan 2 -
hd8 GN43T503430603PS 100.124.55.39 192.168.1.157 Kindle Fire HD 8 -
"""


def _ago(**delta) -> str:
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**delta)).isoformat(timespec="seconds")


def test_lan_ipv4_accepts_only_private_lan_addresses():
    assert lan_ips.lan_ipv4("192.168.68.62") == "192.168.68.62"
    assert lan_ips.lan_ipv4("10.0.0.5") == "10.0.0.5"
    assert lan_ips.lan_ipv4("100.73.253.10") is None  # Tailscale CGNAT
    assert lan_ips.lan_ipv4("8.8.8.8") is None
    assert lan_ips.lan_ipv4("127.0.0.1") is None
    assert lan_ips.lan_ipv4("not-an-ip") is None


def test_rewrite_ssh_config_only_touches_lan_blocks():
    out = lan_ips.rewrite_ssh_config(SSH_FRAGMENT, {"t2e": "192.168.68.62", "s24": "192.168.68.61"})
    assert "Host t2e-lan\n  HostName 192.168.68.62\n" in out
    assert "Host s24-lan\n  HostName 192.168.68.61\n" in out
    # Tailscale and FIRERPA aliases keep their HostName.
    assert out.count("HostName 100.73.253.10") == 2


def test_rewrite_devices_conf_sets_lan_column_and_keeps_labels():
    out = lan_ips.rewrite_devices_conf(DEVICES_CONF, {"t2e": "192.168.68.62"})
    assert "t2e TITAN20000040244 100.73.253.10 192.168.68.62 Unihertz Titan 2 -\n" in out
    assert "s24 RFCX219CHKA 100.123.218.30 192.168.68.54 Galaxy S24 -\n" in out
    assert out.startswith("# alias usb_serial")


def test_refresh_persists_applies_and_keeps_offline_devices(tmp_path, monkeypatch):
    state = tmp_path / "state" / "lan_ips.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"hd8": {"ip": "192.168.1.157", "source": "adb", "seen": _ago(hours=2)}}))
    ssh = tmp_path / "ssh"
    ssh.write_text(SSH_FRAGMENT)
    conf = tmp_path / "devices.conf"
    conf.write_text(DEVICES_CONF)
    monkeypatch.setattr(
        lan_ips,
        "discover",
        lambda devices, adb="adb": {"t2e": ("192.168.68.62", "adb"), "s24": ("192.168.68.61", "tailscale")},
    )

    changes = lan_ips.refresh(
        [("t2e", "100.73.253.10"), ("s24", "100.123.218.30"), ("hd8", "100.124.55.39")],
        state_path=str(state),
        ssh_path=str(ssh),
        conf_path=str(conf),
    )

    assert changes == {"t2e": (None, "192.168.68.62"), "s24": (None, "192.168.68.61")}
    saved = json.loads(state.read_text())
    assert saved["hd8"]["ip"] == "192.168.1.157"  # unreachable device keeps last known
    assert saved["s24"]["source"] == "tailscale"
    assert "HostName 192.168.68.62" in ssh.read_text()
    assert "100.73.253.10 192.168.68.62 Unihertz" in conf.read_text()
    # A second run with nothing new reports no changes.
    assert lan_ips.refresh([("t2e", "100.73.253.10")], str(state), str(ssh), str(conf)) == {}


def test_discover_prefers_adb_then_tailscale(monkeypatch):
    monkeypatch.setattr(lan_ips, "adb_wlan_ip", lambda serial, adb="adb": "192.168.68.62" if "73" in serial else None)
    monkeypatch.setattr(lan_ips, "tailscale_lan_endpoints", lambda: {"100.65.230.108": "192.168.68.74"})
    found = lan_ips.discover([("t2e", "100.73.253.10"), ("p7a", "100.65.230.108"), ("hd8", "100.124.55.39")])
    assert found == {"t2e": ("192.168.68.62", "adb"), "p7a": ("192.168.68.74", "tailscale")}


def _render(template: str, **ctx) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(REPO / "ansible/roles/control_node/templates")))
    return env.get_template(template).render(**ctx)


def _hostvars():
    return {
        "t2e": {"ansible_host": "100.73.253.10", "device_lan_ip": "192.168.68.63", "device_usb_serial": "T"},
        "hd8": {"ansible_host": "100.124.55.39", "device_lan_ip": "192.168.1.157", "device_usb_serial": "H"},
    }


def test_templates_prefer_live_lan_ip_over_inventory():
    ctx = dict(
        groups={"stayturgid": ["t2e", "hd8"]},
        hostvars=_hostvars(),
        stayturgid_ssh_identity_files=[],
        stayturgid_firerpa_certificate_path="/k",
        stayturgid_live_lan_ips={"t2e": {"ip": "192.168.68.62"}},
    )
    ssh = _render("ssh_config_stayturgid.j2", **ctx)
    assert "HostName 192.168.68.62\n  HostKeyAlias t2e\n" in ssh
    assert "HostName 192.168.1.157\n  HostKeyAlias hd8\n" in ssh  # no live value: inventory fallback
    assert "192.168.68.63" not in ssh
    conf = _render("devices.conf.j2", **ctx)
    assert "t2e T 100.73.253.10 192.168.68.62 " in conf
    assert "hd8 H 100.124.55.39 192.168.1.157 " in conf


def test_template_tombstones_lan_alias_when_inventory_lan_ip_is_a_dash():
    hostvars = {"t2e": {"ansible_host": "100.73.253.10", "device_lan_ip": "-", "device_usb_serial": "T"}}
    ctx = dict(
        groups={"stayturgid": ["t2e"]},
        hostvars=hostvars,
        stayturgid_ssh_identity_files=[],
        stayturgid_firerpa_certificate_path="/k",
        stayturgid_live_lan_ips={},
    )
    ssh = _render("ssh_config_stayturgid.j2", **ctx)
    assert "\n".join(lan_ips.tombstone_lines("t2e")) + "\n" in ssh  # the exact text lan_ips writes
    assert "HostKeyAlias t2e" not in ssh and "StrictHostKeyChecking yes" not in ssh


def test_refresh_drops_offline_entries_after_the_ttl_and_stops_applying_them(tmp_path, monkeypatch):
    state = tmp_path / "state" / "lan_ips.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps(
            {
                "p7a": {"ip": "192.168.68.66", "source": "adb", "seen": _ago(days=19)},
                "hd8": {"ip": "192.168.1.157", "source": "adb", "seen": _ago(days=2)},
                "s24": {"ip": "192.168.68.75", "source": "adb"},  # no readable `seen`: treated as stale
            }
        )
    )
    ssh = tmp_path / "ssh"
    ssh.write_text("Host p7a-lan\n  HostName 192.168.68.66\nHost hd8-lan\n  HostName 192.168.1.157\n")
    conf = tmp_path / "devices.conf"
    conf.write_text("p7a P 100.65.230.108 192.168.68.66 Pixel 7a -\n")
    monkeypatch.setattr(lan_ips, "discover", lambda devices, adb="adb": {})

    changes = lan_ips.refresh([], str(state), str(ssh), str(conf))

    assert changes == {"p7a": ("192.168.68.66", None), "s24": ("192.168.68.75", None)}
    assert sorted(json.loads(state.read_text())) == ["hd8"]  # a 19-day-old lease no longer overrides inventory


def test_rewrite_ssh_config_creates_missing_lan_alias_from_the_device_block():
    text = (
        "# header\n"
        "Host t2e 100.73.253.10\n"
        "  HostName 100.73.253.10\n"
        "  Port 8022\n"
        "  User u0_a1\n"
        "  IdentityFile ~/.ssh/termux_key\n"
        "Host t2e-firerpa\n"
        "  HostName 100.73.253.10\n"
        "  Port 65000\n"
    )
    out = lan_ips.rewrite_ssh_config(text, {"t2e": "192.168.68.58", "ghost": "192.168.68.99"})
    assert out.endswith(
        "Host t2e-lan\n  HostName 192.168.68.58\n  HostKeyAlias t2e\n"
        "  Port 8022\n  User u0_a1\n  IdentityFile ~/.ssh/termux_key\n  StrictHostKeyChecking yes\n"
    )
    assert "ghost" not in out  # no device block to clone: nothing invented
    assert out.count("Host t2e-firerpa\n  HostName 100.73.253.10\n  Port 65000\n") == 1
    # Idempotent, and a later address change only rewrites the new block.
    assert lan_ips.rewrite_ssh_config(out, {"t2e": "192.168.68.58"}) == out
    assert "HostName 192.168.68.61\n  HostKeyAlias t2e" in lan_ips.rewrite_ssh_config(out, {"t2e": "192.168.68.61"})


def test_devices_from_env_parses_inventory_pairs():
    assert lan_ips.devices_from_env("s24=100.123.218.30 t2e=100.73.253.10 junk =x y=") == [
        ("s24", "100.123.218.30"),
        ("t2e", "100.73.253.10"),
    ]


# --- M1 (adversary): one address, one device; ssh -lan keys pinned per device ---

_LIVE = {"ip": "192.168.1.157", "source": "adb"}


def _entry(ip, seen, source="adb"):
    return {"ip": ip, "source": source, "seen": seen}


def test_dedupe_keeps_the_most_recent_claim_to_an_address():
    state = {
        "hd8": _entry("192.168.1.157", _ago(hours=3)),
        "m11": _entry("192.168.1.157", _ago(minutes=1)),
        "t2e": _entry("192.168.68.62", _ago(minutes=1)),
    }
    assert lan_ips.dedupe_state(state) == {"hd8": "192.168.1.157"}
    assert set(state) == {"m11", "t2e"}


def test_dedupe_tie_prefers_the_adb_reading_then_the_name():
    seen = _ago(minutes=1)
    state = {"a": _entry("10.0.0.5", seen, "tailscale"), "b": _entry("10.0.0.5", seen, "adb")}
    assert lan_ips.dedupe_state(state) == {"a": "10.0.0.5"}
    state = {"a": _entry("10.0.0.5", seen), "b": _entry("10.0.0.5", seen)}
    lan_ips.dedupe_state(state)
    assert list(state) == ["b"]


def test_ssh_config_tombstones_a_lan_block_whose_address_another_device_holds():
    text = (
        "Host hd8 100.124.55.39\n  HostName 100.124.55.39\n  Port 8022\n"
        "Host hd8-lan\n  HostName 192.168.1.157\n  HostKeyAlias hd8\n  Port 8022\n  StrictHostKeyChecking yes\n"
        "Host m11-lan\n  HostName 192.168.1.150\n  HostKeyAlias m11\n  Port 8022\n  StrictHostKeyChecking yes\n"
        "Host t2e-firerpa\n  HostName 100.73.253.10\n"
    )
    out = lan_ips.rewrite_ssh_config(text, {"m11": "192.168.1.157"})
    assert "HostName 192.168.1.157\n  HostKeyAlias hd8" not in out  # hd8 no longer claims it
    assert "\n".join(lan_ips.tombstone_lines("hd8")) + "\n" in out
    assert "Host hd8 100.124.55.39" in out and "Host t2e-firerpa" in out
    assert "Host m11-lan\n  HostName 192.168.1.157\n" in out
    # A device nobody else holds keeps its (unconfirmed) block.
    kept = lan_ips.rewrite_ssh_config(text, {"m11": "192.168.1.158"})
    assert "Host hd8-lan" in kept


def test_ssh_config_forces_strict_host_key_checking_on_every_lan_block_once():
    text = (
        "Host t2e-lan\n  HostName 192.168.68.63\n  HostKeyAlias t2e\n  StrictHostKeyChecking accept-new\n  Port 8022\n"
        "Host s24-lan\n  HostName 192.168.68.54\n  Port 8022\n"
        "Host s24 100.1.1.1\n  HostName 100.1.1.1\n  StrictHostKeyChecking accept-new\n"
    )
    out = lan_ips.rewrite_ssh_config(text, {})
    for name in ("t2e", "s24"):
        block = out.split("Host %s-lan\n" % name)[1].split("Host ")[0]
        assert block.count("StrictHostKeyChecking") == 1 and "StrictHostKeyChecking yes" in block
        assert "HostKeyAlias %s" % name in block
    assert "Host s24 100.1.1.1\n  HostName 100.1.1.1\n  StrictHostKeyChecking accept-new\n" in out
    assert lan_ips.rewrite_ssh_config(out, {}) == out  # idempotent


def test_devices_conf_blanks_an_address_another_device_holds():
    conf = (
        "hd8 GN43 100.124.55.39 192.168.1.157 Kindle -\n"
        "m11 HA2PMV18 100.1.1.2 192.168.1.150 Lenovo -\n"
        "t2e TITAN 100.73.253.10 192.168.68.63 Titan -\n"
    )
    out = lan_ips.rewrite_devices_conf(conf, {"m11": "192.168.1.157", "t2e": "192.168.68.62"})
    assert "hd8 GN43 100.124.55.39 - Kindle -\n" in out
    assert "m11 HA2PMV18 100.1.1.2 192.168.1.157 Lenovo -\n" in out
    assert "t2e TITAN 100.73.253.10 192.168.68.62 Titan -\n" in out


def test_refresh_evicts_the_older_claim_end_to_end(tmp_path, monkeypatch):
    state = tmp_path / "state" / "lan_ips.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"hd8": _entry("192.168.1.157", _ago(hours=2))}))
    ssh, conf, kh = tmp_path / "ssh", tmp_path / "devices.conf", tmp_path / "known_hosts"
    ssh.write_text("Host hd8-lan\n  HostName 192.168.1.157\n  HostKeyAlias hd8\n  Port 8022\n")
    conf.write_text("hd8 GN43 100.124.55.39 192.168.1.157 Kindle -\nm11 HA2PMV18 100.1.1.2 - Lenovo -\n")
    monkeypatch.setattr(lan_ips, "discover", lambda devices, adb="adb": {"m11": ("192.168.1.157", "adb")})
    changes = lan_ips.refresh(
        [("hd8", "100.124.55.39"), ("m11", "100.1.1.2")], str(state), str(ssh), str(conf), known_hosts_path=str(kh)
    )
    assert changes["hd8"] == ("192.168.1.157", None)
    assert "hd8" not in json.loads(state.read_text())
    assert lan_ips.TOMBSTONE_MARK in ssh.read_text() and "192.168.1.157\n  HostKeyAlias hd8" not in ssh.read_text()
    assert "hd8 GN43 100.124.55.39 - Kindle -" in conf.read_text()
    assert "m11 HA2PMV18 100.1.1.2 192.168.1.157 Lenovo -" in conf.read_text()


def test_templates_skip_an_inventory_fallback_another_device_holds():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(REPO / "ansible/roles/control_node/templates")))
    ctx = {
        "groups": {"stayturgid": ["hd8", "m11"]},
        "hostvars": {
            "hd8": {"ansible_host": "100.124.55.39", "device_lan_ip": "192.168.1.157"},
            "m11": {"ansible_host": "100.1.1.2", "device_lan_ip": "192.168.1.150"},
        },
        "stayturgid_ssh_identity_files": ["/k"],
        "stayturgid_firerpa_certificate_path": "/k",
        "stayturgid_live_lan_ips": {"m11": {"ip": "192.168.1.157"}},
    }
    ssh = env.get_template("ssh_config_stayturgid.j2").render(**ctx)
    assert "\n".join(lan_ips.tombstone_lines("hd8")) + "\n" in ssh  # a tombstone, not hd8's old address
    assert "HostName 192.168.1.157\n  HostKeyAlias hd8" not in ssh
    assert "Host m11-lan\n" in ssh and "HostName 192.168.1.157" in ssh
    conf = env.get_template("devices.conf.j2").render(**ctx)
    assert "hd8 - 100.124.55.39 - hd8 -" in conf
    assert "m11 - 100.1.1.2 192.168.1.157 m11 -" in conf
    # No live entry anywhere: the inventory value still applies.
    ctx["stayturgid_live_lan_ips"] = {}
    assert "HostKeyAlias hd8" in env.get_template("ssh_config_stayturgid.j2").render(**ctx)


def test_template_lan_blocks_are_strict_but_tailscale_blocks_still_accept_new():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(REPO / "ansible/roles/control_node/templates")))
    ssh = env.get_template("ssh_config_stayturgid.j2").render(
        groups={"stayturgid": ["t2e"]},
        hostvars={"t2e": {"ansible_host": "100.73.253.10", "device_lan_ip": "192.168.68.62"}},
        stayturgid_ssh_identity_files=["/k"],
        stayturgid_firerpa_certificate_path="/k",
        stayturgid_live_lan_ips={},
    )
    lan = ssh.split("Host t2e-lan\n")[1].split("Host ")[0]
    assert "StrictHostKeyChecking yes" in lan and "accept-new" not in lan and "HostKeyAlias t2e" in lan
    assert "StrictHostKeyChecking accept-new" in ssh.split("Host t2e-lan")[0]


_KEY_A = "AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
_KEY_B = "AAAAC3NzaC1lZDI1NTE5AAAAIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
_FRAG = "Host hd8 100.124.55.39\n  HostName 100.124.55.39\n  Port 8022\nHost hd8-lan\n  HostName 192.168.1.50\n  HostKeyAlias hd8\n"


def test_pin_known_hosts_copies_the_tailscale_key_to_the_alias(tmp_path):
    kh = tmp_path / "known_hosts"
    kh.write_text("@cert-authority * ssh-ed25519 CAKEY stayturgid-ca\n[100.124.55.39]:8022 ssh-ed25519 %s\n" % _KEY_A)
    kh.chmod(0o640)
    said = []
    assert lan_ips.pin_known_hosts(_FRAG, str(kh), report=said.append) == ["hd8"]
    text = kh.read_text()
    assert "hd8 ssh-ed25519 %s\n" % _KEY_A in text
    assert "@cert-authority * ssh-ed25519 CAKEY stayturgid-ca" in text
    assert kh.stat().st_mode & 0o777 == 0o640 and said
    # Already pinned: nothing changes.
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == []
    assert kh.read_text() == text


def _hashed(name: str, ktype: str, key: str) -> str:
    salt = b"0123456789abcdefghij"
    mac = hmac.new(salt, name.encode(), hashlib.sha1).digest()
    return "|1|%s|%s %s %s" % (base64.b64encode(salt).decode(), base64.b64encode(mac).decode(), ktype, key)


def test_pin_known_hosts_makes_the_alias_hold_exactly_the_trusted_keys(tmp_path):
    kh = tmp_path / "known_hosts"
    kh.write_text(
        "\n".join(
            [
                "@cert-authority * ssh-ed25519 CAKEY stayturgid-ca",
                "hd8 ssh-ed25519 %s" % _KEY_B,  # another phone's key, same type
                "hd8 ssh-ed25519 %s" % _KEY_A,  # a duplicate next to the right one
                "hd8 ecdsa-sha2-nistp256 %s" % _KEY_B,  # another key type nobody scanned
                _hashed("hd8", "ssh-ed25519", _KEY_B),  # accept-new under HashKnownHosts
                _hashed("t2e", "ssh-ed25519", _KEY_B),  # someone else's hashed line stays
                "hd8,otherhost ssh-ed25519 %s" % _KEY_B,  # list entry: only the alias goes
                "[100.124.55.39]:8022 ssh-ed25519 %s" % _KEY_A,
                "unrelated ssh-ed25519 %s" % _KEY_B,
            ]
        )
        + "\n"
    )
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == ["hd8"]
    lines = kh.read_text().splitlines()
    assert [ln for ln in lines if ln.split()[0] == "hd8"] == ["hd8 ssh-ed25519 %s" % _KEY_A]
    assert not any("ecdsa" in ln for ln in lines)
    assert _hashed("hd8", "ssh-ed25519", _KEY_B) not in lines
    assert _hashed("t2e", "ssh-ed25519", _KEY_B) in lines
    assert "otherhost ssh-ed25519 %s" % _KEY_B in lines
    assert "@cert-authority * ssh-ed25519 CAKEY stayturgid-ca" in lines
    assert "[100.124.55.39]:8022 ssh-ed25519 %s" % _KEY_A in lines
    assert "unrelated ssh-ed25519 %s" % _KEY_B in lines
    again = kh.read_text()
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == [] and kh.read_text() == again


def test_pin_known_hosts_removes_alias_entries_it_cannot_confirm(tmp_path):
    kh = tmp_path / "known_hosts"
    kh.write_text("somewhere-else ssh-ed25519 %s\nhd8 ssh-ed25519 %s\n" % (_KEY_A, _KEY_B))
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == ["hd8"]  # no Tailscale entry: fail closed
    assert kh.read_text() == "somewhere-else ssh-ed25519 %s\n" % _KEY_A
    assert lan_ips.pin_known_hosts(_FRAG, str(tmp_path / "missing")) == []
    # A device without a Host block keeps its alias lines (nothing says what is trusted).
    kh.write_text("ghost ssh-ed25519 %s\n" % _KEY_B)
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == [] and "ghost" in kh.read_text()


def test_pin_known_hosts_keeps_a_symlinked_known_hosts_a_symlink(tmp_path):
    real = tmp_path / "dotfiles_known_hosts"
    real.write_text("[100.124.55.39]:8022 ssh-ed25519 %s\n" % _KEY_A)
    link = tmp_path / "known_hosts"
    link.symlink_to(real)
    assert lan_ips.pin_known_hosts(_FRAG, str(link)) == ["hd8"]
    assert link.is_symlink() and "hd8 ssh-ed25519 %s" % _KEY_A in real.read_text()


def test_ssh_config_rewrite_handles_equals_and_lowercase_keywords():
    text = "Host t2e-lan\n  hostname=192.168.68.63\n  stricthostkeychecking=accept-new\n  Port 8022\n"
    out = lan_ips.rewrite_ssh_config(text, {"t2e": "192.168.68.62"})
    block = out.split("Host t2e-lan\n")[1].lower()
    assert "192.168.68.62" in block and "accept-new" not in block and "stricthostkeychecking yes" in block
    assert "192.168.68.63" not in out and "HostKeyAlias t2e" in out


def _agents_tasks() -> list[dict]:
    return yaml.safe_load((REPO / "ansible/roles/control_node/tasks/agents.yml").read_text())


def test_deploy_pins_the_alias_with_one_idempotent_atomic_task_after_the_tailscale_trust():
    tasks = _agents_tasks()
    names = [t.get("name", "") for t in tasks]
    pin = next(t for t in tasks if t.get("name", "").startswith("Pin fleet SSH host keys under each device alias"))
    assert names.index("Trust fleet SSH host keys on Mac (ansible.builtin.known_hosts)") < names.index(pin["name"])
    # No drop-then-add pair: that reported changed on every deploy and left the alias empty in between.
    assert not any(n.startswith("Drop every known_hosts line") for n in names)
    argv = pin["ansible.builtin.command"]["argv"]
    assert argv[argv.index("pin-known-hosts") - 1].endswith("control/lib/lan_ips.py")
    assert "--ssh-config" in argv and "--known-hosts" in argv
    # Changed only when the helper printed an alias it rewrote.
    assert "stdout" in pin["changed_when"] and "length > 0" in pin["changed_when"]


def test_pin_known_hosts_cli_prints_changed_aliases_once_then_nothing(tmp_path, capsys):
    ssh, kh = tmp_path / "frag", tmp_path / "known_hosts"
    ssh.write_text(_FRAG)
    kh.write_text("[100.124.55.39]:8022 ssh-ed25519 %s\nhd8 ssh-ed25519 %s\n" % (_KEY_A, _KEY_B))
    argv = ["--ssh-config", str(ssh), "--known-hosts", str(kh)]
    assert lan_ips._pin_known_hosts_cli(argv) == 0
    assert capsys.readouterr().out.split() == ["hd8"]
    assert kh.read_text().splitlines() == [
        "[100.124.55.39]:8022 ssh-ed25519 %s" % _KEY_A,
        "hd8 ssh-ed25519 %s" % _KEY_A,
    ]
    before = kh.stat().st_ino
    assert lan_ips._pin_known_hosts_cli(argv) == 0
    assert capsys.readouterr().out == "" and kh.stat().st_ino == before  # unchanged: not even rewritten
    assert lan_ips._pin_known_hosts_cli(["--bogus"]) == 2


def test_pin_known_hosts_swaps_the_file_in_one_step_so_the_alias_is_never_empty(tmp_path, monkeypatch):
    kh = tmp_path / "known_hosts"
    kh.write_text("[100.124.55.39]:8022 ssh-ed25519 %s\nhd8 ssh-ed25519 %s\n" % (_KEY_A, _KEY_B))
    seen = {}
    real_replace = lan_ips.os.replace

    def replace(src, dst):
        seen["before"] = Path(dst).read_text()  # the old, complete file is still in place...
        seen["staged"] = Path(src).read_text()  # ...and the new one is complete before the rename
        real_replace(src, dst)

    monkeypatch.setattr(lan_ips.os, "replace", replace)
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == ["hd8"]
    assert "hd8 ssh-ed25519 %s" % _KEY_B in seen["before"]
    assert "hd8 ssh-ed25519 %s" % _KEY_A in seen["staged"] and "ssh-ed25519 %s" % _KEY_B not in seen["staged"]


def test_refresh_pins_the_alias_end_to_end_and_never_uses_the_real_known_hosts(tmp_path, monkeypatch):
    assert lan_ips.KNOWN_HOSTS == str(tmp_path / "known_hosts")  # conftest redirect
    state = tmp_path / "state" / "lan_ips.json"
    state.parent.mkdir()
    ssh, conf, kh = tmp_path / "ssh", tmp_path / "devices.conf", tmp_path / "kh"
    ssh.write_text(_FRAG)
    conf.write_text("hd8 GN43 100.124.55.39 192.168.1.50 Kindle -\n")
    kh.write_text("[100.124.55.39]:8022 ssh-ed25519 %s\nhd8 ssh-ed25519 %s\n" % (_KEY_A, _KEY_B))
    monkeypatch.setattr(lan_ips, "discover", lambda devices, adb="adb": {"hd8": ("192.168.1.50", "adb")})
    said = []
    lan_ips.refresh(
        [("hd8", "100.124.55.39")], str(state), str(ssh), str(conf), known_hosts_path=str(kh), report=said.append
    )
    assert kh.read_text().splitlines() == [
        "[100.124.55.39]:8022 ssh-ed25519 %s" % _KEY_A,
        "hd8 ssh-ed25519 %s" % _KEY_A,
    ]
    assert said and not (tmp_path / "known_hosts").exists()


def test_pin_known_hosts_also_removes_indented_uppercase_and_wildcard_alias_lines(tmp_path):
    kh = tmp_path / "known_hosts"
    kh.write_text(
        "[100.124.55.39]:8022 ssh-ed25519 %s\n  hd8 ssh-ed25519 %s\nHD8 ssh-ed25519 %s\nhd? ssh-ed25519 %s\n"
        "hd*,other ssh-ed25519 %s\nm11 ssh-ed25519 %s\n" % (_KEY_A, _KEY_B, _KEY_B, _KEY_B, _KEY_B, _KEY_B)
    )
    frag = _FRAG.replace("Port 8022", "port=8022")
    assert lan_ips.pin_known_hosts(frag, str(kh)) == ["hd8"]
    lines = kh.read_text().splitlines()
    assert "hd8 ssh-ed25519 %s" % _KEY_A in lines and "m11 ssh-ed25519 %s" % _KEY_B in lines
    assert "other ssh-ed25519 %s" % _KEY_B in lines
    assert not any(ln.split()[0].lower() in ("hd8", "hd?") for ln in lines if "ssh-ed25519 %s" % _KEY_B in ln)
    assert len(lines) == 4  # SRC, other, m11, pinned alias


def test_tombstone_is_idempotent_and_replaced_by_a_real_block_when_an_address_returns():
    text = "Host hd8 100.124.55.39\n  HostName 100.124.55.39\n  Port 8022\n"
    dead = lan_ips.rewrite_ssh_config(text, {})  # a device with no -lan block and no address
    assert "\n".join(lan_ips.tombstone_lines("hd8")) + "\n" in dead
    assert lan_ips.rewrite_ssh_config(dead, {}) == dead
    live = lan_ips.rewrite_ssh_config(dead, {"hd8": "192.168.1.50"})
    assert lan_ips.TOMBSTONE_MARK not in live and ".invalid" not in live
    assert "Host hd8-lan\n  HostName 192.168.1.50\n" in live and "StrictHostKeyChecking yes" in live
    assert lan_ips.rewrite_ssh_config(live, {"hd8": "192.168.1.50"}) == live
    back = lan_ips.rewrite_ssh_config(live, {})  # its address is now unknown but not held by anyone: keep the block
    assert "Host hd8-lan\n  HostName 192.168.1.50\n" in back and lan_ips.TOMBSTONE_MARK not in back


def test_tombstone_leaves_devices_with_an_address_and_non_device_blocks_alone():
    text = (
        "Host s24 100.1.1.1\n  HostName 100.1.1.1\n"
        "Host s24-firerpa\n  HostName 100.1.1.1\n"
        "Host vps-primary\n  HostName example.org\n"
    )
    out = lan_ips.rewrite_ssh_config(text, {"s24": "192.168.68.9"})
    assert lan_ips.TOMBSTONE_MARK not in out and "Host s24-lan\n  HostName 192.168.68.9\n" in out
    assert "vps-primary-lan" not in out and "firerpa-lan" not in out


def test_tombstone_block_fails_loudly_and_beats_a_catch_all_block(tmp_path):
    import shutil
    import subprocess

    ssh = shutil.which("ssh")
    if not ssh:
        return
    cfg = tmp_path / "config"
    cfg.write_text(
        "Host hd8 100.124.55.39\n  HostName 100.124.55.39\n"
        + "\n".join(lan_ips.tombstone_lines("hd8"))
        + "\nHost *\n  ProxyCommand /bin/false\n  HostName catch-all.example\n"
        + "  CanonicalizeHostname yes\n  CanonicalDomains example.org\n"
    )
    eff = subprocess.run([ssh, "-G", "-F", str(cfg), "hd8-lan"], capture_output=True, text=True, timeout=20)
    assert eff.returncode == 0, eff.stderr
    got = dict(ln.split(" ", 1) for ln in eff.stdout.splitlines() if " " in ln)
    assert got["hostname"] == "hd8-no-usable-lan-address.invalid."  # never the catch-all's name; absolute
    assert got["canonicalizehostname"] == "false"
    assert "proxycommand" not in got  # `ProxyCommand none` wins over the catch-all's /bin/false
    run = subprocess.run(
        [ssh, "-F", str(cfg), "-o", "BatchMode=yes", "-o", "ConnectTimeout=3", "hd8-lan", "true"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode != 0 and "hd8-no-usable-lan-address.invalid." in run.stderr
