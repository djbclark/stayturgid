"""Tests for Termux repair's control-ET SSH config self-heal."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "device" / "termux" / "py" / "stayturgid_repair.py"
SPEC = importlib.util.spec_from_file_location("stayturgid_repair", MODULE_PATH)
assert SPEC and SPEC.loader
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


def _setup_repair_tree(tmp_path, monkeypatch, config_text):
    home = tmp_path / "home"
    stg = home / ".stayturgid"
    share = stg / "share"
    share.mkdir(parents=True)
    (share / "ssh-config-control-et").write_text(
        "Host mac\n    HostName 100.0.0.1\n    IdentityFile ~/.ssh/id_ed25519_fleet\n    IdentitiesOnly yes\n",
        encoding="utf-8",
    )
    conf = home / ".ssh" / "config"
    conf.parent.mkdir(parents=True)
    conf.write_text(config_text, encoding="utf-8")
    monkeypatch.setattr(repair, "HOME", str(home))
    monkeypatch.setattr(repair, "STG", str(stg))
    monkeypatch.setattr(repair, "log", lambda *_args, **_kwargs: None)
    return conf


def test_repair_removes_legacy_block_but_preserves_managed_config(tmp_path, monkeypatch):
    conf = _setup_repair_tree(
        tmp_path,
        monkeypatch,
        "# MacBook Air via Tailscale\n"
        "Host mac\n"
        "    HostName old.example\n"
        "    IdentityFile ~/.ssh/id_old\n"
        "    IdentitiesOnly yes\n"
        "# BEGIN STAYTURGID-CONTROL-ET\n"
        "Host mac\n    IdentityFile ~/.ssh/id_ed25519_fleet\n"
        "# END STAYTURGID-CONTROL-ET\n"
        "Host unrelated\n    User preserve\n",
    )

    assert repair.ensure_control_et_ssh_config() == "repaired"
    text = conf.read_text(encoding="utf-8")
    assert "MacBook Air via Tailscale" not in text
    assert "id_old" not in text
    assert "STAYTURGID-CONTROL-ET" in text
    assert "User preserve" in text


def test_repair_cleans_legacy_block_before_restoring_marked_block(tmp_path, monkeypatch):
    conf = _setup_repair_tree(
        tmp_path,
        monkeypatch,
        "# MacBook Air via Tailscale\n"
        "Host mac\n"
        "    HostName old.example\n"
        "    IdentityFile ~/.ssh/id_old\n"
        "    IdentitiesOnly yes\n",
    )

    assert repair.ensure_control_et_ssh_config() == "repaired"
    text = conf.read_text(encoding="utf-8")
    assert "MacBook Air via Tailscale" not in text
    assert "id_old" not in text
    assert "STAYTURGID-CONTROL-ET" in text
    assert "id_ed25519_fleet" in text


def _setup_tailscale(monkeypatch):
    commands = []
    monkeypatch.setattr(repair, "read_device_profile", lambda: {})
    monkeypatch.setattr(repair, "_tailscale_installed", lambda _have_sh=False: True)
    monkeypatch.setattr(
        repair,
        "_device_command",
        lambda args, have_sh=False, timeout=15: commands.append((args, have_sh)) or (0, ""),
    )
    monkeypatch.setattr(repair, "log", lambda *_args, **_kwargs: None)
    return commands


def test_tailscale_healthy_still_enforces_policy(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: True)

    assert repair.ensure_tailscale(have_sh=True) == "up"
    assert [command[:5] for command, _have_sh in commands] == [
        ["settings", "put", "secure", "always_on_vpn_app", repair.TAILSCALE_PACKAGE],
        ["settings", "put", "secure", "always_on_vpn_lockdown", "0"],
    ]
    assert all(have_sh for _command, have_sh in commands)


def test_tailscale_reconnect_receiver_is_verified(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3: True)

    assert repair.ensure_tailscale() == "repaired"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert not any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_first_failure_defers_activity_fallback(monkeypatch):
    """A single down reading shouldn't yank the app into the foreground —
    only a second consecutive cycle (tracked via state.json) escalates."""
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3: False)
    monkeypatch.setattr(repair, "_previous_repair_field", lambda _key: "up")

    assert repair.ensure_tailscale() == "FAILED"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert not any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_failed_receiver_and_activity_report_failure(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3: False)
    monkeypatch.setattr(repair, "_previous_repair_field", lambda _key: "down")

    assert repair.ensure_tailscale() == "FAILED"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_status_normalizes_runtime_and_policy(monkeypatch):
    _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: False)

    assert repair._tailscale_status(have_sh=True) == ("down", "down")


def test_tailscale_status_skips_disabled_profile(monkeypatch):
    monkeypatch.setattr(repair, "read_device_profile", lambda: {"tailscaleEnabled": False})

    assert repair._tailscale_status() == ("skip", "skip")


def test_tailscale_runtime_probes_remote_control_plane(monkeypatch):
    commands = []
    monkeypatch.setattr("builtins.open", lambda _path: io.StringIO("tun0: 0 0 0 0\n"))
    monkeypatch.setattr(
        repair,
        "run",
        lambda args, timeout=15: commands.append((args, timeout)) or (0, ""),
    )

    assert repair._tailscale_runtime_up() is True
    assert commands == [
        (
            ["ping", "-c", "2", "-W", "3", "controlplane.tailscale.com"],
            8,
        )
    ]
