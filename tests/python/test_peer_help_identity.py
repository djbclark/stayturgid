"""#328: both peer-help adb helpers verify the target's ro.serialno before acting (fail closed)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import fire_peer_help as fph
import stayturgid_peer_help as dph

SERIAL = "HD8SERIAL1"
TARGET = "192.0.2.13:5555"


def _fake_adb(serial_reply, rc=0):
    """Stand-in for ``_adb``: records argv, answers ro.serialno with ``serial_reply``."""
    calls: list[tuple[str, ...]] = []

    def adb(*args, timeout=45):
        calls.append(args)
        if args[-2:] == ("getprop", "ro.serialno"):
            return subprocess.CompletedProcess(["adb", *args], rc, serial_reply, "")
        return subprocess.CompletedProcess(["adb", *args], 0, "", "")

    return adb, calls


MODULES = pytest.mark.parametrize("module", [fph, dph], ids=["mac", "device"])


@MODULES
def test_matching_serial_passes_and_stays_connected(monkeypatch, module):
    adb, calls = _fake_adb(SERIAL + "\r\n")
    monkeypatch.setattr(module, "_adb", adb)
    module.verify_identity(TARGET, SERIAL)
    assert ("-s", TARGET, "shell", "getprop", "ro.serialno") in calls
    assert not any(c[0] == "disconnect" for c in calls)


@MODULES
@pytest.mark.parametrize(
    "reply, rc, why",
    [
        ("OTHERPHONE\n", 0, "OTHERPHONE"),
        ("", 0, "could not read"),
        ("", 1, "could not read"),
        (SERIAL, 1, "could not read"),
    ],
)
def test_mismatch_or_unreadable_serial_disconnects_and_refuses(monkeypatch, module, reply, rc, why):
    adb, calls = _fake_adb(reply, rc)
    monkeypatch.setattr(module, "_adb", adb)
    with pytest.raises(SystemExit, match=why):
        module.verify_identity(TARGET, SERIAL)
    assert ("disconnect", TARGET) in calls


@MODULES
@pytest.mark.parametrize("serial", [None, "", "-", "a b", "x;rm -rf /", "--version"])
def test_unknown_or_malformed_requester_serial_refuses_without_reading_the_device(monkeypatch, module, serial):
    adb, calls = _fake_adb(SERIAL)
    monkeypatch.setattr(module, "_adb", adb)
    with pytest.raises(SystemExit, match="no valid requester USB serial"):
        module.verify_identity(TARGET, serial)
    assert not any(c[-2:] == ("getprop", "ro.serialno") for c in calls)
    assert ("disconnect", TARGET) in calls


def _entry(module, verb="shizuku-start", serial=SERIAL):
    if module is fph:
        return lambda: fph.run_verb(verb, TARGET, 9012, serial)
    return lambda: dph.main([verb, "--target", TARGET, "--serial", serial, "--port", "9012"])


@MODULES
@pytest.mark.parametrize("verb", ["handsets-start", "shizuku-start", "ping", "status"])
def test_no_verb_acts_on_a_target_that_fails_the_identity_check(monkeypatch, module, verb):
    adb, calls = _fake_adb("OTHERPHONE")
    monkeypatch.setattr(module, "_adb", adb)
    monkeypatch.setattr(module, "_ensure_connected", lambda target, timeout=20: None)
    for name in ("cmd_ping", "cmd_status", "cmd_handsets_start", "cmd_shizuku_start", "_shell", "_push_jar"):
        monkeypatch.setattr(module, name, lambda *a, **k: pytest.fail("a verb ran on the wrong device"))
    with pytest.raises(SystemExit, match="OTHERPHONE"):
        _entry(module, verb)()
    assert ("disconnect", TARGET) in calls


@MODULES
def test_a_verified_target_reaches_the_verb(monkeypatch, module):
    adb, _ = _fake_adb(SERIAL)
    monkeypatch.setattr(module, "_adb", adb)
    monkeypatch.setattr(module, "_ensure_connected", lambda target, timeout=20: None)
    monkeypatch.setattr(module, "cmd_shizuku_start", lambda target: 0)
    assert _entry(module)() == 0


def test_device_helper_requires_serial_on_the_command_line():
    with pytest.raises(SystemExit) as exc:
        dph.main(["ping", "--target", TARGET])
    assert exc.value.code == 2


def test_device_helper_reads_the_forcecommand_arguments_from_the_environment(monkeypatch):
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "status --target %s --serial %s --port 9012" % (TARGET, SERIAL))
    adb, _ = _fake_adb(SERIAL)
    monkeypatch.setattr(dph, "_adb", adb)
    monkeypatch.setattr(dph, "_ensure_connected", lambda target, timeout=20: None)
    seen = []
    monkeypatch.setattr(dph, "cmd_status", lambda target: seen.append(target) or 0)
    assert dph.main() == 0
    assert seen == [TARGET]


def test_device_helper_force_command_without_serial_is_refused(monkeypatch):
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "status --target %s --port 9012" % TARGET)
    monkeypatch.setattr(dph, "_adb", lambda *a, **k: pytest.fail("no adb before the arguments are valid"))
    with pytest.raises(SystemExit) as exc:
        dph.main()
    assert exc.value.code == 2
