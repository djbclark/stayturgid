"""Unit tests for AutoJs6 accessibility detection."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import a11y_services as a11y

A11Y_SVC = a11y.AUTOJS6_A11Y


def test_parse_empty():
    assert a11y.parse_services("") == []
    assert a11y.parse_services("null") == []
    assert a11y.parse_services(None) == []


def test_parse_preserves_all():
    cur = "com.other.app/.Service:" + A11Y_SVC
    services = a11y.parse_services(cur)
    assert len(services) == 2
    assert A11Y_SVC in services
    assert "com.other.app/.Service" in services


def test_has_autojs6_detection():
    assert a11y.has_autojs6("com.other.app/.Service:" + A11Y_SVC)
    assert a11y.has_autojs6(A11Y_SVC)
    assert not a11y.has_autojs6("com.other.app/.Service")
    assert not a11y.has_autojs6("")
