"""Regression coverage for inventory-backed offline target selection."""

from __future__ import annotations

from pathlib import Path

from control.lib import fleet_targets


def test_resolve_hosts_default_skips_offline(monkeypatch, capsys) -> None:
    data = {
        "stayturgid": {"hosts": {"s24": {}, "p7a": {}, "hd8": {}}},
        "_meta": {"hostvars": {"p7a": {"stayturgid_fleet_status": "offline"}}},
    }
    monkeypatch.setattr(fleet_targets, "inventory_list", lambda _root: data)

    assert fleet_targets.resolve_hosts([], repo_root=Path("."), command_name="cf-run") == ["s24", "hd8"]
    assert "cf-run: skipping offline host(s) p7a" in capsys.readouterr().err


def test_resolve_hosts_explicit_is_override(monkeypatch) -> None:
    monkeypatch.setattr(
        fleet_targets,
        "inventory_list",
        lambda _root: (_ for _ in ()).throw(AssertionError("explicit target must not load inventory")),
    )

    assert fleet_targets.resolve_hosts(["p7a"], repo_root=Path("."), command_name="rollout.py") == ["p7a"]
