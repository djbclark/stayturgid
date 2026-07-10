"""Tests for hd8 Google Play stack helpers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "mac"))
import hd8_google_stack as hgs  # noqa: E402


def test_parse_version_code():
    text = "    versionCode=243530013 minSdk=23 targetSdk=34\n"
    assert hgs.parse_version_code(text) == 243530013


def test_needs_gms_downgrade():
    assert hgs.needs_gms_downgrade(262434022) is True
    assert hgs.needs_gms_downgrade(243530013) is False
    assert hgs.needs_gms_downgrade(None) is False


def test_needs_play_downgrade():
    assert hgs.needs_play_downgrade(85212620) is True
    assert hgs.needs_play_downgrade(84262300) is False
