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

    install_cmds = [c for c in seen_cmds if "install" in " ".join(c)]
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
