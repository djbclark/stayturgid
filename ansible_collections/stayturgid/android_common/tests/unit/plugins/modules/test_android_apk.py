"""Unit tests for android_apk module."""

import json
import os
import sys
from hashlib import sha256

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import android_apk as mod
import apk_install


def test_parse_install_result_success():
    ok, reason = apk_install.parse_install_result("Performing Streamed Install\nSuccess\n")
    assert ok is True
    assert reason == "Success"


def test_parse_install_result_failure():
    ok, reason = apk_install.parse_install_result("Failure [INSTALL_FAILED_VERSION_DOWNGRADE]")
    assert ok is False
    assert "INSTALL_FAILED" in reason


def run_module(mocker, args, cmd_results=None, command_fn=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}
    warnings = []

    def fake_run_command(self, cmd, *a, **kw):
        if command_fn is not None:
            return command_fn(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        if "pm list packages" in joined:
            return (0, "", "")
        if "dumpsys package" in joined:
            return (1, "", "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    def fake_fail(self, **kw):
        captured.update(kw, failed=True)
        raise SystemExit(1)

    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.get_bin_path", lambda self, name, required=False: "/usr/bin/" + name
    )
    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fake_fail)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.warn",
        lambda self, msg: warnings.append(msg),
    )

    with pytest.raises(SystemExit):
        mod.main()
    captured["_warnings"] = warnings
    return captured


def test_android_apk_installs(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert out["reason"] == "Success"


def test_android_apk_disables_play_protect_verifier_around_install(mocker, tmp_path):
    """The install is wrapped in a verifier off/restore pair (unsafe-app dialog)."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "pm list packages" in joined:
            return (0, "", "")
        if "settings get global verifier_verify_adb_installs" in joined:
            return (0, "1\n", "")
        if "settings get global package_verifier_enable" in joined:
            return (0, "null\n", "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
        command_fn=command_fn,
    )
    assert out.get("failed") is not True, out
    install_idx = next(i for i, c in enumerate(seen) if " install" in c)
    disables = [i for i, c in enumerate(seen) if "settings put global" in c and " 0" in c]
    assert len(disables) == 2 and all(i < install_idx for i in disables), seen
    restore_put = [i for i, c in enumerate(seen) if "settings put global verifier_verify_adb_installs 1" in c]
    restore_delete = [i for i, c in enumerate(seen) if "settings delete global package_verifier_enable" in c]
    assert restore_put and restore_put[0] > install_idx, seen
    assert restore_delete and restore_delete[0] > install_idx, seen


def test_android_apk_restores_verifier_on_install_failure(mocker, tmp_path):
    """A failed install must still restore the Play Protect settings."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "pm list packages" in joined:
            return (0, "", "")
        if "settings get global" in joined:
            return (0, "1\n", "")
        if " install" in joined:
            return (1, "Failure [INSTALL_FAILED_INVALID_APK]", "")
        return (0, "", "")

    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
        command_fn=command_fn,
    )
    assert out.get("failed") is True
    restores = [c for c in seen if "settings put global" in c and c.rstrip().endswith(" 1")]
    assert len(restores) == 2, seen


def test_android_apk_accepts_locked_checksum(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            checksum="sha256:" + sha256(b"PK").hexdigest(),
            connect=False,
        ),
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is True


def test_android_apk_rejects_wrong_checksum(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            checksum="0" * 64,
            connect=False,
        ),
    )
    assert out.get("failed") is True
    assert "checksum mismatch" in out["msg"]


def test_android_apk_install_wrapped_in_timeout(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen_cmds = []

    def fake_run_command(self, cmd, *a, **kw):
        seen_cmds.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "", "")
        if "dumpsys package" in joined:
            return (1, "", "")
        if cmd[0].endswith("timeout"):
            return (0, "Success\n", "")
        return (0, "", "")

    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.get_bin_path", lambda self, name, required=False: "/usr/bin/" + name
    )
    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.exit_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(0))
    )
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(1))
    )

    stdin = json.dumps(
        {"ANSIBLE_MODULE_ARGS": dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False)}
    )
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    with pytest.raises(SystemExit):
        mod.main()

    # Match the adb install subcommand as a standalone argv element — a plain
    # substring check also matches the Play Protect verifier settings commands
    # (verifier_verify_adb_installs).
    install_cmds = [c for c in seen_cmds if isinstance(c, (list, tuple)) and "install" in c]
    assert len(install_cmds) == 1
    assert install_cmds[0][:3] == ["/usr/bin/timeout", "180", "adb"], install_cmds[0]


def test_android_apk_install_timeout_fails_loudly(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False),
        cmd_results=[(" install", (124, "", ""))],
    )
    assert out.get("failed") is True
    assert "timed out" in out["msg"]


def test_android_apk_work_profile_install_wrapped_in_timeout(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), work_profile=True, connect=False),
    )
    assert out.get("failed") is not True, out
    assert "also installed for user 10" in out["reason"]


