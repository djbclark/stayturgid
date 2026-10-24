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


def _fake_binary(tmp_path, output: str) -> str:
    """A stand-in binary whose --version prints `output`."""
    (tmp_path / "version.out").write_text(output + "\n")
    binary = tmp_path / "app"
    binary.write_text(f"#!/bin/sh\ncat '{tmp_path / 'version.out'}'\n")
    binary.chmod(0o755)
    return str(binary)


def test_installed_version_comes_from_the_binary_not_a_pin(tmp_path):
    """The roles install the latest release, so the monitor compares installed vs latest."""
    apps = {app["name"]: app for app in um.GITHUB_APPS}
    assert set(apps) == {"openobserve", "olivetin", "blackbox_exporter"}
    samples = {
        "openobserve": ("openobserve v1.0.4", "1.0.4"),
        "olivetin": ('level="info" msg="startup" commit="5c3d342" version="3000.17.1"', "3000.17.1"),
        "blackbox_exporter": ("blackbox_exporter, version 0.28.0 (branch: HEAD, revision: 5a059be)", "0.28.0"),
    }
    for name, (output, expected) in samples.items():
        assert um.get_installed_version(_fake_binary(tmp_path, output), apps[name]["pattern"]) == expected


def test_absent_or_unparseable_binary_reports_nothing(tmp_path):
    assert um.get_installed_version(str(tmp_path / "missing"), r"([0-9.]+)") is None
    assert um.get_installed_version(_fake_binary(tmp_path, "usage: app"), r"version ([0-9]+(?:\.[0-9]+)+)") is None
