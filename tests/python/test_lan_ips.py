"""Live LAN-IP discovery (control/lib/lan_ips.py) and the templates that use it."""

from __future__ import annotations

import datetime
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


def test_template_omits_lan_alias_when_inventory_lan_ip_is_a_dash():
    hostvars = {"t2e": {"ansible_host": "100.73.253.10", "device_lan_ip": "-", "device_usb_serial": "T"}}
    ctx = dict(
        groups={"stayturgid": ["t2e"]},
        hostvars=hostvars,
        stayturgid_ssh_identity_files=[],
        stayturgid_firerpa_certificate_path="/k",
        stayturgid_live_lan_ips={},
    )
    assert "t2e-lan" not in _render("ssh_config_stayturgid.j2", **ctx)


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


def test_ssh_config_drops_a_lan_block_whose_address_another_device_holds():
    text = (
        "Host hd8 100.124.55.39\n  HostName 100.124.55.39\n  Port 8022\n"
        "Host hd8-lan\n  HostName 192.168.1.157\n  HostKeyAlias hd8\n  Port 8022\n  StrictHostKeyChecking yes\n"
        "Host m11-lan\n  HostName 192.168.1.150\n  HostKeyAlias m11\n  Port 8022\n  StrictHostKeyChecking yes\n"
        "Host t2e-firerpa\n  HostName 100.73.253.10\n"
    )
    out = lan_ips.rewrite_ssh_config(text, {"m11": "192.168.1.157"})
    assert "Host hd8-lan" not in out
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
    assert "Host hd8-lan" not in ssh.read_text()
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
    assert "Host hd8-lan" not in ssh
    assert "Host m11-lan\n" in ssh and "HostName 192.168.1.157" in ssh
    conf = env.get_template("devices.conf.j2").render(**ctx)
    assert "hd8 - 100.124.55.39 - hd8 -" in conf
    assert "m11 - 100.1.1.2 192.168.1.157 m11 -" in conf
    # No live entry anywhere: the inventory value still applies.
    ctx["stayturgid_live_lan_ips"] = {}
    assert "Host hd8-lan" in env.get_template("ssh_config_stayturgid.j2").render(**ctx)


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


def test_pin_known_hosts_replaces_a_different_alias_key_and_ignores_unknown_hosts(tmp_path):
    kh = tmp_path / "known_hosts"
    kh.write_text(
        "hd8 ssh-ed25519 %s\n[100.124.55.39]:8022 ssh-ed25519 %s\n|1|abc|def ssh-ed25519 %s\n"
        % (_KEY_B, _KEY_A, _KEY_B)
    )
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == ["hd8"]
    lines = kh.read_text().splitlines()
    assert "hd8 ssh-ed25519 %s" % _KEY_A in lines and "hd8 ssh-ed25519 %s" % _KEY_B not in lines
    assert any(ln.startswith("|1|abc|def") for ln in lines)
    # No Tailscale entry to copy from: the alias stays as it is (the strict check then fails closed).
    kh.write_text("somewhere-else ssh-ed25519 %s\n" % _KEY_A)
    assert lan_ips.pin_known_hosts(_FRAG, str(kh)) == []
    assert lan_ips.pin_known_hosts(_FRAG, str(tmp_path / "missing")) == []


def test_deploy_pins_the_alias_key_from_the_tailscale_scan():
    tasks = yaml.safe_load((REPO / "ansible/roles/control_node/tasks/agents.yml").read_text())
    names = [t.get("name", "") for t in tasks]
    pin = next(t for t in tasks if t.get("name", "").startswith("Pin fleet SSH host keys under each device alias"))
    assert names.index("Trust fleet SSH host keys on Mac (ansible.builtin.known_hosts)") < names.index(pin["name"])
    args = pin["ansible.builtin.known_hosts"]
    assert args["name"] == "{{ item.item }}" and args["state"] == "present"
    assert "regex_replace" in args["key"]