def test_android_apk_work_profile_timeout_warns_with_dialog_hint(mocker, tmp_path):
    """Regression test for #59: a wedged work-profile install must warn with
    the same "confirmation dialog" hint as the primary install path, not just
    a bare rc number, and must not fail the whole task (best-effort)."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), work_profile=True, connect=False),
        cmd_results=[
            ("--user 10", (124, "", "")),
            (" install", (0, "Success\n", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert "also installed for user 10" not in out["reason"]
    assert any("timed out" in w and "confirmation dialog" in w for w in out["_warnings"]), out["_warnings"]


def test_android_apk_skips_when_present(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
        cmd_results=[
            ("pm list packages", (0, "package:com.example.app\n", "")),
        ],
    )
    assert out["changed"] is False


def test_android_apk_reinstalls_when_locked_version_is_stale(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            version_name="2.0.0",
            connect=False,
        ),
        cmd_results=[
            ("pm list packages", (0, "package:com.example.app\n", "")),
            ("dumpsys package", (0, "versionName=1.0.0\n", "")),
        ],
    )
    assert out["changed"] is True
    assert out["reason"] == "Success"


def _capture_commands(mocker, args):
    """Run the module recording every run_command invocation."""
    seen = []

    def fake_run_command(self, cmd, *a, **kw):
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")  # present
        if "dumpsys package" in joined:
            return (1, "", "")
        if "uninstall" in joined:
            return (0, "Success\n", "")
        if cmd[0].endswith("timeout"):
            return (0, "Success\n", "")
        return (0, "", "")

    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.get_bin_path", lambda self, name, required=False: "/usr/bin/" + name
    )
    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.exit_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(0))
    )
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(1))
    )
    with pytest.raises(SystemExit):
        mod.main()
    return [" ".join(c) if isinstance(c, (list, tuple)) else str(c) for c in seen]


def test_android_apk_clean_uninstalls_before_install(mocker, tmp_path):
    """clean=true on a present package uninstalls before installing."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    cmds = _capture_commands(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False, clean=True, force=True),
    )
    uninstall_idx = next((i for i, c in enumerate(cmds) if "uninstall com.example.app" in c), None)
    install_idx = next((i for i, c in enumerate(cmds) if " install -r" in c), None)
    assert uninstall_idx is not None, cmds
    assert install_idx is not None, cmds
    assert uninstall_idx < install_idx, cmds


@pytest.mark.parametrize(
    "uninstall_rc,uninstall_err",
    [
        (1, "Failure [DELETE_FAILED_INTERNAL_ERROR]"),
        (124, ""),
    ],
    ids=["failure", "timeout"],
)
def test_android_apk_clean_uninstall_failure_fails_before_install(mocker, tmp_path, uninstall_rc, uninstall_err):
    """A failed or timed-out clean uninstall must not silently proceed to installing.

    Regression test: run_command_with_timeout()'s clean-uninstall result was
    previously discarded entirely, so a failed/timed-out uninstall silently
    fell through into an in-place `adb install -r`, defeating the native-lib
    re-extraction the `clean` flag exists for (see the module's history with
    #60). Covers both an ordinary adb failure and an rc==124 timeout, since
    run_command_with_timeout() surfaces both the same way (nonzero rc)."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def fake_run_command(cmd):
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")
        if "dumpsys package" in joined:
            return (1, "", "")
        if "uninstall" in joined:
            return (uninstall_rc, "", uninstall_err)
        return (0, "", "")

    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False, clean=True, force=True),
        command_fn=fake_run_command,
    )

    assert out.get("failed") is True
    assert "clean reinstall" in out["msg"], out
    assert not any(" install -r" in " ".join(c) for c in seen), seen


def test_android_apk_clean_false_does_not_uninstall(mocker, tmp_path):
    """clean defaults off: a forced reinstall must not uninstall first."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    cmds = _capture_commands(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False, force=True),
    )
    assert not any("uninstall" in c for c in cmds), cmds


def test_android_apk_incompatible_upgrade_clean_retries(mocker, tmp_path):
    """A stale package from another signing lineage converges automatically."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []
    install_attempt = 0

    def fake_run_command(cmd):
        nonlocal install_attempt
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")
        if "dumpsys package" in joined:
            return (0, "versionName=1.0.0\n", "")
        if " uninstall " in f" {joined} ":
            return (0, "Success\n", "")
        if " install " in f" {joined} ":
            install_attempt += 1
            if install_attempt == 1:
                return (1, "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\n", "")
            return (0, "Success\n", "")
        return (0, "", "")

    captured = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            version_name="2.0.0",
            connect=False,
        ),
        command_fn=fake_run_command,
    )

    commands = [" ".join(command) for command in seen]
    assert sum(" install " in f" {command} " for command in commands) == 2
    assert sum(" uninstall " in f" {command} " for command in commands) == 1
    assert "clean fallback" in captured["reason"]
    assert any("application data will be lost" in warning for warning in captured["_warnings"])


def test_android_apk_incompatible_upgrade_can_fail_without_data_loss(mocker, tmp_path):
    """A caller can explicitly reject the destructive clean fallback."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def fake_run_command(cmd):
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")
        if "dumpsys package" in joined:
            return (0, "versionName=1.0.0\n", "")
        if " install " in f" {joined} ":
            return (1, "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\n", "")
        return (0, "", "")

    captured = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            version_name="2.0.0",
            clean_on_incompatible=False,
            connect=False,
        ),
        command_fn=fake_run_command,
    )

    commands = [" ".join(command) for command in seen]
    assert captured["failed"] is True
    assert not any(" uninstall " in f" {command} " for command in commands)


class FakeDownloadModule:
    """Just enough AnsibleModule for download_gh_release."""

    def __init__(self, tmpdir, run, bins=("gh", "aria2c")):
        self.tmpdir = str(tmpdir)
        self.bins = bins
        self.run = run
        self.params = {"download_timeout": 180}
        self.calls = []
        self.warnings = []

    def get_bin_path(self, name, required=False):
        return "/usr/bin/" + name if name in self.bins or name == "timeout" else None

    def run_command(self, cmd, *a, **kw):
        self.calls.append(cmd)
        return self.run(cmd)

    def warn(self, msg):
        self.warnings.append(msg)

    def fail_json(self, **kw):
        raise AssertionError(kw)


ASSETS = json.dumps({"assets": [{"name": "app-1.apk", "url": "https://example.invalid/app-1.apk"}]})


def tool(cmd, name):
    return any(str(part).endswith("/" + name) for part in cmd)


