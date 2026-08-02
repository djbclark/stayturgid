"""Unit tests for control/lib/fleet_deploy_lock.py (stayturgid issue #58)."""

import os

import fleet_deploy_lock as fdl
import pytest


def test_lock_path_honors_override(tmp_path, monkeypatch):
    override = tmp_path / "custom.lock"
    monkeypatch.setenv("STAYTURGID_FLEET_LOCK_PATH", str(override))
    assert fdl.lock_path() == override


def test_second_acquire_raises_fleet_lock_held(tmp_path, monkeypatch):
    monkeypatch.setenv("STAYTURGID_FLEET_LOCK_PATH", str(tmp_path / "fleet-deploy.lock"))

    with fdl.fleet_lock("deploy_fleet.py s24"):
        with pytest.raises(fdl.FleetLockHeld) as exc_info:
            with fdl.fleet_lock("termux_pkg_nightly.py (whole fleet)"):
                pass

    holder = exc_info.value.holder
    assert holder["label"] == "deploy_fleet.py s24"
    assert holder["pid"] == os.getpid()
    assert "deploy_fleet.py s24" in str(exc_info.value)


def test_lock_released_after_context_exits(tmp_path, monkeypatch):
    monkeypatch.setenv("STAYTURGID_FLEET_LOCK_PATH", str(tmp_path / "fleet-deploy.lock"))

    with fdl.fleet_lock("first run"):
        pass

    # A prior holder that has exited must not block the next one.
    with fdl.fleet_lock("second run"):
        pass


def test_lock_released_even_on_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("STAYTURGID_FLEET_LOCK_PATH", str(tmp_path / "fleet-deploy.lock"))

    with pytest.raises(ValueError):
        with fdl.fleet_lock("first run"):
            raise ValueError("boom")

    with fdl.fleet_lock("second run"):
        pass


def test_format_holder_handles_missing_fields():
    assert fdl.format_holder({}) == "? (pid ?, started ?)"
