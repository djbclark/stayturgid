"""Unit tests for control/bin/verify_hd8_google.py (no device)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
sys.path.insert(0, str(REPO / "control" / "bin"))

import hd8_google_stack as hgs
import verify_hd8_google as vhg


def test_check_stack_ok(monkeypatch):
    monkeypatch.setattr(vhg, "run_command", lambda *a, **k: (0, "", ""))

    def _ver(run, serial, pkg):
        if pkg == hgs.GMS_PKG:
            return hgs.PINNED_GMS_VERSION_CODE
        if pkg == hgs.PLAY_PKG:
            return hgs.PINNED_PLAY_VERSION_CODE
        return 0

    monkeypatch.setattr(hgs, "package_version_code", _ver)
    monkeypatch.setattr(hgs, "package_version_name", lambda *a: "10-6494331")
    ok, detail = vhg.check_stack("SERIAL")
    assert ok is True


def test_check_stack_missing_gsf(monkeypatch):
    monkeypatch.setattr(vhg, "run_command", lambda *a, **k: (0, "", ""))
    monkeypatch.setattr(hgs, "package_version_code", lambda *a: 999_999_999)
    monkeypatch.setattr(hgs, "package_version_name", lambda *a: "9-6957767")
    ok, detail = vhg.check_stack("SERIAL")
    assert ok is False


def test_check_stack_allows_modern_gms(monkeypatch):
    monkeypatch.delenv("STAYTURGID_HD8_PIN_GMS", raising=False)
    monkeypatch.setattr(vhg, "run_command", lambda *a, **k: (0, "", ""))
    monkeypatch.setattr(hgs, "package_version_code", lambda *a: 999_999_999)
    monkeypatch.setattr(hgs, "package_version_name", lambda *a: "10-6494331")
    ok, detail = vhg.check_stack("SERIAL")
    assert ok is True


def test_main_stack_only_no_vlm(monkeypatch):
    monkeypatch.setattr(vhg.dev, "resolve_adb", lambda h: "SERIAL")
    monkeypatch.setattr(vhg.subprocess, "run", MagicMock())
    monkeypatch.setattr(vhg, "check_stack", lambda s: (True, {"ok": True}))
    gate = MagicMock()
    gate.ready = False
    gate.usable = False
    monkeypatch.setattr(vhg.vlm, "VlmGate", lambda **kw: gate)
    monkeypatch.setattr(vhg.vlm, "vlm_strict", lambda: False)
    assert vhg.main(["fireos-device"]) == 0
