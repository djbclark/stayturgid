"""Unit tests for the Python Termux boot supervisor."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import start_adb


def test_cfserverd_argv_quiet_by_default(monkeypatch):
    monkeypatch.delenv("STAYTURGID_CFSERVERD_VERBOSE", raising=False)
    argv = start_adb._cfserverd_argv()
    assert argv[-2:] == ["-Ff", start_adb.CF_SERVERD_CF]
    assert "-v" not in argv and "-d" not in argv


def test_cfserverd_argv_verbose_toggle(monkeypatch):
    for val, flag in [("1", "-v"), ("v", "-v"), ("2", "-d"), ("debug", "-d")]:
        monkeypatch.setenv("STAYTURGID_CFSERVERD_VERBOSE", val)
        assert start_adb._cfserverd_argv()[-1] == flag, val
    monkeypatch.setenv("STAYTURGID_CFSERVERD_VERBOSE", "0")
    assert start_adb._cfserverd_argv()[-1] == start_adb.CF_SERVERD_CF
    monkeypatch.setenv("STAYTURGID_CFSERVERD_VERBOSE", "--log-level=verbose")
    assert start_adb._cfserverd_argv()[-1] == "--log-level=verbose"


def test_shell_transport_prefers_localhost_adb(monkeypatch):
    monkeypatch.setattr(start_adb, "_adb_connect", lambda: "device")
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(start_adb, "_capture", lambda *args, **kwargs: (0, "2000\n"))

    command, name = start_adb._shell_transport()

    assert command == ["adb", "-s", "localhost:5555", "shell"]
    assert name == "localhost-adb"


def test_shell_transport_falls_back_to_rish(monkeypatch):
    responses = iter([(-1, ""), (0, "Entering shell...\n2000\n"), (0, "2000\n")])
    monkeypatch.setattr(start_adb, "_adb_connect", lambda: "device")
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(start_adb, "_capture", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(start_adb.os, "access", lambda *args, **kwargs: True)

    command, name = start_adb._shell_transport()

    assert command == ["adb", "-s", "localhost:5555", "shell"]
    assert name == "localhost-adb-rish-recovered"


def test_shell_transport_leaves_adbd_alone_while_unauthorised(monkeypatch):
    """A rish `ctl.restart adbd` drops the connection showing the dialog, and
    adb's re-dial raises another: never while Termux's key is unauthorised."""
    commands = []
    monkeypatch.setattr(start_adb, "_adb_connect", lambda: "waiting")
    monkeypatch.setattr(start_adb, "_run", lambda command, **_kwargs: commands.append(command) or 0)
    monkeypatch.setattr(start_adb, "_capture", lambda command, **_kwargs: commands.append(command) or (0, "2000\n"))
    monkeypatch.setattr(start_adb.os, "access", lambda *args, **kwargs: True)

    command, name = start_adb._shell_transport()

    assert command is None
    assert name == start_adb.ADB_UNAUTHORISED
    assert commands == []


def test_shell_transport_rish_recovery_stops_when_dialog_appears(monkeypatch):
    """Port was closed, rish reopened it, and adbd now wants the dialog
    answered: one connection offered the key, so stop polling."""
    states = iter(["down", "waiting"])
    connects = []

    def fake_connect():
        connects.append(True)
        return next(states)

    monkeypatch.setattr(start_adb, "_adb_connect", fake_connect)
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(start_adb, "_capture", lambda *args, **kwargs: (0, "2000\n"))
    monkeypatch.setattr(start_adb.os, "access", lambda *args, **kwargs: True)
    monkeypatch.setattr(start_adb.time, "sleep", lambda *_: None)

    command, name = start_adb._shell_transport()

    assert (command, name) == (None, start_adb.ADB_UNAUTHORISED)
    assert len(connects) == 2


def test_launch_reports_unauthorised_adb(monkeypatch):
    monkeypatch.setattr(start_adb, "_shell_run", lambda *args, **kwargs: (-1, start_adb.ADB_UNAUTHORISED))
    ran = []
    monkeypatch.setattr(start_adb, "_run", lambda command, **_kwargs: ran.append(command) or 0)
    messages = []
    monkeypatch.setattr(start_adb, "_boot_log", messages.append)

    assert start_adb._launch_firerpa_via_shell("restart") is False
    assert ran == []
    assert messages == ["FIRERPA restart: adb unauthorised, waiting for the user"]


def test_adb_connect_uses_shared_gate(monkeypatch):
    import stayturgid_shell

    calls = []
    monkeypatch.setattr(stayturgid_shell, "adb_connect", lambda **kwargs: calls.append(kwargs) or "waiting")
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: pytest.fail("bare adb connect bypassed the gate"))

    assert start_adb._adb_connect() == "waiting"
    assert calls == [{"timeout": 5}]


class _StopLoop(BaseException):
    pass


def _daemon_loop_boot_commands(monkeypatch, gate_state):
    ran = []
    monkeypatch.setenv("STAYTURGID_BOOT_SETTLE_SEC", "0")
    monkeypatch.setattr(start_adb.time, "sleep", lambda *_: None)
    monkeypatch.setattr(start_adb.signal, "signal", lambda *args: None)
    monkeypatch.setattr(start_adb, "_run", lambda command, **_kwargs: ran.append(command) or 0)
    monkeypatch.setattr(start_adb, "_adb_connect", lambda: gate_state)

    def stop():
        raise _StopLoop

    monkeypatch.setattr(start_adb, "_ensure_dirs", stop)

    with pytest.raises(_StopLoop):
        start_adb.daemon_loop()
    return ran


@pytest.mark.parametrize("gate_state", ["device", "down"])
def test_daemon_loop_keeps_adb_tcpip_on_one_serial(monkeypatch, gate_state):
    """`adb tcpip 5555` stays as on master (it is what opens 5555 when Termux's
    only transport is a Wireless-debugging one); 127.0.0.1:5555 stays gone."""
    ran = _daemon_loop_boot_commands(monkeypatch, gate_state)
    assert ran == [["adb", "tcpip", "5555"]]


def test_daemon_loop_skips_adb_tcpip_while_a_dialog_is_pending(monkeypatch):
    assert _daemon_loop_boot_commands(monkeypatch, "waiting") == []


class _FakePhone:
    """adbd behind Termux's adb server on a virtual clock: an authorised key,
    5555 closed (row "offline"), and a rish restart that leaves the row
    offline for one second before it comes back as "device"."""

    def __init__(self, row="offline"):
        self.row = row
        self.clock = 0.0
        self.restarted_at = None
        self.restarts = 0

    def state(self):
        if self.restarted_at is not None:
            return "offline" if self.clock < self.restarted_at + 1 else "device"
        return self.row

    def sleep(self, seconds):
        self.clock += seconds

    def restart_adbd(self):
        self.restarts += 1
        self.restarted_at = self.clock

    def adb(self, args, timeout=60, input_text=None):
        import subprocess

        sub = args[1] if len(args) > 1 else ""
        if sub == "devices":
            row = self.state()
            out = "List of devices attached\n" + ("localhost:5555\t%s\n" % row if row else "")
            return subprocess.CompletedProcess(args, 0, out, "")
        if sub == "connect":
            if self.state():
                return subprocess.CompletedProcess(args, 0, "already connected to localhost:5555\n", "")
            return subprocess.CompletedProcess(args, 1, "failed to connect: Connection refused\n", "")
        if sub == "disconnect":
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "unexpected")


def test_shell_transport_offline_after_restart_still_recovers_via_rish(monkeypatch, tmp_path):
    """Review finding 5: through the real gate, a transport that is offline
    before and just after the rish restart must reach a uid-2000 shell with
    rish issued once, and leave no back-off marker."""
    import stayturgid_shell

    phone = _FakePhone()
    monkeypatch.setattr(stayturgid_shell, "STG", str(tmp_path / ".stayturgid"))
    monkeypatch.setattr(stayturgid_shell, "_boot_epoch", lambda: None, raising=False)
    monkeypatch.setattr(stayturgid_shell, "run", phone.adb)
    monkeypatch.setattr(start_adb.time, "sleep", phone.sleep)
    monkeypatch.setattr(start_adb.os, "access", lambda *args, **kwargs: True)

    def fake_capture(command, **_kwargs):
        if command[0] == start_adb.RISH:
            return 0, "2000\n"
        return (0, "2000\n") if phone.state() == "device" else (1, "error: device offline\n")

    def fake_run(command, **_kwargs):
        if command[0] == start_adb.RISH and "ctl.restart adbd" in command[-1]:
            phone.restart_adbd()
        return 0

    monkeypatch.setattr(start_adb, "_capture", fake_capture)
    monkeypatch.setattr(start_adb, "_run", fake_run)

    command, name = start_adb._shell_transport()

    assert (command, name) == (["adb", "-s", "localhost:5555", "shell"], "localhost-adb-rish-recovered")
    assert phone.restarts == 1
    assert not os.path.exists(stayturgid_shell.adb_auth_marker())


def test_launch_accepts_listener_after_client_timeout(monkeypatch):
    monkeypatch.setattr(start_adb, "_shell_run", lambda *args, **kwargs: (0, "localhost-adb"))
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: -1)
    monkeypatch.setattr(start_adb, "_firerpa_alive", lambda: True)
    monkeypatch.setattr(start_adb.time, "sleep", lambda *_: None)
    messages = []
    monkeypatch.setattr(start_adb, "_boot_log", messages.append)

    assert start_adb._launch_firerpa_via_shell("test") is True
    assert any("confirmed" in message for message in messages)


def test_launch_uses_accessibility_coexistence_lifecycle(monkeypatch):
    commands = []
    monkeypatch.setattr(start_adb, "_shell_run", lambda *args, **kwargs: (0, "localhost-adb"))
    monkeypatch.setattr(
        start_adb,
        "_run",
        lambda command, **_kwargs: commands.append(command) or 0,
    )
    messages = []
    monkeypatch.setattr(start_adb, "_boot_log", messages.append)

    assert start_adb._launch_firerpa_via_shell("test") is True
    assert commands[0][:2] == [sys.executable, start_adb.FIRERPA_LIFECYCLE]
    assert "--adb-target" in commands[0]
    assert "launch.sh" not in commands[0]
    assert any("accessibility coexistence" in message for message in messages)


def test_rotate_logs_caps_oversized_files(monkeypatch, tmp_path):
    """Oversized logs rotate to .1; small ones and the newest .1 are preserved."""
    stg_logs = tmp_path / "home" / ".stayturgid" / "logs"
    sd_logs = tmp_path / "sd" / "logs"
    stg_logs.mkdir(parents=True)
    sd_logs.mkdir(parents=True)
    monkeypatch.setattr(start_adb, "STG", str(stg_logs.parent))
    monkeypatch.setattr(start_adb, "SD", str(sd_logs.parent))
    monkeypatch.setenv("STAYTURGID_LOG_MAX_BYTES", "100")

    big = stg_logs / "repair-cfengine.log"
    small = stg_logs / "boot.log"
    mirrored = sd_logs / "watchdog.jsonl"
    big.write_text("x" * 500)
    small.write_text("y" * 10)
    mirrored.write_text("z" * 500)

    start_adb._rotate_logs()

    assert not big.exists()
    assert (stg_logs / "repair-cfengine.log.1").read_text() == "x" * 500
    assert small.read_text() == "y" * 10
    assert (sd_logs / "watchdog.jsonl.1").read_text() == "z" * 500

    # One generation only: a second rotation replaces .1 rather than making .1.1.
    big.write_text("n" * 500)
    start_adb._rotate_logs()
    assert (stg_logs / "repair-cfengine.log.1").read_text() == "n" * 500
    assert not (stg_logs / "repair-cfengine.log.1.1").exists()


def test_rotate_logs_disabled_by_zero_cap(monkeypatch, tmp_path):
    stg_logs = tmp_path / "home" / ".stayturgid" / "logs"
    stg_logs.mkdir(parents=True)
    monkeypatch.setattr(start_adb, "STG", str(stg_logs.parent))
    monkeypatch.setattr(start_adb, "SD", str(tmp_path / "missing"))
    monkeypatch.setenv("STAYTURGID_LOG_MAX_BYTES", "0")

    big = stg_logs / "repair.log"
    big.write_text("x" * 500)
    start_adb._rotate_logs()

    assert big.read_text() == "x" * 500


def test_try_sv_up_sshd_requires_sv_and_service_dir(monkeypatch, tmp_path):
    """No sv binary or no sshd service dir → False, caller starts sshd bare."""
    monkeypatch.setattr(start_adb, "PREFIX", str(tmp_path))
    assert start_adb.try_sv_up_sshd() is False


def test_try_sv_up_sshd_starts_runsvdir_then_sv_up(monkeypatch, tmp_path):
    prefix = tmp_path
    (prefix / "bin").mkdir()
    sv = prefix / "bin" / "sv"
    sv.write_text("#!/bin/sh\n")
    sv.chmod(0o755)
    (prefix / "var" / "service" / "sshd").mkdir(parents=True)
    monkeypatch.setattr(start_adb, "PREFIX", str(prefix))

    calls = []

    class _Result:
        def __init__(self, rc):
            self.returncode = rc

    def fake_run(cmd, **kwargs):
        calls.append(("run", cmd, kwargs.get("env")))
        if cmd[:2] == ["pgrep", "-f"] and "unsvdir" in cmd[2]:
            return _Result(1)  # runsvdir not running yet
        return _Result(0)

    bg = []
    monkeypatch.setattr(start_adb.subprocess, "run", fake_run)
    monkeypatch.setattr(start_adb, "_run_bg", lambda cmd, log_path=None: bg.append(cmd) or 0)
    monkeypatch.setattr(start_adb.time, "sleep", lambda s: None)

    assert start_adb.try_sv_up_sshd() is True
    assert bg == [["runsvdir", str(prefix / "var" / "service")]]
    sv_calls = [c for c in calls if c[1][0] == str(sv)]
    assert sv_calls and sv_calls[0][1][1:] == ["up", "sshd"]
    assert sv_calls[0][2]["SVDIR"] == str(prefix / "var" / "service")


def test_startup_sshd_prefers_sv_over_bare_start(monkeypatch, tmp_path):
    monkeypatch.setattr(start_adb, "PREFIX", str(tmp_path))

    class _Result:
        def __init__(self, rc):
            self.returncode = rc

    monkeypatch.setattr(start_adb.subprocess, "run", lambda cmd, **kw: _Result(1))
    sv_used = []
    monkeypatch.setattr(start_adb, "try_sv_up_sshd", lambda: sv_used.append(True) or True)
    bare = []
    monkeypatch.setattr(start_adb, "_run_bg", lambda cmd, log_path=None: bare.append(cmd) or 0)
    monkeypatch.setattr(start_adb, "_boot_log", lambda msg: None)

    start_adb.startup_sshd()

    assert sv_used == [True]
    assert bare == []