def test_download_gh_release_uses_aria2c(tmp_path, monkeypatch):
    monkeypatch.delenv("STAYTURGID_FETCH_SSH_HOST", raising=False)
    monkeypatch.delenv("STAYTURGID_REPO_ROOT", raising=False)
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(tmp_path))

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if tool(cmd, "aria2c"):
            assert "--continue=true" in cmd
            assert "--quiet" not in cmd
            assert not any(part.startswith("--lowest-speed-limit") for part in cmd)
            out = cmd[cmd.index("--dir") + 1]
            with open(os.path.join(out, cmd[cmd.index("--out") + 1]), "wb") as f:
                f.write(b"PK")
            return (0, "", "")
        raise AssertionError("unexpected %r" % cmd)

    module = FakeDownloadModule(tmp_path, run)
    path = mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert path.endswith("app-1.apk")
    assert not [c for c in module.calls if tool(c, "gh") and "download" in c]


def test_download_gh_release_does_not_abandon_a_failed_transfer(tmp_path, monkeypatch):
    monkeypatch.delenv("STAYTURGID_FETCH_SSH_HOST", raising=False)
    monkeypatch.delenv("STAYTURGID_REPO_ROOT", raising=False)
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(tmp_path))

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if tool(cmd, "aria2c"):
            dest = os.path.join(cmd[cmd.index("--dir") + 1], cmd[cmd.index("--out") + 1])
            with open(dest, "wb") as partial:
                partial.write(b"partial")
            return (1, "", "connection reset")
        raise AssertionError("unexpected %r" % cmd)

    module = FakeDownloadModule(tmp_path, run)
    with pytest.raises(AssertionError, match="download of app-1.apk failed") as raised:
        mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert "partial file was kept" in str(raised.value)
    assert "ADB" not in str(raised.value)
    assert not [c for c in module.calls if tool(c, "gh") and "download" in c]
    kept = list(tmp_path.rglob("app-1.apk"))
    assert kept and kept[0].read_bytes() == b"partial"


def test_download_gh_release_timeout_names_the_window(tmp_path, monkeypatch):
    monkeypatch.delenv("STAYTURGID_FETCH_SSH_HOST", raising=False)
    monkeypatch.delenv("STAYTURGID_REPO_ROOT", raising=False)
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(tmp_path))

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if tool(cmd, "aria2c"):
            return (124, "", "download timed out after 180s")
        raise AssertionError("unexpected %r" % cmd)

    module = FakeDownloadModule(tmp_path, run)
    with pytest.raises(AssertionError, match="did not finish within 180s") as raised:
        mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert "The transfer was stopped" in str(raised.value)
    assert "ADB" not in str(raised.value)


def _helper_tree(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    helper = root / "control" / "bin" / "fetch_asset.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/usr/bin/env python3\n")
    monkeypatch.setenv("STAYTURGID_REPO_ROOT", str(root))
    monkeypatch.setenv("STAYTURGID_FETCH_SSH_HOST", "vps-primary")
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(tmp_path / "cache"))
    return helper


def _writes_apk(cmd, payload):
    dest = cmd[cmd.index("--dest") + 1]
    with open(dest, "wb") as handle:
        handle.write(payload)
    return dest


def test_download_gh_release_uses_the_fetch_helper_when_configured(tmp_path, monkeypatch):
    _helper_tree(tmp_path, monkeypatch)

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if any(str(part).endswith("fetch_asset.py") for part in cmd):
            _writes_apk(cmd, b"PK")
            return (0, "", "")
        raise AssertionError("unexpected %r" % (cmd,))

    module = FakeDownloadModule(tmp_path, run)
    path = mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert path.endswith("app-1.apk")
    assert open(path, "rb").read() == b"PK"
    assert not [c for c in module.calls if tool(c, "aria2c")]
    assert not [c for c in module.calls if tool(c, "gh") and "download" in c]


def test_download_gh_release_helper_failure_is_not_retried(tmp_path, monkeypatch):
    _helper_tree(tmp_path, monkeypatch)

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if any(str(part).endswith("fetch_asset.py") for part in cmd):
            dest = _writes_apk(cmd, b"partial")
            return (1, "", "download of app-1.apk failed. The partial file was kept at %s" % dest)
        raise AssertionError("unexpected %r" % (cmd,))

    module = FakeDownloadModule(tmp_path, run)
    with pytest.raises(AssertionError, match="download of app-1.apk failed") as raised:
        mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert "partial file was kept" in str(raised.value)
    assert not [c for c in module.calls if tool(c, "aria2c")]
    assert not [c for c in module.calls if tool(c, "gh") and "download" in c]
    kept = list((tmp_path / "cache").rglob("app-1.apk"))
    assert kept and kept[0].read_bytes() == b"partial"


def test_download_gh_release_helper_timeout_names_the_window(tmp_path, monkeypatch):
    _helper_tree(tmp_path, monkeypatch)

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if any(str(part).endswith("fetch_asset.py") for part in cmd):
            return (124, "", "download timed out after 180s")
        raise AssertionError("unexpected %r" % (cmd,))

    module = FakeDownloadModule(tmp_path, run)
    with pytest.raises(AssertionError, match="did not finish within 180s") as raised:
        mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert "The transfer was stopped" in str(raised.value)
    assert not [c for c in module.calls if tool(c, "aria2c")]


# --- detached_install: an APK that carries the adb transport (Tailscale) ---

TS_DEVICE = "100.64.0.1:5555"
TS_LOG_PATH = "/data/local/tmp/stayturgid-com.tailscale.ipn.log"
TS_OK_LOG = "Performing Streamed Install\nSuccess\nstayturgid-pm-rc=0\n"


