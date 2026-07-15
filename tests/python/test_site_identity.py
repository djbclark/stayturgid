"""Unit tests for control/lib/site_identity.py.

All tests use synthetic ansible-inventory JSON payloads injected via
``monkeypatch``; no real ``ansible-inventory`` binary is needed.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
import site_identity as si

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_GOOD_INVENTORY = {
    "stayturgid": {
        "hosts": ["s24", "p7a", "hd8"],
    },
    "_meta": {
        "hostvars": {
            "s24": {
                "ansible_host": "100.123.218.30",
                "ansible_port": 8022,
                "ansible_user": "mobile",
                "device_usb_serial": "RFCX219CHKA",
                "device_lan_ip": "192.168.68.60",
                "device_label": "Samsung S24",
                "stayturgid_automation_mode": "full",
                "stayturgid_mac_peer": {
                    "user": "djbclark",
                    "lan": "192.168.68.1",
                    "tailscale": "100.100.100.1",
                },
                "stayturgid_control_ssh_user": "djbclark",
                "stayturgid_hermes_telegram_allowed_users": "alice,bob",
                "stayturgid_hermes_telegram_home_channel": "-1001234567890",
            },
            "p7a": {
                "ansible_host": "100.65.230.108",
                "ansible_port": 8022,
                "ansible_user": "mobile",
                "device_usb_serial": "35261JEHN12374",
                "device_lan_ip": "192.168.68.65",
                "device_label": "Pixel 7a",
                "stayturgid_automation_mode": "full",
                "stayturgid_mac_peer": {
                    "user": "djbclark",
                    "lan": "192.168.68.1",
                    "tailscale": "100.100.100.1",
                },
                "stayturgid_control_ssh_user": "djbclark",
                "stayturgid_hermes_telegram_allowed_users": "alice,bob",
                "stayturgid_hermes_telegram_home_channel": "-1001234567890",
            },
            "hd8": {
                "ansible_host": "100.124.55.39",
                "ansible_port": 2222,
                "ansible_user": "mobile",
                "device_usb_serial": "GN43T503430603PS",
                "device_lan_ip": "192.168.1.157",
                "device_label": "Fire HD 8",
                "stayturgid_automation_mode": "screen",
                "stayturgid_mac_peer": {
                    "user": "djbclark",
                    "lan": "192.168.68.1",
                    "tailscale": "100.100.100.1",
                },
                "stayturgid_control_ssh_user": "djbclark",
                "stayturgid_hermes_telegram_allowed_users": "alice,bob",
                "stayturgid_hermes_telegram_home_channel": "-1001234567890",
            },
        }
    },
}


def _make_run_result(data: dict, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=json.dumps(data),
        stderr="",
    )


@pytest.fixture()
def fake_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch subprocess.run to return _GOOD_INVENTORY; return a dummy hosts.yml path."""
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: _make_run_result(_GOOD_INVENTORY),
    )
    # Disable on-disk caching so tests stay isolated
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    return hosts_yml


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_site_has_three_devices(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    assert set(site.devices.keys()) == {"s24", "p7a", "hd8"}


def test_device_fields_correct(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    s24 = site.devices["s24"]
    assert s24.alias == "s24"
    assert s24.ansible_host == "100.123.218.30"
    assert s24.device_usb_serial == "RFCX219CHKA"
    assert s24.device_lan_ip == "192.168.68.60"
    assert s24.ansible_port == 8022
    assert s24.ansible_user == "mobile"
    assert s24.stayturgid_automation_mode == "full"


def test_control_node_parsed(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    cn = site.control_node
    assert cn.ssh_user == "djbclark"
    assert cn.lan_ip == "192.168.68.1"
    assert cn.tailscale_ip == "100.100.100.1"


def test_telegram_users_tuple(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    assert "alice" in site.telegram_allowed_users
    assert "bob" in site.telegram_allowed_users


def test_telegram_home_channel(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    assert site.telegram_home_channel == "-1001234567890"


def test_device_order_deterministic(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    assert site.device_order() == sorted(site.devices.keys())


def test_optional_usb_serial_dash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """device_usb_serial missing → stored as '-'."""
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    del data["_meta"]["hostvars"]["hd8"]["device_usb_serial"]
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    site = si.load_site_identity(inventory_path=hosts_yml)
    assert site.devices["hd8"].device_usb_serial == "-"


def test_optional_lan_ip_dash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """device_lan_ip missing → stored as '-'."""
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    del data["_meta"]["hostvars"]["hd8"]["device_lan_ip"]
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    site = si.load_site_identity(inventory_path=hosts_yml)
    assert site.devices["hd8"].device_lan_ip == "-"


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------


def test_cache_written_and_read(fake_inventory: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / ".identity_cache.json"
    monkeypatch.setattr(si, "_CACHE_FILE", cache_path)
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)

    site_a = si.load_site_identity(inventory_path=fake_inventory)
    assert cache_path.is_file()

    # Make cache appear newer than inventory file
    future = time.time() + 9999
    import os

    os.utime(cache_path, (future, future))

    call_count = {"n": 0}

    def never_called(*_a, **_kw):
        call_count["n"] += 1
        return _make_run_result(_GOOD_INVENTORY)

    monkeypatch.setattr(subprocess, "run", never_called)
    site_b = si.load_site_identity(inventory_path=fake_inventory)

    assert call_count["n"] == 0, "subprocess.run should not be called when cache is fresh"
    assert site_b.devices.keys() == site_a.devices.keys()


def test_cache_stale_when_inventory_newer(
    fake_inventory: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / ".identity_cache.json"
    monkeypatch.setattr(si, "_CACHE_FILE", cache_path)
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)

    # First load populates the cache
    si.load_site_identity(inventory_path=fake_inventory)

    # Touch the inventory to make it newer than the cache
    import os

    future = time.time() + 9999
    os.utime(fake_inventory, (future, future))

    call_count = {"n": 0}

    def counting_run(*_a, **_kw):
        call_count["n"] += 1
        return _make_run_result(_GOOD_INVENTORY)

    monkeypatch.setattr(subprocess, "run", counting_run)
    si.load_site_identity(inventory_path=fake_inventory)
    assert call_count["n"] == 1, "subprocess.run should be called when cache is stale"


def test_force_refresh_bypasses_cache(fake_inventory: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / ".identity_cache.json"
    monkeypatch.setattr(si, "_CACHE_FILE", cache_path)
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)

    si.load_site_identity(inventory_path=fake_inventory)

    call_count = {"n": 0}

    def counting_run(*_a, **_kw):
        call_count["n"] += 1
        return _make_run_result(_GOOD_INVENTORY)

    monkeypatch.setattr(subprocess, "run", counting_run)
    si.load_site_identity(inventory_path=fake_inventory, force_refresh=True)
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# Error-path / validation tests
# ---------------------------------------------------------------------------


def test_missing_inventory_file() -> None:
    with pytest.raises(FileNotFoundError, match="Authoritative inventory not found"):
        si.load_site_identity(inventory_path=Path("/nonexistent/hosts.yml"))


def test_ansible_inventory_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: subprocess.CompletedProcess([], 1, "", "fatal error"),
    )
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="ansible-inventory failed"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_invalid_json_from_ansible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_kw: subprocess.CompletedProcess([], 0, "NOT JSON", ""),
    )
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="Could not parse"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_missing_stayturgid_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = {"_meta": {"hostvars": {}}}
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="missing a 'stayturgid' group"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_duplicate_usb_serial_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    data["_meta"]["hostvars"]["p7a"]["device_usb_serial"] = "RFCX219CHKA"  # same as s24
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="Duplicate device_usb_serial"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_duplicate_tailscale_ip_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    data["_meta"]["hostvars"]["p7a"]["ansible_host"] = "100.123.218.30"  # same as s24
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="Duplicate ansible_host"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_invalid_lan_ip_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    data["_meta"]["hostvars"]["s24"]["device_lan_ip"] = "not-an-ip"
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="invalid 'device_lan_ip'"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_missing_device_label_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    del data["_meta"]["hostvars"]["s24"]["device_label"]
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="missing required variable: 'device_label'"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_invalid_alias_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    data["stayturgid"]["hosts"] = ["BAD_HOST", "p7a", "hd8"]
    data["_meta"]["hostvars"]["BAD_HOST"] = data["_meta"]["hostvars"]["s24"]
    del data["_meta"]["hostvars"]["s24"]
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="Host alias 'BAD_HOST'"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_site_is_immutable(fake_inventory: Path) -> None:
    """Site and Device are frozen dataclasses — mutation must raise."""
    site = si.load_site_identity(inventory_path=fake_inventory)
    with pytest.raises((AttributeError, TypeError)):
        site.telegram_home_channel = "mutated"  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        site.devices["s24"].alias = "mutated"  # type: ignore[misc]
