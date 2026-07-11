"""Unit tests for AutoJs6 accessibility append helper."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import a11y_services as a11y  # noqa: E402

A11Y_SVC = a11y.AUTOJS6_A11Y


def test_a11y_append_empty():
    assert a11y.append_service("", A11Y_SVC) == A11Y_SVC
    assert a11y.append_service("null", A11Y_SVC) == A11Y_SVC


def test_a11y_append_preserves_existing():
    cur = "com.other.app/.Service"
    out = a11y.append_service(cur, A11Y_SVC)
    assert out.startswith(cur + ":")
    assert A11Y_SVC in out


def test_a11y_append_idempotent():
    cur = "com.other.app/.Service:" + A11Y_SVC
    assert a11y.append_service(cur, A11Y_SVC) == cur