class DetachedDevice:
    """A fake device: offline for the first reads of the log, then the script's log."""

    def __init__(self, log, offline_reads=1, push_rc=0, version_after="2.0.0"):
        self.log = log
        self.offline_reads = offline_reads
        self.push_rc = push_rc
        self.version_after = version_after
        self.seen = []
        self.script_started = False
        self.done = False

    def __call__(self, cmd):
        joined = " ".join(cmd)
        self.seen.append(joined)
        if " push " in joined:
            return (self.push_rc, "", "" if self.push_rc == 0 else "adb: error: failed to copy")
        if "nohup" in joined:
            self.script_started = True
            return (0, "", "")
        if "cat " + TS_LOG_PATH in joined:
            if self.offline_reads > 0:
                self.offline_reads -= 1
                return (1, "", "error: device offline")
            self.done = True
            return (0, self.log, "")
        if "pm list packages" in joined:
            return (0, "package:com.tailscale.ipn\n", "")
        if "dumpsys package" in joined:
            return (0, "versionName=%s\n" % (self.version_after if self.done else "1.0.0"), "")
        if "settings get global verifier_verify_adb_installs" in joined:
            return (0, "1\n", "")
        if "settings get global package_verifier_enable" in joined:
            return (0, "null\n", "")
        return (0, "", "")


@pytest.fixture
def fake_clock(mocker):
    clock = {"t": 0}
    mocker.patch.object(mod, "_now", lambda: clock["t"])
    mocker.patch.object(mod, "_sleep", lambda seconds: clock.__setitem__("t", clock["t"] + seconds))
    return clock


def detached_args(tmp_path, **extra):
    apk = tmp_path / "ts.apk"
    apk.write_bytes(b"PK")
    return dict(
        device=TS_DEVICE,
        package="com.tailscale.ipn",
        apk_path=str(apk),
        version_name="2.0.0",
        detached_install=True,
        **extra,
    )


def test_detached_install_pushes_starts_script_and_survives_offline_read(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, offline_reads=1)
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert out["reason"] == "Success"

    seen = device.seen
    push = next(i for i, c in enumerate(seen) if " push " in c)
    assert seen[push].endswith("/data/local/tmp/stayturgid-com.tailscale.ipn.apk")
    start = next(i for i, c in enumerate(seen) if "nohup" in c)
    script = seen[start]
    assert push < start
    assert "pm install -r --user 0 /data/local/tmp/stayturgid-com.tailscale.ipn.apk" in script
    # The verifier goes off and back on inside the script, restored to its values from before.
    assert script.index("settings put global verifier_verify_adb_installs 0") < script.index("pm install")
    assert script.index("pm install") < script.index("settings put global verifier_verify_adb_installs 1")
    assert script.index("pm install") < script.index("settings delete global package_verifier_enable")
    assert "rm -f /data/local/tmp/stayturgid-com.tailscale.ipn.apk" in script
    # Nothing on the Mac side touches the verifier or runs a plain adb install.
    assert not [c for c in seen if "settings put" in c and "nohup" not in c]
    assert not [c for c in seen if " install " in c and "pm install" not in c]
    # Two log reads (offline, then ready), each preceded by a reconnect.
    reads = [i for i, c in enumerate(seen) if "cat " + TS_LOG_PATH in c]
    assert len(reads) == 2
    connects = [i for i, c in enumerate(seen) if " connect " in c and i > start]
    assert len(connects) >= 2
    assert any("rm -f " + TS_LOG_PATH in c for c in seen[reads[-1] :])
    assert fake_clock["t"] == mod.DETACHED_POLL_SECONDS


def test_detached_install_failure_log_fails(mocker, tmp_path, fake_clock):
    log = "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\nstayturgid-pm-rc=1\n"
    device = DetachedDevice(log, offline_reads=0)
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out["failed"] is True
    assert "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out["msg"]
    # No clean fallback in detached mode: nothing uninstalls the package.
    assert not [c for c in device.seen if "uninstall" in c]


def test_detached_install_downgrade_is_not_uninstalled(mocker, tmp_path, fake_clock):
    log = "Failure [INSTALL_FAILED_VERSION_DOWNGRADE]\nstayturgid-pm-rc=1\n"
    out = run_module(mocker, detached_args(tmp_path), command_fn=DetachedDevice(log, offline_reads=0))
    assert out["failed"] is True
    assert "newer com.tailscale.ipn" in out["msg"]


def test_detached_install_timeout_fails_with_message(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, offline_reads=10**6)
    out = run_module(mocker, detached_args(tmp_path, detached_timeout=20), command_fn=device)
    assert out["failed"] is True
    assert "device did not come back within 20 s" in out["msg"]
    assert "check versionName" in out["msg"]


def test_detached_install_wrong_version_after_success_fails(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, offline_reads=0, version_after="1.5.0")
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out["failed"] is True
    assert "1.5.0" in out["msg"] and "2.0.0" in out["msg"]


def test_detached_install_push_failure_never_starts_script(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, push_rc=1)
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out["failed"] is True
    assert "adb push failed" in out["msg"]
    assert device.script_started is False


@pytest.mark.parametrize("option", ["clean", "work_profile"])
def test_detached_install_refuses_unsupported_combinations(mocker, tmp_path, option):
    out = run_module(mocker, detached_args(tmp_path, **{option: True}))
    assert out["failed"] is True
    assert option in out["msg"]


def test_detached_script_runs_under_sh(tmp_path):
    """Run the rendered script against stub pm/settings: quoting and order hold."""
    import subprocess
    import time

    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (bindir / "pm").write_text('#!/bin/sh\necho "pm $*" >> %s/calls\necho Success\n' % state)
    (bindir / "settings").write_text('#!/bin/sh\necho "settings $*" >> %s/calls\n' % state)
    for stub in bindir.iterdir():
        stub.chmod(0o755)
    remote = tmp_path / "remote"
    remote.mkdir()
    script = mod.detached_script(
        "com.tailscale.ipn",
        "0",
        "com.android.vending",
        [],
        {"verifier_verify_adb_installs": "1", "package_verifier_enable": "null"},
    ).replace("/data/local/tmp", str(remote))
    (remote / "stayturgid-com.tailscale.ipn.apk").write_bytes(b"PK")
    env = dict(os.environ, PATH="%s:%s" % (bindir, os.environ["PATH"]))
    subprocess.run(["/bin/sh", "-c", script], env=env, check=True, timeout=10)
    log = remote / "stayturgid-com.tailscale.ipn.log"
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    text = log.read_text()
    assert mod.DETACHED_DONE_RE.search(text) and mod.DETACHED_DONE_RE.search(text).group(1) == "0"
    assert "Success" in text
    assert not (remote / "stayturgid-com.tailscale.ipn.apk").exists()
    calls = (state / "calls").read_text().splitlines()
    assert calls[0] == "settings put global verifier_verify_adb_installs 0"
    assert calls[2].startswith("pm install -r --user 0 -i com.android.vending ")
    assert calls[3:] == [
        "settings put global verifier_verify_adb_installs 1",
        "settings delete global package_verifier_enable",
    ]


