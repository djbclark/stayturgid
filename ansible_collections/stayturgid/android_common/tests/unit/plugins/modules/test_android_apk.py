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


def test_download_gh_release_uses_aria2c(tmp_path):
    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if tool(cmd, "aria2c"):
            out = cmd[cmd.index("--dir") + 1]
            with open(os.path.join(out, cmd[cmd.index("--out") + 1]), "wb") as f:
                f.write(b"PK")
            return (0, "", "")
        raise AssertionError("unexpected %r" % cmd)

    module = FakeDownloadModule(tmp_path, run)
    path = mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert path.endswith("app-1.apk")
    assert not [c for c in module.calls if tool(c, "gh") and "download" in c]


def test_download_gh_release_falls_back_to_gh_and_retries(tmp_path):
    attempts = []

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if tool(cmd, "aria2c"):
            return (1, "", "connection reset")
        if tool(cmd, "gh") and "download" in cmd:
            attempts.append(cmd)
            if len(attempts) < 2:
                return (1, "", "unexpected EOF")
            with open(os.path.join(cmd[cmd.index("--dir") + 1], "app-1.apk"), "wb") as f:
                f.write(b"PK")
            return (0, "", "")
        raise AssertionError("unexpected %r" % cmd)

    module = FakeDownloadModule(tmp_path, run)
    assert mod.download_gh_release(module, "o/r", "app-*.apk", "v1").endswith("app-1.apk")
    assert len(attempts) == 2
    assert module.warnings and "falling back to gh" in module.warnings[0]
