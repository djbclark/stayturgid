"""Unit tests for stayturgid_peer_keepalive (no device)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import stayturgid_peer_keepalive as pk


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


class _FakePeer:
    WITHHELD_PREFIX = "withheld: "
    SHIZUKU_START_WITHHELD_MSG = (
        "shizuku start withheld: ADB authorisation dialog unanswered; operator: tap Attempt now on the phone"
    )

    def __init__(self, result):
        self.result = result

    def bootstrap_shizuku(self):
        return self.result


def test_withheld_shizuku_is_not_a_failure_and_logs_once(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr(pk, "STATE", str(tmp_path))
    monkeypatch.setattr(pk, "_recent", lambda _n: False)
    monkeypatch.setattr(pk, "_touch", lambda _n: None)
    monkeypatch.setattr(pk, "_log", logs.append)
    peer = _FakePeer((False, "withheld: via peer-a"))
    monkeypatch.setitem(sys.modules, "stayturgid_peer_bootstrap", peer)
    assert pk.ensure_shizuku() is True
    assert pk.ensure_shizuku() is True
    assert logs == ["WARNING: " + peer.SHIZUKU_START_WITHHELD_MSG]
    peer.result = (True, "via peer-a: OK")
    assert pk.ensure_shizuku() is True
    assert len(logs) == 3 and "no longer unanswered" in logs[1]
