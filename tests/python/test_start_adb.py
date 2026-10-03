"""Unit tests for the Python Termux boot supervisor."""

from __future__ import annotations

import sys
from pathlib import Path

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
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(start_adb, "_capture", lambda *args, **kwargs: (0, "2000\n"))

    command, name = start_adb._shell_transport()

    assert command == ["adb", "-s", "localhost:5555", "shell"]
    assert name == "localhost-adb"


def test_shell_transport_falls_back_to_rish(monkeypatch):
    responses = iter([(-1, ""), (0, "Entering shell...\n2000\n"), (0, "2000\n")])
    monkeypatch.setattr(start_adb, "_run", lambda *args, **kwargs: 0)
    monkeypatch.setattr(start_adb, "_capture", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(start_adb.os, "access", lambda *args, **kwargs: True)

    command, name = start_adb._shell_transport()

    assert command == ["adb", "-s", "localhost:5555", "shell"]
    assert name == "localhost-adb-rish-recovered"


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
        if cmd[:2] == ["pgrep", "-x"]:
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
