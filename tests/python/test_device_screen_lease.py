"""Unit tests for DSCL v1 (control/lib/device_screen_lease.py)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "control" / "lib"),
)
import device_screen_lease as dsl  # noqa: E402


@pytest.fixture()
def lease_dir(tmp_path, monkeypatch):
    root = tmp_path / "dsc"
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_DIR", str(root))
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    monkeypatch.delenv("DEVICE_SCREEN_CONTROL_FORCE", raising=False)
    monkeypatch.delenv("STAYTURGID_SCREEN_LEASE_FORCE", raising=False)
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_WAIT_SEC", "0")
    # Reset any cached state — module has none
    return root


def test_acquire_and_status(lease_dir):
    lease = dsl.acquire("stock-android-device", device_ids=["SERIAL1"], purpose="test", agent="unit")
    assert lease["schema"] == dsl.SCHEMA
    assert lease["holder"]["project"] == "stayturgid"
    assert dsl.is_active(lease)
    found = dsl.find_active_lease("stock-android-device")
    assert found is not None
    assert found["holder"]["agent"] == "unit"
    lines = dsl.status_lines("stock-android-device")
    assert any("HELD" in x for x in lines)
    assert dsl.release("stock-android-device")
    assert dsl.find_active_lease("stock-android-device") is None


def test_foreign_project_blocks(lease_dir, monkeypatch):
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "other-app")
    dsl.acquire("stock-android-device", purpose="theirs", agent="claude")
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    with pytest.raises(dsl.LeaseConflict) as ei:
        dsl.acquire("stock-android-device", purpose="ours")
    assert "other-app" in str(ei.value) or "project=other-app" in dsl.format_holder(ei.value.lease)


def test_same_project_renews(lease_dir):
    a = dsl.acquire("oneui-device", purpose="one", agent="a")
    sid = a["holder"]["session_id"]
    b = dsl.acquire("oneui-device", purpose="two", agent="b", session_id=sid)
    assert b["purpose"] == "two"
    assert dsl.find_active_lease("oneui-device")["holder"]["agent"] == "b"


def test_same_project_different_session_blocks(lease_dir, monkeypatch):
    """Peer stayturgid jobs (different process) must not silent-takeover (M2)."""
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_WAIT_SEC", "0")
    a = dsl.acquire("oneui-device", purpose="one", agent="a", session_id="sess-a")
    assert a["holder"]["session_id"] == "sess-a"
    holder_pid = a.get("holder", {}).get("pid") or os.getpid()
    # Same pytest process would match pid renew; simulate a peer process.
    monkeypatch.setattr(os, "getpid", lambda: int(holder_pid) + 9001)
    with pytest.raises(dsl.LeaseConflict):
        dsl.acquire("oneui-device", purpose="two", agent="b", session_id="sess-b")
    assert dsl.find_active_lease("oneui-device")["holder"]["session_id"] == "sess-a"


def test_heartbeat_extends(lease_dir):
    lease = dsl.acquire("fireos-device", ttl_sec=120)
    exp1 = lease["expires_at"]
    time.sleep(1.05)
    updated = dsl.heartbeat("fireos-device", ttl_sec=120)
    assert updated is not None
    assert updated["expires_at"] >= exp1


def test_heartbeat_refreshes_alias_files(lease_dir):
    """Multi-key leases must not leave stale expires_at on serial/IP aliases."""
    import json

    dsl.acquire("stock-android-device", device_ids=["USB123"], purpose="alias-hb", ttl_sec=120)
    primary = dsl.lease_path("stock-android-device")
    alias = dsl.lease_path("USB123")
    exp_before = json.loads(alias.read_text())["expires_at"]
    time.sleep(1.05)
    updated = dsl.heartbeat("stock-android-device", ttl_sec=120)
    assert updated is not None
    prim = json.loads(primary.read_text())
    als = json.loads(alias.read_text())
    assert prim["expires_at"] == als["expires_at"]
    assert als["expires_at"] >= exp_before
    assert als["expires_at"] == updated["expires_at"]


def test_match_by_serial_alias(lease_dir):
    dsl.acquire("stock-android-device", device_ids=["USB123", "10.0.0.1:5555"])
    assert dsl.find_active_lease("USB123") is not None
    assert dsl.find_active_lease("10.0.0.1:5555") is not None


def test_force_steals(lease_dir, monkeypatch):
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "other")
    dsl.acquire("stock-android-device")
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_FORCE", "1")
    lease = dsl.acquire("stock-android-device", purpose="steal")
    assert lease["holder"]["project"] == "stayturgid"
