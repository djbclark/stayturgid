"""Unit tests for the obtainium_app module (catalog rendering + idempotence)."""

import json

import pytest

from ansible_collections.stayturgid.obtainium.plugins.modules import obtainium_app

AUTOJS = {
    "id": "org.autojs.autojs6",
    "url": "https://github.com/djbclark/AutoJs6",
    "name": "AutoJs6",
    "author": "djbclark",
    "categories": ["Automation"],
    "settings": {"apkFilterRegEx": "arm64-v8a", "about": "watchdog"},
}


def run_module(mocker, args, cmd_results=None):
    """Drive obtainium_app.main() with mocked AnsibleModule I/O.

    cmd_results: list of (substring-of-joined-cmd, (rc, stdout, stderr)).
    Returns (result_dict, list_of_command_strings, warnings).
    """
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    commands, warnings, captured = [], [], {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        commands.append(joined)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
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
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.warn",
        lambda self, msg: warnings.append(msg),
    )

    with pytest.raises(SystemExit):
        obtainium_app.main()
    return captured, commands, warnings


def test_renders_catalog(tmp_path, mocker):
    path = str(tmp_path / "catalog.json")
    res, _cmds, _w = run_module(
        mocker,
        {"apps": [AUTOJS], "catalog_path": path, "check_installed": False},
    )
    assert res["changed"] is True
    data = json.load(open(path))
    (entry,) = data["apps"]
    assert entry["id"] == "org.autojs.autojs6"
    assert entry["overrideSource"] == "GitHub"
    settings = json.loads(entry["additionalSettings"])
    assert settings["apkFilterRegEx"] == "arm64-v8a"
    assert settings["about"] == "watchdog"
    assert settings["fallbackToOlderReleases"] is True, "baseline preserved"
    assert data["settings"] == {"groupByCategory": True}


def test_idempotent_second_run(tmp_path, mocker):
    path = str(tmp_path / "catalog.json")
    args = {"apps": [AUTOJS], "catalog_path": path, "check_installed": False}
    run_module(mocker, args)
    res, _cmds, _w = run_module(mocker, args)
    assert res["changed"] is False


def test_spec_change_is_detected(tmp_path, mocker):
    path = str(tmp_path / "catalog.json")
    run_module(mocker, {"apps": [AUTOJS], "catalog_path": path, "check_installed": False})
    changed_spec = dict(AUTOJS, settings={"apkFilterRegEx": "universal"})
    res, _cmds, _w = run_module(mocker, {"apps": [changed_spec], "catalog_path": path, "check_installed": False})
    assert res["changed"] is True
    settings = json.loads(json.load(open(path))["apps"][0]["additionalSettings"])
    assert settings["apkFilterRegEx"] == "universal"


def test_check_mode_writes_nothing(tmp_path, mocker):
    path = str(tmp_path / "catalog.json")
    res, _cmds, _w = run_module(
        mocker,
        {
            "apps": [AUTOJS],
            "catalog_path": path,
            "check_installed": False,
            "_ansible_check_mode": True,
        },
    )
    assert res["changed"] is True
    assert not (tmp_path / "catalog.json").exists()


def test_import_ui_only_on_change(tmp_path, mocker):
    path = str(tmp_path / "catalog.json")
    args = {
        "apps": [AUTOJS],
        "catalog_path": path,
        "check_installed": False,
        "import_ui": True,
    }
    res, cmds, _w = run_module(mocker, args)
    assert res["import_launched"] is True
    assert any("am start" in c and "obtainium" in c for c in cmds)
    res, cmds, _w = run_module(mocker, args)  # unchanged now
    assert res["import_launched"] is False
    assert not any("am start" in c for c in cmds)


def test_installed_report_and_warning(tmp_path, mocker):
    path = str(tmp_path / "catalog.json")
    pm_out = "package:org.autojs.autojs6\npackage:com.termux\n"
    other = dict(AUTOJS, id="com.example.missing", name="Missing")
    res, _cmds, warnings = run_module(
        mocker,
        {"apps": [AUTOJS, other], "catalog_path": path},
        cmd_results=[("pm list packages", (0, pm_out, ""))],
    )
    assert res["installed"] == {
        "org.autojs.autojs6": True,
        "com.example.missing": False,
    }
    assert any("com.example.missing" in w for w in warnings)


def test_missing_required_key_fails(tmp_path, mocker):
    res, _cmds, _w = run_module(
        mocker,
        {
            "apps": [{"id": "no.url.app"}],
            "catalog_path": str(tmp_path / "c.json"),
            "check_installed": False,
        },
    )
    assert res["failed"] is True
    assert "url" in res["msg"]
