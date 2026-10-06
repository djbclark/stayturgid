"""ShizukuTendCF r2842+ owns wireless debugging: repair hands off instead of writing adb_wifi_enabled.

Covers the Termux repair pass (device/termux/py/stayturgid_repair.py) and the
Mac Fire helper (control/bin/fire_help_monitor.py). Fakes only, no device.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fire_help_monitor as fhm  # noqa: E402
from test_stayturgid_repair import _gated, _main_with_closed_shell, _no_bare_adb_connect, repair  # noqa: E402

PUT = "settings put global adb_wifi_enabled 1"
GET = "settings get global adb_wifi_enabled"

VERSIONS = [
    ("    versionName=ShizukuTendCF 13.7.0.r2842\n", 2842),
    ("    versionName=ShizukuTendCF 13.7.0.r2846\n", 2846),
    ("    versionName=ShizukuTendCF 13.7.0.r2841\n", 2841),
    ('Broadcast completed: result=1, data="running (binder=true, v ShizukuTendCF 13.7.0.r2900)"', 2900),
    ("result=1 data=vShizukuTendCF 13.7.0.r3001)", 3001),
    # Upstream Shizuku and other builds: an .rNNNN, but not ShizukuTendCF.
    ("    versionName=13.5.4.r1049.0e53409\n", None),
    ("    versionName=Shizuku+ 13.6.0.r3000\n", None),
    ("", None),
    (None, None),
    ("Unable to find package: moe.shizuku.privileged.api\n", None),
]


@pytest.mark.parametrize(("text", "want"), VERSIONS)
def test_revision_parse_both_sides_agree(text, want):
    assert repair.shizuku_tendcf_revision(text) == want
    assert fhm.shizuku_tendcf_revision(text) == want


def test_gate_threshold():
    assert repair.SHIZUKU_OWNS_WIFI_RESTORE_REVISION == fhm.SHIZUKU_OWNS_WIFI_RESTORE_REVISION == 2842
    assert repair.app_owns_wireless_restore(2842)
    assert repair.app_owns_wireless_restore(2900)
    assert not repair.app_owns_wireless_restore(2841)
    assert not repair.app_owns_wireless_restore(None)


# --- Termux repair: ensure_wireless_debugging ---


class _Shell:
    """uid-2000 shell with the toggle off and a given versionName."""

    def __init__(self, version_out, version_rc=0, toggle="0"):
        self.version_out = version_out
        self.version_rc = version_rc
        self.toggle = toggle
        self.cmds = []

    def __call__(self, cmd, timeout=15):
        self.cmds.append(cmd)
        if cmd == GET:
            return 0, self.toggle + "\n"
        if cmd == PUT:
            self.toggle = "1"
            return 0, ""
        if "dumpsys package" in cmd and "versionName" in cmd:
            return self.version_rc, self.version_out
        if "HEADLESS_START" in cmd:
            return 0, 'Broadcast completed: result=0, data="STARTING"\n'
        return 0, ""

    def starts(self):
        return [c for c in self.cmds if "HEADLESS_START" in c]


@pytest.fixture
def termux(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr(repair, "WIFI_HANDOFF_STAMP", str(tmp_path / "state" / "wireless-debug-handoff"))
    monkeypatch.setattr(repair, "log", lambda msg, level=repair.INFO: logs.append((msg, level)))
    monkeypatch.setattr(repair.time, "sleep", lambda *_: None)
    _gated(monkeypatch, "device")
    _no_bare_adb_connect(monkeypatch)
    return logs


def test_app_owned_build_hands_off_and_never_writes(monkeypatch, termux):
    shell = _Shell("    versionName=ShizukuTendCF 13.7.0.r2842\n")
    monkeypatch.setattr(repair, "sh_adb", shell)

    assert repair.ensure_wireless_debugging() == "app"
    assert PUT not in shell.cmds
    assert len(shell.starts()) == 1
    start = shell.starts()[0]
    assert "moe.shizuku.privileged.api.HEADLESS_START" in start
    assert "force" not in start
    assert any("handed to ShizukuTendCF r2842" in msg for msg, _level in termux)


def test_app_owned_hand_off_is_rate_limited(monkeypatch, termux):
    shell = _Shell("    versionName=ShizukuTendCF 13.7.0.r2850\n")
    monkeypatch.setattr(repair, "sh_adb", shell)
    clock = [1_000_000.0]
    monkeypatch.setattr(repair.time, "time", lambda: clock[0])

    assert repair.ensure_wireless_debugging() == "app"
    clock[0] += 300
    assert repair.ensure_wireless_debugging() == "app"
    assert len(shell.starts()) == 1
    clock[0] += 301
    assert repair.ensure_wireless_debugging() == "app"
    assert len(shell.starts()) == 2
    assert PUT not in shell.cmds


@pytest.mark.parametrize(
    ("version_out", "version_rc"),
    [
        ("    versionName=ShizukuTendCF 13.7.0.r2841\n", 0),
        ("    versionName=13.5.4.r1049.0e53409\n", 0),
        ("", 1),
        ("garbage\n", 0),
    ],
)
def test_older_or_other_builds_keep_writing(monkeypatch, termux, version_out, version_rc):
    shell = _Shell(version_out, version_rc)
    monkeypatch.setattr(repair, "sh_adb", shell)

    assert repair.ensure_wireless_debugging() == "repaired"
    assert PUT in shell.cmds
    assert shell.starts() == []


def test_toggle_already_on_reads_no_version(monkeypatch, termux):
    shell = _Shell("    versionName=ShizukuTendCF 13.7.0.r2842\n", toggle="1")
    monkeypatch.setattr(repair, "sh_adb", shell)

    assert repair.ensure_wireless_debugging() == "up"
    assert shell.cmds == [GET]


# --- Termux repair: main()'s write after a HEADLESS_START (profile step) ---


class _OpenShellPhone:
    """Privileged shell up, toggle on, Shizuku down so repair sends HEADLESS_START."""

    def __init__(self, version_out):
        self.shell = _Shell(version_out, toggle="1")

    def install(self, monkeypatch, tmp_path):
        _gated(monkeypatch, "device")
        return _no_bare_adb_connect(monkeypatch)

    def sleep(self, *_):
        return None

    def sh_adb(self, cmd, timeout=15):
        if cmd == "id -u":
            return 0, "2000\n"
        if "HEADLESS_STATUS" in cmd:
            self.shell.cmds.append(cmd)
            return 0, "Broadcast completed: result=2\n"
        if cmd.startswith("pgrep"):
            return 1, ""
        if "shizuku-fleet.json" in cmd:
            return 0, "ok\n"
        return self.shell(cmd, timeout)


@pytest.mark.parametrize(
    ("version_out", "writes"),
    [
        ("    versionName=ShizukuTendCF 13.7.0.r2842\n", False),
        ("    versionName=ShizukuTendCF 13.7.0.r2800\n", True),
        ("    versionName=13.5.4.r1049.0e53409\n", True),
    ],
)
def test_main_start_sent_write_is_gated(monkeypatch, tmp_path, version_out, writes):
    phone = _OpenShellPhone(version_out)
    _rc, _ran, _logs, statuses = _main_with_closed_shell(monkeypatch, tmp_path, None, phone=phone)

    assert phone.shell.starts(), "repair should have sent HEADLESS_START for a down server"
    assert (PUT in phone.shell.cmds) is writes
    assert "shizuku_profile=applied" in statuses[-1]


# --- Mac Fire helper: fire_help_monitor.ensure_wireless_debugging ---


class _FireShell:
    def __init__(self, version_out, toggle="0"):
        self.version_out = version_out
        self.toggle = toggle
        self.cmds = []

    def __call__(self, target, cmd, timeout=30):
        self.cmds.append(cmd)
        out = ""
        if cmd == GET:
            out = self.toggle + "\n"
        elif cmd == PUT:
            self.toggle = "1"
        elif "dumpsys package" in cmd:
            out = self.version_out
        elif "HEADLESS_START" in cmd:
            out = "Broadcast completed: result=0\n"
        return subprocess.CompletedProcess([cmd], 0, out, "")

    def starts(self):
        return [c for c in self.cmds if "HEADLESS_START" in c]


@pytest.fixture
def fire(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr(fhm, "WIFI_HANDOFF_DIR", tmp_path / "handoff")
    monkeypatch.setattr(fhm, "log", logs.append)
    monkeypatch.setattr(fhm.time, "sleep", lambda *_: None)
    monkeypatch.setattr(fhm.fph, "_ensure_connected", lambda *_a, **_k: None)
    return logs


def test_fire_app_owned_build_hands_off_rate_limited(monkeypatch, fire):
    shell = _FireShell("    versionName=ShizukuTendCF 13.7.0.r2842\n")
    monkeypatch.setattr(fhm.fph, "_shell", shell)
    clock = [5_000_000.0]
    monkeypatch.setattr(fhm.time, "time", lambda: clock[0])

    assert fhm.ensure_wireless_debugging("192.0.2.13:5555", "fireos-device") == "app"
    clock[0] += 599
    assert fhm.ensure_wireless_debugging("192.0.2.13:5555", "fireos-device") == "app"
    assert len(shell.starts()) == 1
    clock[0] += 2
    assert fhm.ensure_wireless_debugging("192.0.2.13:5555", "fireos-device") == "app"
    assert len(shell.starts()) == 2
    assert PUT not in shell.cmds
    assert all("force" not in c for c in shell.starts())
    assert any("handed to ShizukuTendCF r2842" in line for line in fire)


@pytest.mark.parametrize(
    "version_out",
    ["    versionName=ShizukuTendCF 13.7.0.r2841\n", "    versionName=13.5.4.r1049.0e53409\n", ""],
)
def test_fire_older_or_other_builds_keep_writing(monkeypatch, fire, version_out):
    shell = _FireShell(version_out)
    monkeypatch.setattr(fhm.fph, "_shell", shell)

    assert fhm.ensure_wireless_debugging("192.0.2.13:5555", "fireos-device") == "repaired"
    assert PUT in shell.cmds
    assert shell.starts() == []