def _releases(digest, draft_first=False):
    newest = {
        "tag_name": "nightly",
        "draft": False,
        "assets": [
            {"name": "termux-x11-universal-debug.apk", "digest": digest},
            {"name": "termux-x11-universal-sharedUid-debug.apk", "digest": "sha256:" + "1" * 64},
        ],
    }
    releases = [newest, {"tag_name": "1.02.07", "draft": False, "assets": []}]
    if draft_first:
        releases.insert(0, {"tag_name": "draft-x", "draft": True, "assets": []})
    return json.dumps(releases)


def _run_latest(mocker, tmp_path, monkeypatch, digest, device_sha, apk_bytes=b"PK", draft_first=False):
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(tmp_path / "cache"))
    downloads = []

    def fake_download(module, repo, pattern, tag):
        downloads.append((repo, pattern, tag))
        path = tmp_path / "dl.apk"
        path.write_bytes(apk_bytes)
        return str(path)

    monkeypatch.setattr(mod, "download_gh_release", fake_download)
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "api repos/termux/termux-x11/releases" in joined:
            return (0, _releases(digest, draft_first), "")
        if "pm list packages" in joined:
            return (0, "package:com.termux.x11\n", "")
        if "pm path" in joined:
            return (0, "package:/data/app/~~x/com.termux.x11-y/base.apk\n", "")
        if "sha256sum" in joined:
            return (0, "%s  /data/app/~~x/com.termux.x11-y/base.apk\n" % device_sha, "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.termux.x11",
            gh_repo="termux/termux-x11",
            gh_latest=True,
            gh_pattern="termux-x11-universal-debug.apk",
            connect=False,
        ),
        command_fn=command_fn,
    )
    return out, downloads, seen


def test_gh_latest_skips_when_installed_apk_matches_published_digest(mocker, tmp_path, monkeypatch):
    digest = sha256(b"PK").hexdigest()
    out, downloads, seen = _run_latest(mocker, tmp_path, monkeypatch, "sha256:" + digest, digest)
    assert out.get("failed") is not True, out
    assert out["changed"] is False
    assert out["reason"] == "newest release nightly already installed"
    assert downloads == []


def test_gh_latest_installs_newest_release_verified_by_digest(mocker, tmp_path, monkeypatch):
    digest = sha256(b"PK").hexdigest()
    out, downloads, seen = _run_latest(mocker, tmp_path, monkeypatch, "sha256:" + digest, "0" * 64, draft_first=True)
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert downloads == [("termux/termux-x11", "termux-x11-universal-debug.apk", "nightly")]
    assert any(" install " in c for c in seen)


def test_gh_latest_rejects_asset_that_does_not_match_digest(mocker, tmp_path, monkeypatch):
    out, _downloads, seen = _run_latest(mocker, tmp_path, monkeypatch, "sha256:" + "a" * 64, "0" * 64)
    assert out["failed"] is True
    assert "checksum mismatch" in out["msg"]
    assert not any(" install " in c for c in seen)


def test_gh_latest_installs_unverified_when_no_digest_is_published(mocker, tmp_path, monkeypatch):
    out, downloads, _seen = _run_latest(mocker, tmp_path, monkeypatch, None, "0" * 64)
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert any("installing unverified" in w for w in out["_warnings"])


def test_gh_latest_without_digest_skips_when_download_matches_device(mocker, tmp_path, monkeypatch):
    out, downloads, seen = _run_latest(mocker, tmp_path, monkeypatch, None, sha256(b"PK").hexdigest())
    assert out["changed"] is False
    assert len(downloads) == 1
    assert not any(" install " in c for c in seen)


def _run_latest_offline(mocker, tmp_path, monkeypatch, remembered, present=True, device_sha="0" * 64):
    cache = tmp_path / "cache"
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(cache))
    apk = b"PK-cached"
    digest = sha256(apk).hexdigest()
    if remembered:
        cache.mkdir()
        (cache / (digest + ".apk")).write_bytes(apk)
        mod._remember_gh_release("termux/termux-x11", "termux-x11-universal-release.apk", "nightly", digest)
    downloads = []
    monkeypatch.setattr(mod, "download_gh_release", lambda *a: downloads.append(a))
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "api repos/termux/termux-x11/releases" in joined:
            return (1, "", "error connecting to api.github.com")
        if "pm list packages" in joined:
            return (0, "package:com.termux.x11\n" if present else "", "")
        if "pm path" in joined:
            return (0, "package:/data/app/~~x/com.termux.x11-y/base.apk\n", "")
        if "sha256sum" in joined:
            return (0, "%s  /data/app/~~x/com.termux.x11-y/base.apk\n" % device_sha, "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.termux.x11",
            gh_repo="termux/termux-x11",
            gh_latest=True,
            gh_pattern="termux-x11-universal-release.apk",
            connect=False,
        ),
        command_fn=command_fn,
    )
    return out, downloads, seen, digest


def test_gh_latest_outage_installs_the_cached_release_when_absent(mocker, tmp_path, monkeypatch):
    out, downloads, seen, _digest = _run_latest_offline(mocker, tmp_path, monkeypatch, remembered=True, present=False)
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert downloads == []
    assert any("using cached nightly" in w for w in out["_warnings"])
    assert any(" install " in c for c in seen)


