"""Unit tests for the android_packages lookup plugin (#59: timeout-wrap control-node adb calls).

See test_adb_device_lookup.py for why these live here rather than under the
collection's tests/unit/plugins/lookup/."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from conftest import REPO

MODULE_PATH = Path(REPO) / "ansible_collections/stayturgid/android_common/plugins/lookup/android_packages.py"
SPEC = importlib.util.spec_from_file_location("android_packages_lookup", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_target_from_cmd_extracts_serial():
    assert mod._target_from_cmd(["adb", "-s", "SERIAL123", "shell", "pm list packages --user 0"]) == "SERIAL123"
    assert mod._target_from_cmd(["adb", "connect", "192.0.2.9:5555"]) == "192.0.2.9:5555"
    # timeout-prefixed variant must resolve the same way
    assert (
        mod._target_from_cmd(["/usr/bin/timeout", "30", "adb", "-s", "SERIAL123", "shell", "pm list packages"])
        == "SERIAL123"
    )


def test_raw_run_command_announces_using_before_run_and_free_after(monkeypatch, capsys):
    """Assert strict ordering, not just presence: USING must already be on
    stderr by the time the actual subprocess call happens, and FREE must
    not appear until after it returns."""

    def fake_run(cmd, capture_output, text, check):
        mid_call_err = capsys.readouterr().err
        assert "USING — SERIAL123" in mid_call_err, mid_call_err
        assert "FREE — SERIAL123" not in mid_call_err, mid_call_err
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    mod._raw_run_command(["adb", "-s", "SERIAL123", "shell", "pm list packages --user 0"])

    after_call_err = capsys.readouterr().err
    assert "USING — SERIAL123" not in after_call_err, after_call_err
    assert "FREE — SERIAL123" in after_call_err, after_call_err


def test_run_command_wraps_with_timeout(monkeypatch):
    seen = []
    monkeypatch.setattr(mod, "_raw_run_command", lambda cmd: seen.append(cmd) or (0, "", ""))

    rc, out, err = mod._run_command(["adb", "-s", "dev", "shell", "pm list packages --user 0"])

    assert rc == 0
    assert len(seen) == 1
    wrapped = seen[0]
    assert wrapped[0].endswith("timeout"), wrapped
    assert wrapped[1] == "30", wrapped
    assert wrapped[2:] == ["adb", "-s", "dev", "shell", "pm list packages --user 0"], wrapped


def test_lookup_module_uses_wrapped_run_command(monkeypatch):
    """End-to-end: LookupModule.run() must funnel through the new
    timeout-wrapping _run_command, not a raw unwrapped subprocess call —
    regression test for #59's originally-reported gap in this file."""
    seen = []

    def fake_raw(cmd):
        seen.append(cmd)
        joined = " ".join(cmd)
        if "pm list packages" in joined:
            return 0, "package:com.example.app\npackage:com.example.other\n", ""
        return 0, "", ""

    monkeypatch.setattr(mod, "_raw_run_command", fake_raw)

    lm = mod.LookupModule(loader=None, templar=SimpleNamespace(template=lambda x: x))
    result = lm.run(["dev"])

    assert result == ["com.example.app", "com.example.other"]
    assert seen, "expected at least one wrapped adb call"
    assert all(cmd[0].endswith("timeout") and cmd[1] == "30" for cmd in seen), seen
