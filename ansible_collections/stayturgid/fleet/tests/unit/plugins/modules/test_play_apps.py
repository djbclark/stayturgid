"""Unit tests for play_apps module (helpers + mocked Ansible I/O)."""
import json
import os
import sys

import pytest

FLEET_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, os.path.join(FLEET_ROOT, "plugins", "modules"))
import play_apps as mod  # noqa: E402


def run_module(mocker, args, cmd_results=None, check=False):
    args = dict(args)
    args["_ansible_check_mode"] = check
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": args})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    commands, captured = [], {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        commands.append(joined)
        for needle, result in (cmd_results or []):
            if needle in joined:
                return result
        if "pm list packages" in joined and "com.example.app" in joined:
            return (0, "", "")
        if " shell true" in joined:
            return (0, "", "")
        if "adb connect" in joined:
            return (0, "connected", "")
        if "apkeep" in joined:
            return (0, "downloaded", "")
        if "install -r" in joined:
            return (0, "Success", "")
        if "uninstall" in joined:
            return (0, "Success", "")
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
    return captured, commands


def test_find_apk_prefers_package_name(tmp_path):
    (tmp_path / "other.apk").write_bytes(b"x")
    target = tmp_path / "com.foo.app_1.apk"
    target.write_bytes(b"y")
    assert mod.find_apk(str(tmp_path), "com.foo.app") == str(target)


def test_extract_xapk_base_apk(tmp_path):
    import zipfile

    xapk = tmp_path / "com.example.app.xapk"
    with zipfile.ZipFile(xapk, "w") as zf:
        zf.writestr("split_config.apk", b"split")
        zf.writestr("base.apk", b"base-bytes")
    out = mod.extract_xapk(str(xapk), str(tmp_path))
    assert out.endswith("base.apk")
    assert open(out, "rb").read() == b"base-bytes"
    assert mod.resolve_installable_apk(str(tmp_path), "com.example.app") == out


def test_package_installed_detects_package():
    class FakeModule:
        def run_command(self, cmd):
            joined = " ".join(cmd)
            if "com.foo" in joined:
                return (0, "package:com.foo\n", "")
            return (0, "", "")

    module = FakeModule()
    assert mod.package_installed(module, "dev", "com.foo") is True
    assert mod.package_installed(module, "dev", "com.missing") is False


def test_install_with_local_apk(mocker, tmp_path):
    apk = tmp_path / "com.example.app.apk"
    apk.write_bytes(b"fake")
    res, cmds = run_module(
        mocker,
        {
            "apps": [{"id": "com.example.app", "apk_path": str(apk)}],
            "device": "localhost:5555",
            "download_backend": "none",
        },
    )
    assert res["changed"] is True
    assert res["installed"] == ["com.example.app"]
    assert any("install -r" in c and "com.android.vending" in c for c in cmds)
    assert not any("apkeep" in c for c in cmds)


def test_check_mode_reports_change_when_missing(mocker, tmp_path):
    apk = tmp_path / "com.example.app.apk"
    apk.write_bytes(b"fake")
    res, _cmds = run_module(
        mocker,
        {
            "apps": [{"id": "com.example.app", "apk_path": str(apk)}],
            "device": "localhost:5555",
            "download_backend": "none",
        },
        cmd_results=[("pm list packages", (0, "", ""))],
        check=True,
    )
    assert res["changed"] is True
    assert not any("install -r" in c for c in _cmds)


def test_google_play_download_requires_token(mocker):
    mocker.patch.dict(os.environ, {}, clear=True)
    res, _cmds = run_module(
        mocker,
        {
            "apps": [{"id": "com.example.app"}],
            "device": "localhost:5555",
            "download_backend": "apkeep",
            "apkeep_source": "google-play",
        },
        cmd_results=[("pm list packages", (0, "", ""))],
    )
    assert res.get("failed") is True
    assert "google-play" in res.get("msg", "")
