"""Unit tests for control/bin/update_monitor.py — dependency-free version compare."""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_module():
    path = REPO / "control" / "bin" / "update_monitor.py"
    spec = importlib.util.spec_from_file_location("update_monitor", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_monitor"] = module
    spec.loader.exec_module(module)
    return module


um = _load_module()


def test_equal_dotted_versions_no_update():
    assert um.versions_differ("1.2.3", "1.2.3") is False


def test_zero_padding_equivalence_no_false_positive():
    """The bug this fix addresses: "1.2" and "1.2.0" are the same version."""
    assert um.versions_differ("1.2", "1.2.0") is False
    assert um.versions_differ("1.2.0", "1.2") is False


def test_numeric_ordering_still_detects_real_differences():
    assert um.versions_differ("1.2.3", "1.2.4") is True
    assert um.versions_differ("1.9.0", "1.10.0") is True  # not a string-lexical trap
    assert um.versions_differ("0.91.1", "0.91.4") is True


def test_calver_style_tags_compare_correctly():
    assert um.versions_differ("2026.7.20", "2026.7.20") is False
    assert um.versions_differ("2026.7.20", "2026.7.21") is True


def test_non_numeric_segments_fall_back_to_string_inequality():
    """A tag that doesn't parse as dotted integers must never raise — just
    fall back to plain string comparison."""
    assert um.versions_differ("1.2.3-rc1", "1.2.3-rc1") is False
    assert um.versions_differ("1.2.3-rc1", "1.2.3-rc2") is True
    assert um.versions_differ("v1.2.3", "1.2.3") is True  # caller strips "v" before calling


def test_escape_label_value_handles_prometheus_special_chars():
    assert um.escape_label_value('1.2"x') == '1.2\\"x'
    assert um.escape_label_value("a\\b\nc") == "a\\\\b\\nc"
