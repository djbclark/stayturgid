"""Unit tests for shared/a11y_services.py."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared"))
import a11y_services as a11y  # noqa: E402


def test_append_preserves_existing():
    cur = "com.other.app/.Service"
    out = a11y.append_service(cur, a11y.AUTOJS6_A11Y)
    assert cur in out
    assert a11y.AUTOJS6_A11Y in out


def test_services_lost_detects_shrink():
    before = "a:b:c"
    after = "c"
    assert a11y.services_lost(before, after) == ["a", "b"]


def test_desired_services_merges_profile():
    merged = a11y.parse_services(
        a11y.desired_services("p7a", "com.live/.Svc", ensure_autojs6=True)
    )
    assert "com.live/.Svc" in merged
    assert a11y.AUTOJS6_A11Y in merged
    assert "com.wispr.flowapp/com.wispr.flowapp.service.FlowAccessibilityService" in merged


def test_repair_after_shrink():
    before = "com.a/.A:com.b/.B"
    after = a11y.AUTOJS6_A11Y
    fixed = a11y.repair_after_shrink(before, after, "p7a")
    assert fixed
    assert "com.a/.A" in fixed
    assert a11y.AUTOJS6_A11Y in fixed
