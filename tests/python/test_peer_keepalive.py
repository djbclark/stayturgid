"""Unit tests for stayturgid_peer_keepalive (no device)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import stayturgid_peer_keepalive as pk  # noqa: E402


def test_no_local_adb_env(monkeypatch):
    monkeypatch.setenv("STAYTURGID_NO_LOCAL_ADB", "1")
    assert pk._no_local_adb() is True
    monkeypatch.delenv("STAYTURGID_NO_LOCAL_ADB", raising=False)
    monkeypatch.setattr(pk, "STG", "/nonexistent")
    assert pk._no_local_adb() is False


def test_main_noop_without_flag(monkeypatch):
    monkeypatch.delenv("STAYTURGID_NO_LOCAL_ADB", raising=False)
    monkeypatch.setattr(pk, "STG", "/nonexistent")
    assert pk.main([]) == 0
