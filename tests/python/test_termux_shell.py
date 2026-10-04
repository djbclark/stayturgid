"""Unit tests for termux stayturgid_shell helpers (no device)."""

import fcntl
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "device", "termux", "py"))
import stayturgid_shell as sh


class FakeAdb:
    """Termux's adb server as the gate sees it: one localhost:5555 row."""

    def __init__(self, state="", after_connect=None, connect_rc=0, connect_out="connected to localhost:5555", alias=""):
        self.state = state
        self.after_connect = after_connect
        self.connect_rc = connect_rc
        self.connect_out = connect_out
        self.alias = alias
        self.calls = []

    def __call__(self, args, timeout=60, input_text=None):
        self.calls.append(list(args))
        sub = args[1] if len(args) > 1 else ""
        if sub == "devices":
            out = "List of devices attached\n"
            if self.alias:
                out += "127.0.0.1:5555\t%s\n" % self.alias
            if self.state:
                out += "localhost:5555\t%s\n" % self.state
            return subprocess.CompletedProcess(args, 0, out, "")
        if sub == "connect":
            if self.after_connect is not None:
                self.state = self.after_connect
            return subprocess.CompletedProcess(args, self.connect_rc, self.connect_out + "\n", "")
        if sub == "disconnect":
            if args[2:] == ["127.0.0.1:5555"]:
                self.alias = ""
            else:
                self.state = ""
            return subprocess.CompletedProcess(args, 0, "disconnected %s\n" % args[2], "")
        if sub == "-s":
            return subprocess.CompletedProcess(args, 0, "2000\n", "")
        return subprocess.CompletedProcess(args, 1, "", "unexpected")

    def verbs(self, verb):
        return [c for c in self.calls if len(c) > 1 and c[1] == verb]

    def mutating(self):
        return [c for c in self.calls if len(c) > 1 and c[1] in ("connect", "reconnect", "disconnect", "kill-server")]


@pytest.fixture
def gate(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "STG", str(tmp_path / ".stayturgid"))
    monkeypatch.setattr(sh, "ADB_AUTH_RETRY_SEC", 600)
    # Stamps here are small fake epochs; a real CLOCK_BOOTTIME would call them pre-boot.
    monkeypatch.setattr(sh, "_boot_epoch", lambda: None, raising=False)

    def install(fake):
        monkeypatch.setattr(sh, "run", fake)
        return fake

    return install


def _marker(stamp, state="unauthorized"):
    path = sh.adb_auth_marker()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("%d %s\n" % (stamp, state))


def test_gate_authorised_costs_no_connect(gate):
    fake = gate(FakeAdb(state="device"))
    _marker(1000)
    assert sh.adb_connect(now=1001) == "device"
    assert fake.mutating() == []
    assert not os.path.exists(sh.adb_auth_marker())


@pytest.mark.parametrize("state", ["unauthorized", "authorizing"])
def test_gate_pending_dialog_first_sighting_stands_down(gate, state):
    fake = gate(FakeAdb(state=state))
    assert sh.adb_connect(now=5000) == "waiting"
    assert fake.mutating() == []
    with open(sh.adb_auth_marker()) as f:
        assert f.read().split() == ["5000", state]


@pytest.mark.parametrize("state", ["offline", "connecting"])
def test_gate_offline_is_not_a_dialog_and_still_connects(gate, state):
    """offline/connecting is also an authorised transport mid adbd restart or
    a closed 5555: master's connect must run and no back-off may start, or
    repair skips the rish restart that reopens the port."""
    refused = "failed to connect to 'localhost:5555': Connection refused"
    fake = gate(FakeAdb(state=state, connect_rc=1, connect_out=refused))
    assert sh.adb_connect(now=5000) == "down"
    assert len(fake.verbs("connect")) == 1
    assert not os.path.exists(sh.adb_auth_marker())


def test_gate_offline_with_fresh_marker_still_connects(gate):
    fake = gate(FakeAdb(state="offline", after_connect="device"))
    _marker(5000)
    assert sh.adb_connect(now=5010) == "device"
    assert len(fake.verbs("connect")) == 1
    assert not os.path.exists(sh.adb_auth_marker())


