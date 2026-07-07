"""Unit tests for shared/mac/screen_control.py input gating."""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "shared", "mac"))
import screen_control as sc  # noqa: E402


def test_is_input_command_detects_tap():
    assert sc.is_input_command(["input", "tap", "1", "2"])
    assert sc.is_input_command(["input", "keyevent", "KEYCODE_HOME"])


def test_is_input_command_ignores_dump():
    assert not sc.is_input_command(["uiautomator", "dump", "/sdcard/x.xml"])
    assert not sc.is_input_command(["settings", "get", "secure", "x"])


def test_is_input_command_empty():
    assert not sc.is_input_command([])
    assert not sc.is_input_command(["pm", "list", "packages"])


def test_restore_default_ime_skips_when_unchanged(monkeypatch):
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: "com.example/.Ime")
    assert sc.restore_default_ime("serial", "com.example/.Ime") is True


def test_restore_default_ime_from_adb_keyboard(monkeypatch):
    calls = []
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: sc.ADB_KEYBOARD)
    monkeypatch.setattr(sc, "set_default_ime",
                        lambda _s, ime: calls.append(ime) or True)
    assert sc.restore_default_ime("serial", "com.amazon.redstone/.FireKeyboardService")
    assert calls == ["com.amazon.redstone/.FireKeyboardService"]
