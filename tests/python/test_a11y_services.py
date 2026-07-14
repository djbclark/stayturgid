"""Unit tests for control/lib/a11y_services.py (detection-only)."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import a11y_services as a11y  # noqa: E402


def test_parse_services():
    cur = "com.other.app/.Service:%s" % a11y.AUTOJS6_A11Y
    parsed = a11y.parse_services(cur)
    assert "com.other.app/.Service" in parsed
    assert a11y.AUTOJS6_A11Y in parsed


def test_has_autojs6():
    assert a11y.has_autojs6("foo:bar:%s:baz" % a11y.AUTOJS6_A11Y)
    assert not a11y.has_autojs6("")
    assert not a11y.has_autojs6(None)


def test_normalize_value():
    assert a11y.normalize_value("  foo  ") == "foo"
    assert a11y.normalize_value("null") == ""
    assert a11y.normalize_value(None) == ""


def test_profile_services():
    svcs = a11y.profile_services("p7a")
    assert isinstance(svcs, list)
