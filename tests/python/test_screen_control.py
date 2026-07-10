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


def test_session_fails_closed_when_presence_on_missing(monkeypatch):
    """rc 127 from agent-presence on must abort (not warn-and-continue)."""
    session = sc.ScreenControlSession("s24", skip_request=True)
    session._skip = False
    monkeypatch.setattr(sc, "_run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(sc, "mac_adb_shell", lambda *a, **k: (0, "0\n"))
    monkeypatch.setattr(sc.uc, "clear_ui_obstructions", lambda *a, **k: [])
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: "com.example/.Ime")
    monkeypatch.setattr(sc, "set_inversion", lambda _s, en: True)
    monkeypatch.setattr(sc, "ssh_presence", lambda *a, **k: (127, "missing"))
    try:
        session.__enter__()
        assert False, "expected ScreenControlError"
    except sc.ScreenControlError as e:
        assert "agent-presence on failed" in str(e)


def test_skip_presence_still_enables_inversion(monkeypatch):
    """SKIP_PRESENCE skips consent/torch but must still invert + gate input."""
    calls = []
    session = sc.ScreenControlSession("s24", skip_request=True)
    session._skip = True
    monkeypatch.setattr(
        sc,
        "_run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(sc.uc, "clear_ui_obstructions", lambda *a, **k: [])
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: "com.example/.Ime")
    monkeypatch.setattr(
        sc, "set_inversion", lambda _s, en: calls.append(("inv", en)) or True
    )
    monkeypatch.setattr(
        sc,
        "ssh_presence",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("presence must not run")),
    )
    session.__enter__()
    assert session.active is True
    assert ("inv", True) in calls
    # Exit must clear inversion even when presence was skipped.
    monkeypatch.setattr(sc, "restore_default_ime", lambda *a, **k: True)
    session.__exit__(None, None, None)
    assert ("inv", False) in calls
    assert session.active is False


def test_guarded_shell_blocks_input_when_inversion_off(monkeypatch):
    monkeypatch.setattr(sc, "inversion_enabled", lambda _s: False)

    def boom(*_a, **_k):
        raise AssertionError("adb must not run")

    monkeypatch.setattr(sc, "mac_adb_shell", boom)
    try:
        sc.guarded_adb_shell("serial", True, "input", "tap", "1", "2")
        assert False, "expected ScreenControlError"
    except sc.ScreenControlError as e:
        assert "inversion is off" in str(e)


def test_ssh_presence_timeout_returns_124(monkeypatch):
    import subprocess

    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=25)

    monkeypatch.setattr(sc.dev, "resolve_ssh_host", lambda h: "hd8")
    monkeypatch.setattr(sc.subprocess, "run", boom)
    rc, out = sc.ssh_presence("hd8", "request-screen", "hd8", "Auto")
    assert rc == 124
    assert "timed out" in out
