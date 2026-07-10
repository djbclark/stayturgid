"""Tests for hd8 Google Play stack helpers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control" / "lib"))
import hd8_google_stack as hgs  # noqa: E402


def test_parse_version_code():
    text = "    versionCode=243530013 minSdk=23 targetSdk=34\n"
    assert hgs.parse_version_code(text) == 243530013


def test_needs_gms_downgrade_off_by_default(monkeypatch):
    monkeypatch.delenv("STAYTURGID_HD8_PIN_GMS", raising=False)
    assert hgs.pin_gms_enabled() is False
    # Default: do not force-downgrade modern GMS.
    assert hgs.needs_gms_downgrade(262434022) is False
    assert hgs.needs_gms_downgrade(243530013) is False
    assert hgs.needs_gms_downgrade(None) is False


def test_needs_gms_downgrade_when_pin_enabled(monkeypatch):
    monkeypatch.setenv("STAYTURGID_HD8_PIN_GMS", "1")
    assert hgs.pin_gms_enabled() is True
    assert hgs.needs_gms_downgrade(262434022) is True
    assert hgs.needs_gms_downgrade(243530013) is False


def test_needs_play_downgrade(monkeypatch):
    monkeypatch.delenv("STAYTURGID_HD8_PIN_GMS", raising=False)
    assert hgs.needs_play_downgrade(85212620) is False
    monkeypatch.setenv("STAYTURGID_HD8_PIN_GMS", "1")
    assert hgs.needs_play_downgrade(85212620) is True
    assert hgs.needs_play_downgrade(84262300) is False


def test_needs_gsf_reinstall():
    assert hgs.needs_gsf_reinstall("9-6957767") is True
    assert hgs.needs_gsf_reinstall("10-6494331") is False
    assert hgs.needs_gsf_reinstall(None) is True
