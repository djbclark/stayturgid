"""Live LAN-IP discovery (control/lib/lan_ips.py) and the templates that use it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jinja2

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
    state.write_text(json.dumps({"hd8": {"ip": "192.168.1.157", "source": "adb", "seen": "x"}}))
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