def test_gate_pending_dialog_inside_backoff_stands_down(gate):
    fake = gate(FakeAdb(state="unauthorized"))
    _marker(5000)
    assert sh.adb_connect(now=5000 + 599) == "waiting"
    assert fake.mutating() == []


def test_gate_backoff_expiry_reraises_exactly_one_dialog(gate):
    fake = gate(
        FakeAdb(state="unauthorized", after_connect="unauthorized", connect_rc=1, connect_out="failed to authenticate")
    )
    _marker(5000)
    assert sh.adb_connect(now=5000 + 600) == "waiting"
    assert [c[1] for c in fake.mutating()] == ["disconnect", "connect"]
    with open(sh.adb_auth_marker()) as f:
        assert f.read().split()[0] == "5600"
    # The refreshed marker restarts the clock for every later caller.
    assert sh.adb_connect(now=5601) == "waiting"
    assert len(fake.verbs("connect")) == 1


def test_gate_absent_row_inside_backoff_still_connects(gate):
    """A marker alone is not a dialog: with no row listed, a closed port must
    come back "down" so repair restarts adbd, not wait out the back-off."""
    refused = "failed to connect to 'localhost:5555': Connection refused"
    fake = gate(FakeAdb(state="", connect_rc=1, connect_out=refused))
    _marker(5000)
    assert sh.adb_connect(now=5100) == "down"
    assert len(fake.verbs("connect")) == 1


def test_gate_absent_transport_connects_when_no_dialog_pending(gate):
    fake = gate(FakeAdb(state="", after_connect="device"))
    assert sh.adb_connect(now=5000) == "device"
    assert len(fake.verbs("connect")) == 1
    assert fake.verbs("disconnect") == []
    assert not os.path.exists(sh.adb_auth_marker())


def test_gate_connect_refused_is_down_without_backoff(gate):
    refused = "failed to connect to 'localhost:5555': Connection refused"
    fake = gate(FakeAdb(state="", connect_rc=1, connect_out=refused))
    assert sh.adb_connect(now=5000) == "down"
    assert not os.path.exists(sh.adb_auth_marker())
    assert sh.adb_connect(now=5001) == "down"
    assert len(fake.verbs("connect")) == 2


def test_gate_adb_missing_is_down(gate):
    gate(lambda args, timeout=60, input_text=None: None)
    assert sh.adb_connect(now=5000) == "down"


def test_gate_revoke_burst_raises_one_connection(gate):
    """The 2026-10-04 s24 shape: several callers inside a few seconds of a
    revoke. Only the first may offer Termux's key; the rest stand down."""
    fake = gate(
        FakeAdb(
            state="",
            after_connect="unauthorized",
            connect_rc=1,
            connect_out="failed to authenticate to localhost:5555",
        )
    )
    results = [sh.adb_connect(now=7000 + i) for i in range(4)]
    assert results == ["waiting"] * 4
    assert len(fake.verbs("connect")) == 1
    assert fake.verbs("disconnect") == []


def _hold_lock():
    path = sh.adb_auth_marker() + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    holder = open(path, "a")
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return holder


def test_gate_lock_held_elsewhere_with_dialog_up_stands_down(gate):
    fake = gate(FakeAdb(state="unauthorized"))
    with _hold_lock():
        assert sh.adb_connect(timeout=0, now=5000) == "waiting"
    assert fake.mutating() == []


def test_gate_lock_held_elsewhere_without_dialog_still_connects(gate):
    """A busy lock is not the user's dialog: a closed port still reports down."""
    refused = "failed to connect to 'localhost:5555': Connection refused"
    fake = gate(FakeAdb(state="", connect_rc=1, connect_out=refused))
    with _hold_lock():
        assert sh.adb_connect(timeout=0, now=5000) == "down"
    assert len(fake.verbs("connect")) == 1


def _break_state_dir():
    # A file where ~/.stayturgid/state should be: neither lock nor marker can be made.
    os.makedirs(sh.STG, exist_ok=True)
    with open(os.path.join(sh.STG, "state"), "w") as f:
        f.write("not a directory\n")


