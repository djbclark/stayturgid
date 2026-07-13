"""Tests for Termux repair's control-ET SSH config self-heal."""
from __future__ import annotations

import importlib.util
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
        "Host mac\n    HostName 100.0.0.1\n"
        "    IdentityFile ~/.ssh/id_ed25519_fleet\n"
        "    IdentitiesOnly yes\n",
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
