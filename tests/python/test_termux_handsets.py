"""Unit tests for Termux Handsets wire helpers (no device required)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "termux" / "py"))

# Import module under test without stayturgid_shell connecting.
import stayturgid_handsets as th  # noqa: E402


def test_frame_pack():
    assert th._frame("ping") == b"\x00\x00\x00\x04ping"


def test_checked_flag_capital_k():
    assert th.Session._checked({"flags": "ckKfev"}) is True
    assert th.Session._checked({"flags": "ckfev"}) is False
    assert th.Session._checked({"checked": True}) is True


def test_center_bounds():
    assert th.Session._center({"bounds": [100, 200, 300, 400]}) == (200, 300)
    assert th.Session._center({}) is None


def test_enabled_respects_env(monkeypatch):
    monkeypatch.setenv("STAYTURGID_HANDSETS", "0")
    assert th.enabled() is False
    monkeypatch.setenv("STAYTURGID_HANDSETS", "1")
    monkeypatch.setenv("STAYTURGID_NO_LOCAL_ADB", "1")
    monkeypatch.setenv("STAYTURGID_PEER_BOOTSTRAP", "0")
    monkeypatch.setattr(th.sh, "privileged_shell_expected", lambda: False)
    assert th.enabled() is False
