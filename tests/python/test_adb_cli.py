"""Unit tests for control/lib/adb_cli.py."""

import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "control", "lib")
)
import adb_cli as ac


def test_adb_builds_serial_scoped_argv(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

    monkeypatch.setattr(ac, "run", fake_run)
    monkeypatch.setattr(ac, "adb_bin", lambda: "adb")
    ac.adb("192.0.2.12:5555", "shell", "true", check=False)
    assert seen["cmd"] == ["adb", "-s", "192.0.2.12:5555", "shell", "true"]
    assert seen["kwargs"]["check"] is False


def test_alias_for_host_forwards_to_stayturgid_device(monkeypatch):
    seen = {}

    def fake_alias_for_host(host):
        seen["host"] = host
        return "hd8"

    monkeypatch.setattr(ac.dev, "alias_for_host", fake_alias_for_host)
    assert ac.alias_for_host("100.124.55.39") == "hd8"
    assert seen["host"] == "100.124.55.39"


def test_debugging_dialog_present_detects_usb_activity(monkeypatch):
    monkeypatch.setattr(
        ac,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="...UsbDebuggingActivity...", stderr=""),
    )
    assert ac.debugging_dialog_present("serial") is True


def test_debugging_dialog_present_detects_wifi_activity(monkeypatch):
    monkeypatch.setattr(
        ac,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="...WifiDebuggingActivity...", stderr=""),
    )
    assert ac.debugging_dialog_present("serial") is True


def test_debugging_dialog_present_false_when_absent(monkeypatch):
    monkeypatch.setattr(
        ac,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="nothing interesting", stderr=""),
    )
    assert ac.debugging_dialog_present("serial") is False


def test_debugging_dialog_present_never_sends_keyevents(monkeypatch):
    """The old dismiss function sent 'input keyevent' — the detector must never do this."""
    sent = []

    def fake_run(cmd, **kwargs):
        sent.append(cmd)
        return subprocess.CompletedProcess([], 0, stdout="...WifiDebuggingActivity...", stderr="")

    monkeypatch.setattr(ac, "run", fake_run)
    ac.debugging_dialog_present("serial")
    assert not any("keyevent" in part for cmd in sent for part in cmd)


def fake_phone(monkeypatch, inversion_turns_on):
    """run() stand-in for a phone showing the 16 KB dialog until OK is pressed while inverted."""
    state = {"inv": "0", "dialog": True}
    sent = []

    def fake_run(cmd, **kwargs):
        sent.append(cmd)
        out = ""
        if cmd[4:7] == ["settings", "put", "secure"]:
            state["inv"] = cmd[-1] if cmd[-1] != "1" or inversion_turns_on else state["inv"]
        elif cmd[4:7] == ["settings", "get", "secure"]:
            out = state["inv"] + "\n"
        elif "KEYCODE_ENTER" in cmd:
            state["dialog"] = state["inv"] != "1"
        elif "dumpsys" in cmd and state["dialog"]:
            out = "...AppCompatibilityDialog..."
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(ac, "run", fake_run)
    monkeypatch.setattr(ac, "adb_bin", lambda: "adb")
    monkeypatch.setattr(ac.time, "sleep", lambda _s: None)
    return state, sent


def test_dismiss_app_compatibility_dialog_presses_ok_only_while_inverted(monkeypatch):
    state, sent = fake_phone(monkeypatch, inversion_turns_on=True)
    assert ac.dismiss_app_compatibility_dialog("serial") is True
    assert state["dialog"] is False
    assert state["inv"] == "0"  # restored to what it was


def test_dismiss_app_compatibility_dialog_refuses_without_inversion(monkeypatch):
    state, sent = fake_phone(monkeypatch, inversion_turns_on=False)
    assert ac.dismiss_app_compatibility_dialog("serial") is False
    assert state["dialog"] is True
    assert not any("keyevent" in part for cmd in sent for part in cmd)


