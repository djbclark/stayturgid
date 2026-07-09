"""Unit tests for termux stayturgid_shell helpers (no device)."""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "termux", "py"))
import stayturgid_shell as sh  # noqa: E402


def test_privileged_shell_expected_false_from_profile(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    (state / "device.json").write_text(json.dumps({"privilegedShellExpected": False}))
    monkeypatch.setattr(sh, "SD", str(tmp_path))
    monkeypatch.setattr(sh, "STG", str(tmp_path))
    monkeypatch.setattr(sh, "HOME", str(tmp_path))
    assert sh.privileged_shell_expected() is False


def test_privileged_shell_expected_true_from_profile(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    (state / "device.json").write_text(json.dumps({"privilegedShellExpected": True}))
    monkeypatch.setattr(sh, "SD", str(tmp_path))
    monkeypatch.setattr(sh, "STG", str(tmp_path))
    assert sh.privileged_shell_expected() is True


def test_is_input_command():
    sys.path.insert(0, os.path.join(REPO, "termux", "py"))
    import stayturgid_screen_control as sc

    assert sc.is_input_command(["input", "tap", "1", "2"])
    assert not sc.is_input_command(["uiautomator", "dump", "/x"])
