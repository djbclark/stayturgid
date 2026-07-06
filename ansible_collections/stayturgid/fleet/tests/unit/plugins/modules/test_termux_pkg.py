"""Unit tests for the termux_pkg Ansible module.

Idiomatic module testing: import the module and drive main() through Ansible's
own stdin-args contract, intercepting run_command so no device is touched.
Complements the end-to-end `ansible localhost` checks in tests/test-unit.sh —
here we assert the exact command sequence (check-mode skips, update-once).
"""
import json

import pytest

from ansible_collections.stayturgid.fleet.plugins.modules import termux_pkg


def run_module(mocker, args, rc_map=None, check=False):
    """Invoke termux_pkg.main() with mocked AnsibleModule I/O.

    rc_map: list of (substring, (rc, stdout, stderr)); first match wins.
    Returns (exit_json_kwargs_or_fail, list_of_shell_scripts_run).
    """
    args = dict(args)
    args["_ansible_check_mode"] = check
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": args})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    # ansible-core >= 2.19 requires a serialization profile alongside the args.
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    scripts = []

    def fake_run_command(self, cmd, *a, **kw):
        script = cmd[-1] if isinstance(cmd, (list, tuple)) else str(cmd)
        scripts.append(script)
        for needle, result in (rc_map or []):
            if needle in script:
                return result
        return (0, "", "")

    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.run_command",
        fake_run_command,
    )

    captured = {}
    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)
    def fake_fail(self, **kw):
        captured.update(kw, failed=True)
        raise SystemExit(1)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fake_fail)

    with pytest.raises(SystemExit):
        termux_pkg.main()
    return captured, scripts


def count(scripts, needle):
    return sum(1 for s in scripts if needle in s)


def test_pkg_list_normalizes():
    assert termux_pkg._pkg_list(None, None) == []
    assert termux_pkg._pkg_list(None, "openssh") == ["openssh"]
    assert termux_pkg._pkg_list(None, ["a", "b"]) == ["a", "b"]


def test_check_mode_runs_no_mutations(mocker):
    # dpkg-query rc=1 => package missing
    res, scripts = run_module(
        mocker,
        {"name": ["foo"], "update_cache": True, "upgrade": True},
        rc_map=[("dpkg-query", (1, "", ""))],
        check=True,
    )
    assert res["changed"] is True
    assert count(scripts, "pkg update") == 0, "check mode must not run pkg update"
    assert count(scripts, "full-upgrade") == 0, "check mode must not upgrade"
    assert count(scripts, "dpkg-query") >= 1, "check mode still probes state"
    assert count(scripts, "pkg install") == 0


def test_install_runs_update_once(mocker):
    res, scripts = run_module(
        mocker,
        {"name": ["foo"], "update_cache": True, "upgrade": True},
        rc_map=[
            ("dpkg-query", (1, "", "")),
            ("pkg update", (0, "Get:1 repo", "")),
            ("full-upgrade", (0, "0 upgraded", "")),
        ],
    )
    assert res["changed"] is True
    assert count(scripts, "pkg update") == 1, "update must run exactly once (M6)"
    assert count(scripts, "pkg install -y foo") == 1


def test_mirror_sync_failure_is_tolerated(mocker):
    # pkg update rc=100 (mirror sync) must warn + continue to install
    res, scripts = run_module(
        mocker,
        {"name": ["foo"], "update_cache": True, "upgrade": False},
        rc_map=[
            ("dpkg-query", (1, "", "")),
            ("pkg update", (100, "", "E: Mirror sync in progress?")),
        ],
    )
    assert res["failed"] is False, "mirror-sync update failure must not fail the module"
    assert count(scripts, "pkg install -y foo") == 1


def test_already_installed_no_change(mocker):
    res, scripts = run_module(
        mocker,
        {"name": ["foo"], "update_cache": False, "upgrade": False},
        rc_map=[("dpkg-query", (0, "install ok installed", ""))],
    )
    assert res.get("changed") is False
    assert count(scripts, "pkg install") == 0