PENDING_LOGCAT = (
    "1760760000.123  1234  1250 I adbd    : adbd_auth: received public key\n"
    "1760760000.456  1234  1250 I adbd    : adbd_auth: prompt currently pending, skipping\n"
)
NORMAL_LOGCAT = (
    "1760760000.123  1234  1250 I adbd    : adbd_auth: received public key\n"
    "1760760001.000   800   900 I ActivityTaskManager: START u0 {cmp=com.termux/.app.TermuxActivity}\n"
)


def fake_auth_phone(monkeypatch, logcat, dialog, logcat_rc=0):
    """run() stand-in: logcat returns `logcat`, dumpsys shows the debugging dialog if `dialog`."""
    sent = []

    def fake_run(cmd, **kwargs):
        sent.append(cmd)
        out, rc = "", 0
        if "logcat" in cmd[-1]:
            out, rc = logcat, logcat_rc
        elif "dumpsys" in cmd and dialog:
            out = "...com.android.systemui/.wifi.WifiDebuggingActivity..."
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="")

    monkeypatch.setattr(ac, "run", fake_run)
    monkeypatch.setattr(ac, "adb_bin", lambda: "adb")
    return sent


def restarts(sent):
    return [cmd for cmd in sent if "ctl.restart" in cmd[-1]]


def test_adb_prompt_pending_in_detects_pending_line():
    assert ac.adb_prompt_pending_in(PENDING_LOGCAT) is True


def test_adb_prompt_pending_in_ignores_normal_output():
    assert ac.adb_prompt_pending_in(NORMAL_LOGCAT) is False
    assert ac.adb_prompt_pending_in("") is False


def test_check_adb_prompt_ok_on_normal_logcat(monkeypatch):
    sent = fake_auth_phone(monkeypatch, NORMAL_LOGCAT, dialog=False)
    assert ac.check_adb_prompt("serial", restart_adbd=True) == "ok"
    assert not restarts(sent)


def test_check_adb_prompt_unknown_when_logcat_fails(monkeypatch):
    sent = fake_auth_phone(monkeypatch, PENDING_LOGCAT, dialog=False, logcat_rc=1)
    assert ac.check_adb_prompt("serial", restart_adbd=True) == "unknown"
    assert not restarts(sent)


def test_check_adb_prompt_reads_a_device_clock_window(monkeypatch):
    sent = fake_auth_phone(monkeypatch, NORMAL_LOGCAT, dialog=False)
    ac.check_adb_prompt("serial", window_s=300)
    assert sent[0][:4] == ["adb", "-s", "serial", "shell"]
    assert sent[0][4] == 'logcat -d -v epoch -t "$(( $(date +%s) - 300 )).0"'


def test_check_adb_prompt_offers_hint_by_default(monkeypatch, capsys):
    sent = fake_auth_phone(monkeypatch, PENDING_LOGCAT, dialog=False)
    assert ac.check_adb_prompt("serial") == "stuck"
    assert not restarts(sent)
    assert "stuck prompt" in capsys.readouterr().out


def test_check_adb_prompt_refuses_restart_while_dialog_showing(monkeypatch):
    sent = fake_auth_phone(monkeypatch, PENDING_LOGCAT, dialog=True)
    assert ac.check_adb_prompt("serial", restart_adbd=True) == "dialog"
    assert not restarts(sent)
    assert not any(part in ("am", "start", "keyevent", "input") for cmd in sent for part in cmd)


def test_check_adb_prompt_opt_in_issues_only_a_detached_restart(monkeypatch):
    sent = fake_auth_phone(monkeypatch, PENDING_LOGCAT, dialog=False)
    assert ac.check_adb_prompt("serial", restart_adbd=True) == "restarted"
    assert restarts(sent) == [["adb", "-s", "serial", "shell", ac.ADBD_RESTART_DETACHED]]
    assert ac.ADBD_RESTART_DETACHED.startswith("nohup setsid ")
    assert ac.ADBD_RESTART_DETACHED.endswith(" &")
    # Read logcat, read activities, restart: nothing else reaches the phone.
    assert len(sent) == 3
    assert not any(" am " in " %s " % " ".join(cmd) or "keyevent" in " ".join(cmd) for cmd in sent)
