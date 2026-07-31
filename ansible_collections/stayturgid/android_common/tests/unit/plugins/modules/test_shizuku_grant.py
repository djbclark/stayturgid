"""Unit tests for shizuku_grant module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import shizuku_grant as mod  # noqa: E402


def run_module(mocker, args, cmd_results=None, expect_fail=False):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        if joined.endswith("shell true"):
            return (0, "", "")
        if "pm list packages -U" in joined:
            return (0, "package:com.machiav3lli.fdroid uid:10002", "")
        if "dumpsys package" in joined:
            # Not yet granted by default; tests override via cmd_results.
            return (0, "moe.shizuku.manager.permission.API_V23:\n  granted=false", "")
        if "pm grant" in joined:
            return (0, "", "")
        if "HEADLESS_STATUS" in joined:
            return (0, "", "")
        if "pgrep" in joined:
            return (1, "", "")
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

    with pytest.raises(SystemExit) as exc:
        mod.main()
    if expect_fail:
        assert exc.value.code == 1
        assert captured.get("failed") is True
    return captured


def test_shizuku_grant_grants_and_skips_restart_when_not_running(mocker):
    out = run_module(
        mocker,
        dict(
            device="localhost:5555",
            package="com.machiav3lli.fdroid",
            connect=False,
        ),
    )
    assert out["changed"] is True
    assert out["uid"] == "10002"
    # Shizuku wasn't running (HEADLESS_STATUS empty, pgrep rc=1) -> no restart needed.
    assert out["restarted"] is False


def test_shizuku_grant_already_granted_is_noop(mocker):
    out = run_module(
        mocker,
        dict(
            device="localhost:5555",
            package="com.machiav3lli.fdroid",
            connect=False,
        ),
        cmd_results=[
            ("dumpsys package", (0, "moe.shizuku.manager.permission.API_V23:\n  granted=true", "")),
        ],
    )
    assert out["changed"] is False
    assert out["restarted"] is False


def test_shizuku_grant_restarts_when_shizuku_running(mocker):
    out = run_module(
        mocker,
        dict(
            device="localhost:5555",
            package="com.machiav3lli.fdroid",
            connect=False,
        ),
        cmd_results=[
            ("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS", (0, "result=1", "")),
            (
                "pm path moe.shizuku.privileged.api",
                (0, "package:/data/app/~~x/moe.shizuku.privileged.api/base.apk", ""),
            ),
            ("libshizuku.so", (0, "", "")),
        ],
    )
    assert out["changed"] is True
    assert out["restarted"] is True


def test_shizuku_grant_fails_when_pm_grant_fails(mocker):
    out = run_module(
        mocker,
        dict(
            device="localhost:5555",
            package="com.machiav3lli.fdroid",
            connect=False,
        ),
        cmd_results=[
            ("pm grant", (1, "", "Package moe.shizuku.manager.permission.API_V23 has not been requested")),
        ],
        expect_fail=True,
    )
    assert "pm grant" in out.get("msg", "")
