"""Unit tests for control/lib/screen_control.py input gating."""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "lib")
)
import screen_control as sc


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
    monkeypatch.setattr(sc, "set_default_ime", lambda _s, ime: calls.append(ime) or True)
    assert sc.restore_default_ime("serial", "com.amazon.redstone/.FireKeyboardService")
    assert calls == ["com.amazon.redstone/.FireKeyboardService"]


def test_skip_presence_still_enables_inversion(monkeypatch, tmp_path):
    """SKIP_PRESENCE skips consent/torch but must still invert + gate input."""
    calls = []
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_DIR", str(tmp_path / "dsc"))
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    session = sc.ScreenControlSession("oneui-device", skip_request=True)
    session._skip = True
    monkeypatch.setattr(
        sc,
        "_run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(sc.uc, "clear_ui_obstructions", lambda *a, **k: [])
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: "com.example/.Ime")
    monkeypatch.setattr(sc, "get_foreground_component", lambda _s: None)
    monkeypatch.setattr(sc, "set_inversion", lambda _s, en: calls.append(("inv", en)) or True)
    monkeypatch.setattr(
        sc,
        "ssh_presence",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("presence must not run")),
    )
    monkeypatch.setattr(sc.ScreenControlSession, "_start_keepalive", lambda self: None)
    monkeypatch.setattr(sc.ScreenControlSession, "_stop_keepalive_thread", lambda self: None)
    monkeypatch.setattr(sc.dev, "device_row", lambda *a, **k: None)
    monkeypatch.setattr(sc.dev, "resolve_adb", lambda h, *a, **k: "serial-oneui-device")
    monkeypatch.setattr(sc, "lock_portrait_orientation", lambda _s: None)
    session.__enter__()
    assert session.active is True
    assert ("inv", True) in calls
    # Exit must clear inversion even when presence was skipped.
    monkeypatch.setattr(sc, "restore_default_ime", lambda *a, **k: True)
    monkeypatch.setattr(sc, "restore_foreground", lambda *a, **k: True)
    session.__exit__(None, None, None)
    assert ("inv", False) in calls
    assert session.active is False


def test_foreign_lease_blocks_session(monkeypatch, tmp_path):
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_DIR", str(tmp_path / "dsc"))
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "other-project")
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_WAIT_SEC", "0")
    sc.dsl.acquire("stock-android-device", purpose="foreign", agent="them")
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    session = sc.ScreenControlSession("stock-android-device")
    monkeypatch.setattr(sc.dev, "resolve_adb", lambda h, *a, **k: "serial-stock-android-device")
    monkeypatch.setattr(sc.dev, "device_row", lambda *a, **k: None)
    with pytest.raises(sc.ScreenControlError) as ei:
        session.__enter__()
    assert "blocked" in str(ei.value).lower() or "held" in str(ei.value).lower()


def test_parse_foreground_component():
    sample = (
        "  mCurrentFocus=Window{abc u0 com.discord/.MainActivity}\n"
        "  mFocusedApp=ActivityRecord{… com.discord/.MainActivity}\n"
    )
    assert sc.parse_foreground_component(sample) == "com.discord/.MainActivity"
    assert sc.parse_foreground_component("") is None


def test_restore_foreground_launcher_goes_home(monkeypatch):
    calls = []

    def fake_shell(*args, **_k):
        calls.append(args)
        return 0, ""

    assert sc.restore_foreground(
        "serial",
        "com.google.android.apps.nexuslauncher/.NexusLauncherActivity",
        shell_fn=fake_shell,
    )
    assert calls[0][:2] == ("input", "keyevent")
    assert "KEYCODE_HOME" in calls[0]


def test_restore_foreground_app_am_start(monkeypatch):
    calls = []

    def fake_shell(*args, **_k):
        calls.append(args)
        return 0, ""

    assert sc.restore_foreground("serial", "com.discord/.MainActivity", shell_fn=fake_shell)
    assert calls[0][0] == "am"
    assert "com.discord/.MainActivity" in calls[0]


def test_session_does_not_save_or_restore_foreground(monkeypatch, tmp_path):
    """Foreground save/restore disabled 2026-07-14 (H9)."""
    restored = []
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_DIR", str(tmp_path / "dsc"))
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_WAIT_SEC", "0")
    session = sc.ScreenControlSession("oneui-device", skip_request=True)
    session._skip = True
    monkeypatch.setattr(
        sc,
        "_run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(sc.uc, "clear_ui_obstructions", lambda *a, **k: [])
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: "com.example/.Ime")
    monkeypatch.setattr(sc, "set_inversion", lambda _s, en: True)
    monkeypatch.setattr(sc, "restore_default_ime", lambda *a, **k: True)
    monkeypatch.setattr(sc, "lock_portrait_orientation", lambda _s: None)
    monkeypatch.setattr(
        sc,
        "restore_foreground",
        lambda serial, comp, shell_fn=None: restored.append(comp) or True,
    )
    monkeypatch.setattr(sc.ScreenControlSession, "_start_keepalive", lambda self: None)
    monkeypatch.setattr(sc.ScreenControlSession, "_stop_keepalive_thread", lambda self: None)
    monkeypatch.setattr(sc.dev, "device_row", lambda *a, **k: None)
    monkeypatch.setattr(sc.dev, "resolve_adb", lambda h, *a, **k: "serial-oneui-device")
    session.__enter__()
    assert session._saved_component is None
    session.__exit__(None, None, None)
    assert restored == []


