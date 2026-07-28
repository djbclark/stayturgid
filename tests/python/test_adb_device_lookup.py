"""Unit tests for the adb_device lookup plugin (#59: timeout-wrap control-node adb calls).

Lives here rather than under the collection's tests/unit/plugins/lookup/ —
ansible-test units categorizes lookup plugins as "controller" tests, and this
repo's --local ansible-test invocation currently mis-builds
ANSIBLE_COLLECTIONS_PATH as a colon-joined multi-path string for that
category (a pre-existing ansible-test harness gap never triggered before,
since no controller-category unit test existed in this collection until
now). Matches the established script-twin convention already used for
other module_utils files (e.g. test_adb_resolve.py exists both here and
under the collection)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from conftest import REPO

MODULE_PATH = Path(REPO) / "ansible_collections/stayturgid/android_common/plugins/lookup/adb_device.py"
SPEC = importlib.util.spec_from_file_location("adb_device_lookup", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_target_from_cmd_extracts_serial_and_endpoint():
    assert mod._target_from_cmd(["adb", "-s", "SERIAL123", "shell", "getprop"]) == "SERIAL123"
    assert mod._target_from_cmd(["adb", "connect", "192.0.2.9:5555"]) == "192.0.2.9:5555"
    assert mod._target_from_cmd(["adb", "devices"]) == "control-node adb"
    assert mod._target_from_cmd(["adb", "mdns", "services"]) == "control-node adb"
    # timeout-prefixed variants must resolve the same way
    assert mod._target_from_cmd(["/usr/bin/timeout", "30", "adb", "-s", "SERIAL123", "shell", "x"]) == "SERIAL123"


def test_raw_run_command_announces_before_and_after(monkeypatch, capsys):
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda cmd, capture_output, text, check: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    mod._raw_run_command(["adb", "-s", "SERIAL123", "shell", "getprop"])

    err = capsys.readouterr().err
    assert "USING — SERIAL123" in err
    assert "FREE — SERIAL123" in err


def test_run_command_wraps_with_timeout(monkeypatch):
    seen = []
    monkeypatch.setattr(mod, "_raw_run_command", lambda cmd: seen.append(cmd) or (0, "", ""))

    rc, out, err = mod._run_command(["adb", "devices"])

    assert rc == 0
    assert len(seen) == 1
    wrapped = seen[0]
    assert wrapped[0].endswith("timeout"), wrapped
    assert wrapped[1] == "30", wrapped
    assert wrapped[2:] == ["adb", "devices"], wrapped


def test_run_command_does_not_double_wrap_an_already_wrapped_cmd(monkeypatch):
    """The double-wrap guard must recognize an incoming cmd that's already
    prefixed (the real call pattern here, since resolve_adb() always wraps
    before invoking this function's outer caller)."""
    seen = []
    monkeypatch.setattr(mod, "_raw_run_command", lambda cmd: seen.append(cmd) or (0, "", ""))

    mod._run_command(["adb", "devices"])
    timeout_bin = seen[0][0]
    seen.clear()

    # Re-invoke with a cmd already prefixed with the same resolved binary the
    # first call used — resolve_adb() always wraps before invoking this
    # function's outer caller, so this is the real call pattern.
    mod._run_command([timeout_bin, "30", "adb", "devices"])

    assert seen == [[timeout_bin, "30", "adb", "devices"]], seen


def test_lookup_module_resolve_path_uses_wrapped_run_command(monkeypatch, tmp_path):
    """End-to-end: LookupModule.run() must still funnel through the new
    timeout-wrapping _run_command, not a raw unwrapped subprocess call —
    regression test for #59's originally-reported gap in this file."""
    seen = []

    def fake_raw(cmd):
        seen.append(cmd)
        joined = " ".join(cmd)
        if "devices" in joined:
            return 0, "EXAMPLE-SERIAL\tdevice\n", ""
        return 1, "", ""

    monkeypatch.setattr(mod, "_raw_run_command", fake_raw)

    conf = tmp_path / "devices.conf"
    conf.write_text("stock-android-device EXAMPLE-SERIAL 100.0.0.12 192.0.2.12\n")
    monkeypatch.setenv("STAYTURGID_DEVICES_CONF", str(conf))

    lm = mod.LookupModule(loader=None, templar=SimpleNamespace(template=lambda x: x))
    result = lm.run(["stock-android-device"])

    assert result == ["EXAMPLE-SERIAL"]
    assert seen, "expected at least one wrapped adb call"
    assert all(cmd[0].endswith("timeout") and cmd[1] == "30" for cmd in seen), seen