def test_gh_latest_outage_with_cached_release_already_installed_is_a_no_op(mocker, tmp_path, monkeypatch):
    digest = sha256(b"PK-cached").hexdigest()
    out, downloads, seen, _d = _run_latest_offline(mocker, tmp_path, monkeypatch, remembered=True, device_sha=digest)
    assert out["changed"] is False
    assert downloads == []
    assert not any(" install " in c for c in seen)


def test_gh_latest_outage_leaves_an_installed_app_alone_when_nothing_is_cached(mocker, tmp_path, monkeypatch):
    out, downloads, seen, _d = _run_latest_offline(mocker, tmp_path, monkeypatch, remembered=False, present=True)
    assert out.get("failed") is not True, out
    assert out["changed"] is False
    assert any("leaving the installed build" in w for w in out["_warnings"])
    assert not any(" install " in c for c in seen)


def test_gh_latest_outage_fails_for_a_first_install_with_nothing_cached(mocker, tmp_path, monkeypatch):
    out, _downloads, _seen, _d = _run_latest_offline(mocker, tmp_path, monkeypatch, remembered=False, present=False)
    assert out["failed"] is True
    assert "could not list releases" in out["msg"]


def test_gh_latest_success_remembers_the_release_for_a_later_outage(mocker, tmp_path, monkeypatch):
    digest = sha256(b"PK").hexdigest()
    _run_latest(mocker, tmp_path, monkeypatch, "sha256:" + digest, digest)
    memory = list((tmp_path / "cache" / "gh-latest").glob("*.json"))
    assert len(memory) == 1
    assert json.loads(memory[0].read_text()) == {"tag": "nightly", "sha256": digest}


def _run_pinned(mocker, tmp_path, monkeypatch, remembered, apk_cached=True, tamper=False, pin=True, present=False):
    cache = tmp_path / "cache"
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(cache))
    apk = b"PK-fleet"
    digest = sha256(apk).hexdigest()
    cache.mkdir()
    if apk_cached:
        (cache / (digest + ".apk")).write_bytes(b"tampered" if tamper else apk)
    if remembered:
        mod._remember_gh_release("termux/termux-x11", "termux-x11-universal-release.apk", "fleet-tag", digest)
    downloads = []
    monkeypatch.setattr(mod, "download_gh_release", lambda *a: downloads.append(a))
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "api repos/termux/termux-x11/releases" in joined:
            return (1, "", "must not be called")
        if "pm list packages" in joined:
            return (0, "package:com.termux.x11\n" if present else "", "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    args = dict(
        device="dev",
        package="com.termux.x11",
        gh_repo="termux/termux-x11",
        gh_latest=True,
        gh_pattern="termux-x11-universal-release.apk",
        connect=False,
    )
    if pin:
        args["gh_latest_pin_to_cache"] = True
    return run_module(mocker, args, command_fn=command_fn), downloads, seen


def test_gh_latest_pin_to_cache_installs_the_remembered_release_without_asking_github(mocker, tmp_path, monkeypatch):
    out, downloads, seen = _run_pinned(mocker, tmp_path, monkeypatch, remembered=True)
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert downloads == []
    assert not any("api repos/" in c for c in seen)
    assert any(" install " in c for c in seen)
    assert any("pinned to the cached fleet release fleet-tag" in w for w in out["_warnings"])


def test_gh_latest_pin_to_cache_without_memory_fails_instead_of_resolving_latest(mocker, tmp_path, monkeypatch):
    out, downloads, seen = _run_pinned(mocker, tmp_path, monkeypatch, remembered=False, apk_cached=False)
    assert out["failed"] is True
    assert "no release remembered for termux/termux-x11" in out["msg"]
    assert downloads == []
    assert not any("api repos/" in c for c in seen)
    assert not any(" install " in c for c in seen)


def test_gh_latest_pin_to_cache_with_missing_cached_apk_fails_naming_the_path(mocker, tmp_path, monkeypatch):
    out, downloads, seen = _run_pinned(mocker, tmp_path, monkeypatch, remembered=True, apk_cached=False, present=True)
    digest = sha256(b"PK-fleet").hexdigest()
    assert out["failed"] is True
    assert "missing or does not match" in out["msg"]
    assert str(tmp_path / "cache" / (digest + ".apk")) in out["msg"]
    assert "termux/termux-x11" in out["msg"]
    assert downloads == []
    assert not any("api repos/" in c for c in seen)
    assert not any(" install " in c for c in seen)


def test_gh_latest_pin_to_cache_with_mismatched_cached_apk_fails(mocker, tmp_path, monkeypatch):
    out, downloads, seen = _run_pinned(mocker, tmp_path, monkeypatch, remembered=True, tamper=True)
    assert out["failed"] is True
    assert "missing or does not match" in out["msg"]
    assert downloads == []
    assert not any(" install " in c for c in seen)


def test_gh_latest_pin_to_cache_false_still_asks_github(mocker, tmp_path, monkeypatch):
    # Default behaviour: a remembered release is only an outage fallback, so GitHub is listed first.
    out, _downloads, seen = _run_pinned(mocker, tmp_path, monkeypatch, remembered=True, pin=False)
    assert any("api repos/termux/termux-x11/releases" in c for c in seen)
    assert any("using cached fleet-tag" in w for w in out["_warnings"])


# gh_tag_prefix / gh_skip_prereleases ---------------------------------------------------------


def _rel(tag, asset, digest, prerelease=False, draft=False):
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": asset, "digest": digest}] if asset else [],
    }


def test_select_gh_release_without_filters_takes_the_first_published_release():
    releases = [
        _rel("d", None, None, draft=True),
        _rel("agent-ci-1", None, None, prerelease=True),
        _rel("agent-r5", None, None),
    ]
    assert mod.select_gh_release(releases)["tag_name"] == "agent-ci-1"


