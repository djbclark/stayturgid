"""Unit tests for the fdroid_client lookup plugin (#59: timeout-wrap control-node adb calls).

See test_adb_device_lookup.py for why these live here rather than under the
collection's tests/unit/plugins/lookup/."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from conftest import REPO

MODULE_PATH = Path(REPO) / "ansible_collections/stayturgid/android_common/plugins/lookup/fdroid_client.py"
SPEC = importlib.util.spec_from_file_location("fdroid_client_lookup", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


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
            return 0, "package:com.looker.droidify\n", ""
        return 0, "", ""

    monkeypatch.setattr(mod, "_raw_run_command", fake_raw)

    lm = mod.LookupModule(loader=None, templar=SimpleNamespace(template=lambda x: x))
    result = lm.run(["dev"])

    assert result == ["com.looker.droidify/.MainActivity"]
    assert seen, "expected at least one wrapped adb call"
    assert all(cmd[0].endswith("timeout") and cmd[1] == "30" for cmd in seen), seen