def test_session_fails_closed_when_presence_on_missing(monkeypatch, tmp_path):
    """rc 127 from agent-presence on must abort (not warn-and-continue)."""
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_DIR", str(tmp_path / "dsc"))
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_WAIT_SEC", "0")
    session = sc.ScreenControlSession("oneui-device", skip_request=True)
    session._skip = False
    monkeypatch.setattr(sc, "_run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(sc, "mac_adb_shell", lambda *a, **k: (0, "0\n"))
    monkeypatch.setattr(sc.uc, "clear_ui_obstructions", lambda *a, **k: [])
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: "com.example/.Ime")
    monkeypatch.setattr(sc, "get_foreground_component", lambda _s: None)
    monkeypatch.setattr(sc, "set_inversion", lambda _s, en: True)
    monkeypatch.setattr(sc, "ssh_presence", lambda *a, **k: (127, "missing"))
    monkeypatch.setattr(sc.dev, "device_row", lambda *a, **k: None)
    monkeypatch.setattr(sc.dev, "resolve_adb", lambda h, *a, **k: "serial-oneui-device")
    try:
        session.__enter__()
        assert False, "expected ScreenControlError"
    except sc.ScreenControlError as e:
        assert "agent-presence on failed" in str(e)


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


def test_ssh_presence_exports_quiet(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setenv("STAYTURGID_PRESENCE_QUIET", "1")
    monkeypatch.setattr(sc.dev, "resolve_ssh_host", lambda h: "oneui-device")
    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    rc, _out = sc.ssh_presence("oneui-device", "on", "oneui-device", "Auto")
    assert rc == 0
    remote = captured["cmd"][-1]
    assert "STAYTURGID_PRESENCE_QUIET=1" in remote


def test_ssh_presence_timeout_returns_124(monkeypatch):
    import subprocess

    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=25)

    monkeypatch.setattr(sc.dev, "resolve_ssh_host", lambda h: "fireos-device")
    monkeypatch.setattr(sc.subprocess, "run", boom)
    rc, out = sc.ssh_presence("fireos-device", "request-screen", "fireos-device", "Auto")
    assert rc == 124
    assert "timed out" in out


def test_apply_portrait_lock_sets_system_settings(monkeypatch):
    calls = []

    def fake_shell(serial, *args, **kw):
        calls.append((serial, args))
        return 0, ""

    monkeypatch.setattr(sc, "mac_adb_shell", fake_shell)
    assert sc.apply_portrait_lock("serial-1") is True
    assert (
        "serial-1",
        ("settings", "put", "system", "accelerometer_rotation", "0"),
    ) in calls
    assert (
        "serial-1",
        ("settings", "put", "system", "user_rotation", "0"),
    ) in calls
    # Best-effort window-manager lock (first successful variant is enough).
    assert any(
        c[0] == "serial-1" and c[1][:2] in (("cmd", "window"), ("wm", "set-user-rotation"), ("wm", "user-rotation"))
        for c in calls
    )


def test_session_locks_portrait_on_enter_and_does_not_restore_on_exit(monkeypatch, tmp_path):
    """Portrait lock is a standing baseline — exit must never touch rotation
    settings, even though a prior manual lock may have happened mid-session."""
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_DIR", str(tmp_path / "dsc"))
    monkeypatch.setenv("DEVICE_SCREEN_CONTROL_PROJECT", "stayturgid")
    rotation_calls = []
    # resolve_adb is called in __init__ — mock first.
    monkeypatch.setattr(sc.dev, "resolve_adb", lambda h, *a, **k: "serial-oneui-device")
    monkeypatch.setattr(sc.dev, "device_row", lambda *a, **k: None)
    session = sc.ScreenControlSession("oneui-device", skip_request=True)
    session._skip = True
    monkeypatch.setattr(
        sc,
        "_run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(sc.uc, "clear_ui_obstructions", lambda *a, **k: [])
    monkeypatch.setattr(sc, "get_default_ime", lambda _s: "com.example/.Ime")
    monkeypatch.setattr(sc, "get_foreground_component", lambda _s: None)
    monkeypatch.setattr(sc, "set_inversion", lambda _s, en: True)
    monkeypatch.setattr(
        sc,
        "lock_portrait_orientation",
        lambda s: rotation_calls.append(("lock", s)),
    )
    monkeypatch.setattr(sc.ScreenControlSession, "_start_keepalive", lambda self: None)
    monkeypatch.setattr(sc.ScreenControlSession, "_stop_keepalive_thread", lambda self: None)
    session.__enter__()
    assert session.serial == "serial-oneui-device"
    assert ("lock", "serial-oneui-device") in rotation_calls
    monkeypatch.setattr(sc, "restore_default_ime", lambda *a, **k: True)
    monkeypatch.setattr(sc, "restore_foreground", lambda *a, **k: True)
    session.__exit__(None, None, None)
    assert not hasattr(session, "_saved_rotation")
    assert [c for c in rotation_calls if c[0] == "restore"] == []
