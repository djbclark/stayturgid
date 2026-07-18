"""Unit tests for fdroid_apps module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
REPO_ROOT = os.path.abspath(os.path.join(ROOT, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import fdroid_apps as mod  # noqa: E402


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        if "pm list packages" in joined:
            return (0, "", "")
        if "fdroidcl" in joined and " install" in joined:
            return (0, "installed org.breezyweather", "")
        return (0, "", "")

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json",
        lambda self, **kw: (_ for _ in ()).throw(SystemExit(1)),
    )

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_fdroid_apps_installs(mocker):
    out = run_module(
        mocker,
        dict(
            device="stock-android-device",
            apps=[dict(id="org.breezyweather")],
        ),
    )
    assert out["changed"] is True
    assert out["installed"] == ["org.breezyweather"]


def test_fdroid_apps_skips_present(mocker):
    out = run_module(
        mocker,
        dict(
            device="stock-android-device",
            apps=[dict(id="org.breezyweather")],
        ),
        cmd_results=[
            ("pm list packages", (0, "package:org.breezyweather\n", "")),
        ],
    )
    assert out["changed"] is False
    assert out["skipped"] == ["org.breezyweather"]