def test_select_gh_release_prefix_skips_other_tag_families():
    releases = [
        _rel("agent-ci-0.9-ab", None, None, prerelease=True),
        _rel("agent-v0.9.19", None, None),
        _rel("agent-r40", None, None),
        _rel("agent-r39", None, None),
    ]
    assert mod.select_gh_release(releases, tag_prefix="agent-r")["tag_name"] == "agent-r40"
    assert mod.select_gh_release(releases, tag_prefix="nope-") is None


def test_select_gh_release_prefix_must_match_the_whole_tag_as_prefix_plus_version():
    # A stray tag that merely starts with the prefix must not become what the fleet installs.
    stray = ["agent-rz", "agent-r", "agent-r1x", "agent-r-1", "agent-r1.2-evil", "agent-rc1", "xagent-r9"]
    releases = [_rel(tag, None, None) for tag in stray] + [_rel("agent-r40", None, None)]
    assert mod.select_gh_release(releases, tag_prefix="agent-r")["tag_name"] == "agent-r40"
    assert mod.select_gh_release(releases[:-1], tag_prefix="agent-r") is None
    assert mod.select_gh_release([_rel("v1.2.3", None, None)], tag_prefix="v")["tag_name"] == "v1.2.3"


def test_select_gh_release_can_skip_prereleases():
    releases = [_rel("v0.119.0-beta.3", None, None, prerelease=True), _rel("v0.118.3", None, None)]
    assert mod.select_gh_release(releases)["tag_name"] == "v0.119.0-beta.3"
    assert mod.select_gh_release(releases, skip_prereleases=True)["tag_name"] == "v0.118.3"


def test_gh_memory_key_is_unchanged_without_filters_and_distinct_with_them():
    plain = mod._gh_memory_path("o/r", "a.apk")
    assert plain == mod._gh_memory_path("o/r", "a.apk", None, False)
    assert mod._gh_memory_path("o/r", "a.apk", "agent-r") != plain
    assert mod._gh_memory_path("o/r", "a.apk", "agent-r") != mod._gh_memory_path("o/r", "a.apk", "agent-v")
    assert mod._gh_memory_path("o/r", "a.apk", None, True) != plain


def _run_prefixed(mocker, tmp_path, monkeypatch, releases, device_sha="0" * 64, **extra):
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(tmp_path / "cache"))
    downloads = []

    def fake_download(module, repo, pattern, tag):
        downloads.append((repo, pattern, tag))
        path = tmp_path / "dl.apk"
        path.write_bytes(b"PK")
        return str(path)

    monkeypatch.setattr(mod, "download_gh_release", fake_download)
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "api repos/djbclark/stayturgid/releases" in joined:
            return (0, json.dumps(releases), "")
        if "pm list packages" in joined:
            return (0, "package:org.stayturgid.agent\n", "")
        if "pm path" in joined:
            return (0, "package:/data/app/~~x/org.stayturgid.agent-y/base.apk\n", "")
        if "sha256sum" in joined:
            return (0, "%s  /data/app/~~x/org.stayturgid.agent-y/base.apk\n" % device_sha, "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    args = dict(
        device="dev",
        package="org.stayturgid.agent",
        gh_repo="djbclark/stayturgid",
        gh_latest=True,
        gh_pattern="app-release.apk",
        connect=False,
        **extra,
    )
    return run_module(mocker, args, command_fn=command_fn), downloads, seen


def test_gh_latest_tag_prefix_installs_the_newest_matching_release_not_the_newest_release(
    mocker, tmp_path, monkeypatch
):
    digest = "sha256:" + sha256(b"PK").hexdigest()
    releases = [
        _rel("agent-ci-0.9.19-cdd76c47", "stayturgid-agent-0.9.19-release-unsigned.apk", digest, prerelease=True),
        _rel("agent-r102", "app-release.apk", digest),
        _rel("agent-v0.9.19", "app-release.apk", digest),
    ]
    out, downloads, seen = _run_prefixed(mocker, tmp_path, monkeypatch, releases, gh_tag_prefix="agent-r")
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert downloads == [("djbclark/stayturgid", "app-release.apk", "agent-r102")]
    assert any("per_page=100" in c for c in seen)


def test_gh_latest_without_tag_prefix_trips_on_the_unsigned_prerelease(mocker, tmp_path, monkeypatch):
    digest = "sha256:" + sha256(b"PK").hexdigest()
    releases = [
        _rel("agent-ci-0.9.19-cdd76c47", "stayturgid-agent-0.9.19-release-unsigned.apk", digest, prerelease=True)
    ]
    out, _downloads, _seen = _run_prefixed(mocker, tmp_path, monkeypatch, releases)
    assert out["failed"] is True
    assert "expected 1" in out["msg"]


def test_gh_latest_tag_prefix_with_no_such_release_fails_naming_the_prefix(mocker, tmp_path, monkeypatch):
    out, downloads, _seen = _run_prefixed(
        mocker, tmp_path, monkeypatch, [_rel("agent-v0.9.19", "app-release.apk", None)], gh_tag_prefix="agent-r"
    )
    assert out["failed"] is True
    assert "tag prefix 'agent-r'" in out["msg"]
    assert downloads == []


def test_gh_latest_skip_prereleases_ignores_a_newer_beta(mocker, tmp_path, monkeypatch):
    digest = "sha256:" + sha256(b"PK").hexdigest()
    releases = [_rel("v2-beta", "app-release.apk", digest, prerelease=True), _rel("v1", "app-release.apk", digest)]
    out, downloads, _seen = _run_prefixed(mocker, tmp_path, monkeypatch, releases, gh_skip_prereleases=True)
    assert out.get("failed") is not True, out
    assert downloads == [("djbclark/stayturgid", "app-release.apk", "v1")]


def test_gh_latest_prefix_release_is_remembered_under_the_prefix_key(mocker, tmp_path, monkeypatch):
    digest = sha256(b"PK").hexdigest()
    _run_prefixed(
        mocker,
        tmp_path,
        monkeypatch,
        [_rel("agent-r7", "app-release.apk", "sha256:" + digest)],
        gh_tag_prefix="agent-r",
    )
    assert mod._read_gh_memory("djbclark/stayturgid", "app-release.apk", "agent-r") == ("agent-r7", digest)
    assert mod._read_gh_memory("djbclark/stayturgid", "app-release.apk") is None


