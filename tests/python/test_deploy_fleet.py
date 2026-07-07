"""Unit tests for mac/deploy_fleet.py — argv building and inventory parsing."""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mac"))
import deploy_fleet as df  # noqa: E402


INVENTORY_JSON = {
    "stayturgid": {
        "hosts": {"s24": {}, "hd8": {}, "p7a": {}},
    }
}


def test_parse_inventory_hosts():
    assert df.parse_inventory_hosts(INVENTORY_JSON) == ["s24", "hd8", "p7a"]


def test_build_playbook_argv_full():
    cmd = df.build_playbook_argv(limit=["s24", "hd8"], check=False, tags=None)
    assert cmd == [
        "ansible-playbook",
        str(df.FLEET_PLAYBOOK),
        "--limit",
        "s24,hd8",
    ]


def test_build_playbook_argv_check_and_tags():
    cmd = df.build_playbook_argv(limit=["s24"], check=True, tags="app-stores")
    assert cmd == [
        "ansible-playbook",
        str(df.FLEET_PLAYBOOK),
        "--limit",
        "s24",
        "--check",
        "--diff",
        "--tags",
        "app-stores",
    ]


def test_check_mode_env(monkeypatch):
    monkeypatch.delenv("CHECK", raising=False)
    assert df.check_mode(False) is False
    monkeypatch.setenv("CHECK", "1")
    assert df.check_mode(False) is True
    assert df.check_mode(True) is True


def test_scope_ansible_tags():
    assert df.Scope.FULL.ansible_tags is None
    assert df.Scope.FDROID.ansible_tags == "fdroid"
    assert df.Scope.PLAY.ansible_tags == "play"
    assert df.Scope.APP_STORES.ansible_tags == "app-stores"


def test_resolve_hosts_explicit():
    assert df.resolve_hosts(["s24"]) == ["s24"]


def test_resolve_hosts_from_inventory(monkeypatch):
    monkeypatch.setattr(df, "inventory_hosts", lambda group="stayturgid": ["s24", "p7a"])
    assert df.resolve_hosts([]) == ["s24", "p7a"]
