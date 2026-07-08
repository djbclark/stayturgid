"""Unit tests for shizuku_grant module."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import shizuku as shizuku_utils  # noqa: E402
import shizuku_grant as mod  # noqa: E402


def test_patch_shizuku_json_adds_entry():
    current = '{"version":2,"packages":[{"uid":10001,"flags":2,"packages":["com.other"]}]}'
    patched = shizuku_utils.patch_shizuku_json(current, 10002, "com.machiav3lli.fdroid")
    data = json.loads(patched)
    uids = [e["uid"] for e in data["packages"]]
    assert 10001 in uids
    assert 10002 in uids


def test_patch_shizuku_json_idempotent():
    current = '{"version":2,"packages":[{"uid":10002,"flags":2,"packages":["com.machiav3lli.fdroid"]}]}'
    patched = shizuku_utils.patch_shizuku_json(current, 10002, "com.machiav3lli.fdroid")
    assert patched.strip() == current.strip()


def run_module(mocker, args, cmd_results=None, expect_fail=False):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in (cmd_results or []):
            if needle in joined:
                return result
        if joined.endswith("shell true"):
            return (0, "", "")
        if "pm list packages -U" in joined:
            return (0, "package:com.machiav3lli.fdroid uid:10002", "")
        if "test -f" in joined:
            return (0, "", "")
        if "cat /data/local/tmp/shizuku/shizuku.json" in joined:
            return (0, '{"version":2,"packages":[]}', "")
        if "pm grant" in joined:
            return (0, "", "")
        if "adb push" in joined:
            return (0, "", "")
        if "cp /sdcard" in joined:
            return (0, "", "")
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


def test_shizuku_grant_changes_json(mocker):
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


def test_shizuku_grant_unreadable_json(mocker):
    out = run_module(
        mocker,
        dict(
            device="localhost:5555",
            package="com.machiav3lli.fdroid",
            connect=False,
        ),
        cmd_results=[
            ("cat /data/local/tmp/shizuku/shizuku.json", (1, "", "read error")),
        ],
        expect_fail=True,
    )
    assert "unreadable" in out.get("msg", "")


def test_shizuku_grant_already_granted(mocker):
    existing = shizuku_utils.patch_shizuku_json("", 10002, "com.machiav3lli.fdroid")
    out = run_module(
        mocker,
        dict(
            device="localhost:5555",
            package="com.machiav3lli.fdroid",
            connect=False,
        ),
        cmd_results=[
            ("cat /data/local/tmp/shizuku/shizuku.json", (0, existing, "")),
        ],
    )
    assert out["changed"] is False