def test_gh_latest_prefix_outage_recalls_only_the_same_prefix(mocker, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(cache))
    cache.mkdir()
    digest = sha256(b"PK").hexdigest()
    (cache / (digest + ".apk")).write_bytes(b"PK")
    mod._remember_gh_release("o/r", "a.apk", "agent-r9", digest, "agent-r")
    assert mod._recall_gh_release("o/r", "a.apk", "agent-r") == ("agent-r9", digest)
    assert mod._recall_gh_release("o/r", "a.apk", "agent-v") is None
    assert mod._recall_gh_release("o/r", "a.apk") is None


def test_gh_latest_prefix_pin_to_cache_uses_the_prefix_memory(mocker, tmp_path, monkeypatch):
    out, downloads, seen = _run_prefixed(
        mocker, tmp_path, monkeypatch, [], gh_tag_prefix="agent-r", gh_latest_pin_to_cache=True
    )
    assert out["failed"] is True
    assert "no release remembered" in out["msg"]
    assert not any("api repos/" in c for c in seen)


def test_gh_tag_prefix_without_gh_latest_is_refused(mocker):
    out = run_module(
        mocker, dict(device="dev", package="p", gh_repo="o/r", gh_tag="v1", gh_tag_prefix="v", connect=False)
    )
    assert out["failed"] is True


# signer_sha256 ------------------------------------------------------------------------------

SIGNER = "35bbc3d1a93c2a726df14bcc066bdc791f7f55f21b57d9455da27439c5ff9b6a"


def _run_signed(
    mocker, tmp_path, monkeypatch, certs, package="org.stayturgid.agent", tools=True, present=False, code="101"
):
    monkeypatch.setattr(mod, "APK_CACHE_DIR", str(tmp_path / "cache"))
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    if tools:
        for name in ("apksigner", "aapt2"):
            (sdk / name).write_text("#!/bin/sh\n")
    digest = sha256(b"PK").hexdigest()
    monkeypatch.setattr(mod, "download_gh_release", lambda *a: _write(tmp_path / "dl.apk"))
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "api repos/djbclark/stayturgid/releases" in joined:
            return (0, json.dumps([_rel("agent-r101", "app-release.apk", "sha256:" + digest)]), "")
        if "apksigner verify" in joined:
            return (0, "".join("Signer #%d certificate SHA-256 digest: %s\n" % (i, c) for i, c in enumerate(certs)), "")
        if "dump badging" in joined:
            return (0, "package: name='%s' versionCode='%s'\n" % (package, code), "")
        if "pm list packages" in joined:
            return (0, "package:org.stayturgid.agent\n" if present else "", "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    args = dict(
        device="dev",
        package="org.stayturgid.agent",
        gh_repo="djbclark/stayturgid",
        gh_latest=True,
        gh_tag_prefix="agent-r",
        gh_pattern="app-release.apk",
        signer_sha256=SIGNER,
        apksigner_bin=str(sdk / "apksigner"),
        connect=False,
    )
    return run_module(mocker, args, command_fn=command_fn), seen


def _write(path):
    path.write_bytes(b"PK")
    return str(path)


def test_signer_sha256_installs_an_apk_signed_by_the_pinned_certificate(mocker, tmp_path, monkeypatch):
    out, seen = _run_signed(mocker, tmp_path, monkeypatch, [SIGNER])
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert any(" install " in c for c in seen)


def test_signer_sha256_refuses_a_foreign_signer_before_any_install_or_uninstall(mocker, tmp_path, monkeypatch):
    out, seen = _run_signed(mocker, tmp_path, monkeypatch, ["a" * 64], present=True)
    assert out["failed"] is True
    assert "not signed by the pinned certificate" in out["msg"]
    assert not any(" install " in c or " uninstall " in c for c in seen)


def test_signer_sha256_refuses_an_extra_signer(mocker, tmp_path, monkeypatch):
    out, seen = _run_signed(mocker, tmp_path, monkeypatch, [SIGNER, "b" * 64])
    assert out["failed"] is True
    assert not any(" install " in c for c in seen)


def test_signer_sha256_refuses_another_package(mocker, tmp_path, monkeypatch):
    out, seen = _run_signed(mocker, tmp_path, monkeypatch, [SIGNER], package="com.evil.app")
    assert out["failed"] is True
    assert "com.evil.app" in out["msg"]
    assert not any(" install " in c for c in seen)


def test_signer_sha256_fails_closed_without_the_sdk_tools(mocker, tmp_path, monkeypatch):
    out, seen = _run_signed(mocker, tmp_path, monkeypatch, [SIGNER], tools=False)
    assert out["failed"] is True
    assert "needs" in out["msg"]
    assert not any(" install " in c for c in seen)


def test_signer_sha256_binds_the_apk_versioncode_to_the_release_tag(mocker, tmp_path, monkeypatch):
    # A genuine, fleet-signed older build attached to a newer tag must not install.
    out, seen = _run_signed(mocker, tmp_path, monkeypatch, [SIGNER], code="77")
    assert out["failed"] is True
    assert "versionCode 77" in out["msg"] and "says 101" in out["msg"]
    assert not any(" install " in c for c in seen)


def test_select_gh_release_takes_the_highest_tag_number_not_the_first_listed():
    # A release re-created on an old tag is listed first (newest created) but is not the newest build.
    releases = [_rel("agent-r105", None, None), _rel("agent-r120", None, None), _rel("agent-r99", None, None)]
    assert mod.select_gh_release(releases, tag_prefix="agent-r")["tag_name"] == "agent-r120"
    assert mod.select_gh_release([_rel("agent-r\u0661\u0660\u0661", None, None)], tag_prefix="agent-r") is None
