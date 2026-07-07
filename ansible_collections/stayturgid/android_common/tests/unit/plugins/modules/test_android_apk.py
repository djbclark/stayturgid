"""Unit tests for android_apk module."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import apk_install  # noqa: E402
import android_apk as mod  # noqa: E402


def test_parse_install_result_success():
    ok, reason = apk_install.parse_install_result("Performing Streamed Install\nSuccess\n")
    assert ok is True
    assert reason == "Success"


def test_parse_install_result_failure():
    ok, reason = apk_install.parse_install_result("Failure [INSTALL_FAILED_VERSION_DOWNGRADE]")
    assert ok is False
    assert "INSTALL_FAILED" in reason


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in (cmd_results or []):
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

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fake_fail)

    with pytest.raises(SystemExit):
        mod.main()
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
