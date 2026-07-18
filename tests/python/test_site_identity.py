"""Unit tests for control/lib/site_identity.py.

All tests use synthetic ansible-inventory JSON payloads injected via
``monkeypatch``; no real ``ansible-inventory`` binary is needed.
Fixtures use §4.1 example aliases and RFC 5737 addresses only.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
import site_identity as si

# ---------------------------------------------------------------------------
# Fixture helpers — generic example identity only
# ---------------------------------------------------------------------------

_GOOD_INVENTORY = {
    "stayturgid": {
        "hosts": ["oneui-device", "stock-android-device", "fireos-device"],
    },
    "_meta": {
        "hostvars": {
            "oneui-device": {
                "ansible_host": "100.0.0.11",
                "ansible_port": 8022,
                "ansible_user": "termux",
                "device_usb_serial": "EXAMPLE-SERIAL-ONEUI",
                "device_lan_ip": "192.0.2.11",
                "device_label": "Example One UI phone",
                "stayturgid_automation_mode": "full",
                "stayturgid_mac_peer": {
                    "user": "operator",
                    "lan": "192.0.2.1",
                    "tailscale": "100.0.0.1",
                },
                "stayturgid_control_ssh_user": "operator",
                "stayturgid_hermes_telegram_allowed_users": "alice,bob",
                "stayturgid_hermes_telegram_home_channel": "-1001234567890",
            },
            "stock-android-device": {
                "ansible_host": "100.0.0.12",
                "ansible_port": 8022,
                "ansible_user": "termux",
                "device_usb_serial": "EXAMPLE-SERIAL-STOCK",
                "device_lan_ip": "192.0.2.12",
                "device_label": "Example stock Android phone",
                "stayturgid_automation_mode": "full",
                "stayturgid_mac_peer": {
                    "user": "operator",
                    "lan": "192.0.2.1",
                    "tailscale": "100.0.0.1",
                },
                "stayturgid_control_ssh_user": "operator",
                "stayturgid_hermes_telegram_allowed_users": "alice,bob",
                "stayturgid_hermes_telegram_home_channel": "-1001234567890",
            },
            "fireos-device": {
                "ansible_host": "100.0.0.13",
                "ansible_port": 2222,
                "ansible_user": "termux",
                "device_usb_serial": "EXAMPLE-SERIAL-FIRE",
                "device_lan_ip": "192.0.2.13",
                "device_label": "Example Fire OS tablet",
                "stayturgid_automation_mode": "screen",
                "stayturgid_mac_peer": {
                    "user": "operator",
                    "lan": "192.0.2.1",
                    "tailscale": "100.0.0.1",
                },
                "stayturgid_control_ssh_user": "operator",
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
    assert set(site.devices.keys()) == {"oneui-device", "stock-android-device", "fireos-device"}


def test_device_fields_correct(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    oneui = site.devices["oneui-device"]
    assert oneui.alias == "oneui-device"
    assert oneui.ansible_host == "100.0.0.11"
    assert oneui.device_usb_serial == "EXAMPLE-SERIAL-ONEUI"
    assert oneui.device_lan_ip == "192.0.2.11"
    assert oneui.ansible_port == 8022
    assert oneui.ansible_user == "termux"
    assert oneui.stayturgid_automation_mode == "full"


def test_control_node_parsed(fake_inventory: Path) -> None:
    site = si.load_site_identity(inventory_path=fake_inventory)
    cn = site.control_node
    assert cn.ssh_user == "operator"
    assert cn.lan_ip == "192.0.2.1"
    assert cn.tailscale_ip == "100.0.0.1"


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
    del data["_meta"]["hostvars"]["fireos-device"]["device_usb_serial"]
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    site = si.load_site_identity(inventory_path=hosts_yml)
    assert site.devices["fireos-device"].device_usb_serial == "-"


def test_optional_lan_ip_dash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """device_lan_ip missing → stored as '-'."""
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    del data["_meta"]["hostvars"]["fireos-device"]["device_lan_ip"]
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    site = si.load_site_identity(inventory_path=hosts_yml)
    assert site.devices["fireos-device"].device_lan_ip == "-"


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


def test_cache_not_reused_for_different_inventory(
    fake_inventory: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache is keyed by inventory path — a different inventory must re-export."""
    cache_path = tmp_path / ".identity_cache.json"
    monkeypatch.setattr(si, "_CACHE_FILE", cache_path)
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)

    si.load_site_identity(inventory_path=fake_inventory)

    other = tmp_path / "other-hosts.yml"
    other.write_text("# other\n", encoding="utf-8")
    future = time.time() + 9999
    import os

    os.utime(cache_path, (future, future))

    call_count = {"n": 0}

    def counting_run(*_a, **_kw):
        call_count["n"] += 1
        return _make_run_result(_GOOD_INVENTORY)

    monkeypatch.setattr(subprocess, "run", counting_run)
    si.load_site_identity(inventory_path=other)
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# Context-aware resolution
# ---------------------------------------------------------------------------


