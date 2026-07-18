"""Tests for fireos-device Google Play stack helpers."""

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


def test_ensure_fire_tools_zip_skips_when_present(tmp_path, monkeypatch):
    zip_path = tmp_path / "Fire-Tools.zip"
    zip_path.write_bytes(b"x" * 1_000_001)
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise AssertionError("curl must not run when cache is warm")

    monkeypatch.setattr(hgs.subprocess, "run", boom)
    hgs._ensure_fire_tools_zip(zip_path)
    assert calls == []


def test_ensure_fire_tools_zip_downloads_under_lock(tmp_path, monkeypatch):
    zip_path = tmp_path / "Fire-Tools.zip"
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        # Write the -o target (unique .part path).
        out = cmd[cmd.index("-o") + 1]
        Path(out).write_bytes(b"y" * 1_000_001)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(hgs.subprocess, "run", fake_run)
    hgs._ensure_fire_tools_zip(zip_path)
    assert zip_path.is_file() and zip_path.stat().st_size > 1_000_000
    assert any("curl" in c for c in calls)
    assert (tmp_path / "Fire-Tools.lock").is_file() or list(tmp_path.glob("*.lock"))