def test_gate_unusable_lock_file_is_not_waiting(gate):
    refused = "failed to connect to 'localhost:5555': Connection refused"
    fake = gate(FakeAdb(state="", connect_rc=1, connect_out=refused))
    _break_state_dir()
    assert sh.adb_connect(timeout=0, now=5000) == "down"
    assert len(fake.verbs("connect")) == 1


def test_gate_without_a_marker_never_stands_down_for_good(gate):
    """No marker can be kept, so nothing would ever re-raise a dismissed
    dialog: report down and let callers recover as they did before the gate."""
    fake = gate(
        FakeAdb(state="unauthorized", after_connect="unauthorized", connect_rc=1, connect_out="failed to authenticate")
    )
    _break_state_dir()
    assert sh.adb_connect(timeout=0, now=5000) == "down"
    assert sh.adb_connect(timeout=0, now=5001) == "down"
    assert len(fake.verbs("connect")) == 2


def test_gate_marker_from_before_this_boot_is_ignored(gate, monkeypatch):
    fake = gate(FakeAdb(state="unauthorized"))
    _marker(5000)
    monkeypatch.setattr(sh, "_boot_epoch", lambda: 5050.0, raising=False)
    assert sh.adb_connect(now=5100) == "waiting"
    assert fake.mutating() == []
    with open(sh.adb_auth_marker()) as f:
        assert f.read().split()[0] == "5100"


def test_gate_marker_cleared_once_the_dialog_is_accepted(gate):
    fake = gate(FakeAdb(state="unauthorized"))
    assert sh.adb_connect(now=5000) == "waiting"
    fake.state = "device"
    assert sh.adb_connect(now=5001) == "device"
    assert not os.path.exists(sh.adb_auth_marker())


def test_gate_retry_period_override_is_capped():
    env = dict(os.environ, STAYTURGID_ADB_AUTH_RETRY_SEC="99999999")
    code = "import stayturgid_shell as s; print(s.ADB_AUTH_RETRY_SEC)"
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.join(REPO, "device", "termux", "py"),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.stdout.strip() == "3600"


def test_gate_drops_the_loopback_alias_once(gate):
    """Pre-gate boot loops left a 127.0.0.1:5555 transport that adb re-dials
    on its own, raising its own dialog after a revoke."""
    fake = gate(FakeAdb(state="device", alias="device"))
    assert sh.adb_connect(now=5000) == "device"
    assert sh.adb_connect(now=5001) == "device"
    assert fake.verbs("disconnect") == [["adb", "disconnect", "127.0.0.1:5555"]]
    assert fake.verbs("connect") == []


def test_shell_skips_adb_shell_while_waiting(gate, monkeypatch):
    fake = gate(FakeAdb(state="unauthorized"))
    monkeypatch.setattr(sh, "_ensure_env", lambda: None)
    assert sh.shell("id", "-u") == (1, "")
    assert fake.verbs("-s") == []


def test_shell_runs_when_authorised(gate, monkeypatch):
    gate(FakeAdb(state="device"))
    monkeypatch.setattr(sh, "_ensure_env", lambda: None)
    assert sh.shell("id", "-u") == (0, "2000\n")


def test_cli_reports_waiting(gate, monkeypatch, capsys):
    gate(FakeAdb(state="unauthorized"))
    monkeypatch.setattr(sh, "_ensure_env", lambda: None)
    assert sh.main(["adb-connect"]) == 2
    out, err = capsys.readouterr()
    assert out.strip() == "waiting"
    assert sh.ADB_AUTH_WAITING_MSG in err


def test_cli_reports_device(gate, monkeypatch, capsys):
    gate(FakeAdb(state="device"))
    monkeypatch.setattr(sh, "_ensure_env", lambda: None)
    assert sh.main(["adb-connect"]) == 0
    assert capsys.readouterr().out.strip() == "device"


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
    sys.path.insert(0, os.path.join(REPO, "device", "termux", "py"))
    import stayturgid_screen_control as sc

    assert sc.is_input_command(["input", "tap", "1", "2"])
    assert not sc.is_input_command(["uiautomator", "dump", "/x"])
