"""Unit tests for control/lib/a11y_services.py (detection-only)."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import a11y_services as a11y


def test_parse_services():
    cur = "com.other.app/.Service:com.example.app/.ExampleService"
    parsed = a11y.parse_services(cur)
    assert "com.other.app/.Service" in parsed
    assert "com.example.app/.ExampleService" in parsed


def test_normalize_value():
    assert a11y.normalize_value("  foo  ") == "foo"
    assert a11y.normalize_value("null") == ""
    assert a11y.normalize_value(None) == ""


def test_profile_services():
    svcs = a11y.profile_services("stock-android-device")
    assert isinstance(svcs, list)