def _write_ansible_cfg(root: Path, inventory_rel: str = "inventory/hosts.yml") -> Path:
    cfg = root / "ansible.cfg"
    cfg.write_text(
        f"[defaults]\ninventory = {inventory_rel}\ncollections_path = collections\n",
        encoding="utf-8",
    )
    return cfg


def test_resolve_inventory_explicit_ansible_config(tmp_path: Path) -> None:
    product = tmp_path / "product"
    (product / "ansible").mkdir(parents=True)
    _write_ansible_cfg(product / "ansible")
    explicit = tmp_path / "site"
    explicit.mkdir()
    _write_ansible_cfg(explicit, "inventory/live.yml")
    (explicit / "inventory").mkdir()
    inv = explicit / "inventory" / "live.yml"
    inv.write_text("all: {}\n", encoding="utf-8")

    resolved = si.resolve_inventory_path(
        repo_root=product,
        environ={"ANSIBLE_CONFIG": str(explicit / "ansible.cfg")},
    )
    assert resolved == inv.resolve()


def test_resolve_inventory_site_overlay_default(tmp_path: Path) -> None:
    product = tmp_path / "product"
    (product / "ansible").mkdir(parents=True)
    _write_ansible_cfg(product / "ansible")
    site = tmp_path / "site-overlay"
    site.mkdir()
    _write_ansible_cfg(site)
    (site / "inventory").mkdir()
    inv = site / "inventory" / "hosts.yml"
    inv.write_text("all: {}\n", encoding="utf-8")

    resolved = si.resolve_inventory_path(
        repo_root=product,
        environ={"STAYTURGID_SITE_DIR": str(site)},
    )
    assert resolved == inv.resolve()


def test_resolve_inventory_upstream_example_fallback(tmp_path: Path) -> None:
    product = tmp_path / "product"
    inv_dir = product / "ansible" / "inventory"
    inv_dir.mkdir(parents=True)
    _write_ansible_cfg(product / "ansible")
    example = inv_dir / "hosts.yml.example"
    example.write_text("all: {}\n", encoding="utf-8")
    # No live hosts.yml, no site overlay
    resolved = si.resolve_inventory_path(
        repo_root=product,
        environ={"STAYTURGID_SITE_DIR": str(tmp_path / "missing-site")},
    )
    assert resolved == example


def test_ansible_listable_path_materialises_example(tmp_path: Path) -> None:
    example = tmp_path / "hosts.yml.example"
    example.write_text("all:\n  children: {}\n", encoding="utf-8")
    listable = si._ansible_listable_path(example, tmp_dir=tmp_path / "mat")
    assert listable.name == "hosts.yml"
    assert listable.is_file()
    assert listable.read_text(encoding="utf-8") == example.read_text(encoding="utf-8")


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
    data["_meta"]["hostvars"]["stock-android-device"]["device_usb_serial"] = "EXAMPLE-SERIAL-ONEUI"
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="Duplicate device_usb_serial"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_duplicate_tailscale_ip_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    data["_meta"]["hostvars"]["stock-android-device"]["ansible_host"] = "100.0.0.11"
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="Duplicate ansible_host"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_invalid_lan_ip_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    data["_meta"]["hostvars"]["oneui-device"]["device_lan_ip"] = "not-an-ip"
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="invalid 'device_lan_ip'"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_missing_device_label_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    del data["_meta"]["hostvars"]["oneui-device"]["device_label"]
    hosts_yml = tmp_path / "hosts.yml"
    hosts_yml.write_text("# dummy\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: _make_run_result(data))
    monkeypatch.setattr(si, "_CACHE_FILE", tmp_path / ".identity_cache.json")
    monkeypatch.setattr(si, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError, match="missing required variable: 'device_label'"):
        si.load_site_identity(inventory_path=hosts_yml)


def test_invalid_alias_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(json.dumps(_GOOD_INVENTORY))
    data["stayturgid"]["hosts"] = ["BAD_HOST", "stock-android-device", "fireos-device"]
    data["_meta"]["hostvars"]["BAD_HOST"] = data["_meta"]["hostvars"]["oneui-device"]
    del data["_meta"]["hostvars"]["oneui-device"]
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
        site.devices["oneui-device"].alias = "mutated"  # type: ignore[misc]
