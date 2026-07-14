"""Unit tests for fdroid_repos module (pure helpers + mocked Ansible I/O)."""

import json
import os
import sys

import pytest

FLEET_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(FLEET_ROOT, "plugins", "modules"))
import fdroid_repos as mod  # noqa: E402

REAL_REPO_LIST = """\
Name: f-droid
URL: https://f-droid.org/repo
Enabled: yes

Name: IzzyOnDroid
URL: https://apt.izzysoft.de/fdroid/repo
Enabled: yes

Name: Guardian Project
URL: https://guardianproject.info/fdroid/repo
Enabled: no
"""


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    commands, captured = [], {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        commands.append(joined)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        if joined.startswith("fdroidcl repo"):
            return (0, REAL_REPO_LIST, "")
        if joined.startswith("fdroidcl update"):
            return (0, "updated", "")
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
        lambda self, msg: None,
    )

    with pytest.raises(SystemExit):
        mod.main()
    return captured, commands


def test_parse_current_repos_real_format():
    parsed = mod.parse_current_repos(REAL_REPO_LIST)
    assert mod.repo_key("IzzyOnDroid", "https://apt.izzysoft.de/fdroid/repo") in parsed
    assert parsed[mod.repo_key("IzzyOnDroid", "https://apt.izzysoft.de/fdroid/repo")] is True
    assert parsed[mod.repo_key("Guardian Project", "https://guardianproject.info/fdroid/repo")] is False


def test_fdroidrepos_uri_with_and_without_fingerprint():
    assert mod.fdroidrepos_uri("https://apt.izzysoft.de/fdroid/repo") == ("fdroidrepos://apt.izzysoft.de/fdroid/repo")
    assert (
        mod.fdroidrepos_uri(
            "https://guardianproject.info/fdroid/repo",
            "B7:C2:EE:FD:8D:AC:78:06",
        )
        == "fdroidrepos://guardianproject.info/fdroid/repo?fingerprint=B7C2EEFD8DAC7806"
    )


def test_repo_present_exact_match_not_substring():
    current = mod.parse_current_repos(REAL_REPO_LIST)
    assert mod.repo_present(current, "IzzyOnDroid", "https://apt.izzysoft.de/fdroid/repo")
    assert not mod.repo_present(current, "Izzy", "https://evil.example/fdroid/repo")


def test_adds_missing_repo(mocker):
    empty = "Name: f-droid\nURL: https://f-droid.org/repo\nEnabled: yes\n\n"
    res, cmds = run_module(
        mocker,
        {
            "repos": [
                {
                    "name": "NewRepo",
                    "address": "https://example.com/fdroid/repo",
                }
            ],
            "device": "p7a",
        },
        cmd_results=[
            ("adb -s p7a shell true", (0, "", "")),
            ("fdroidcl repo", (0, empty, "")),
            ("fdroidcl repo add", (0, "added", "")),
        ],
    )
    assert res["changed"] is True
    assert any("fdroidcl repo add NewRepo" in c for c in cmds)


def test_idempotent_when_present_and_enabled(mocker):
    res, cmds = run_module(
        mocker,
        {
            "repos": [
                {
                    "name": "IzzyOnDroid",
                    "address": "https://apt.izzysoft.de/fdroid/repo",
                }
            ],
            "device": "p7a",
        },
        cmd_results=[("adb -s p7a shell true", (0, "", ""))],
    )
    assert res["changed"] is False
    assert not any("fdroidcl repo add" in c for c in cmds)


def test_enables_disabled_repo(mocker):
    res, cmds = run_module(
        mocker,
        {
            "repos": [
                {
                    "name": "Guardian Project",
                    "address": "https://guardianproject.info/fdroid/repo",
                }
            ],
            "device": "p7a",
        },
        cmd_results=[("adb -s p7a shell true", (0, "", ""))],
    )
    assert res["changed"] is True
    assert any("fdroidcl repo enable Guardian Project" in c for c in cmds)


def test_check_mode_no_mutations(mocker):
    res, cmds = run_module(
        mocker,
        {
            "repos": [
                {
                    "name": "NewRepo",
                    "address": "https://example.com/fdroid/repo",
                }
            ],
            "device": "p7a",
            "_ansible_check_mode": True,
        },
        cmd_results=[
            ("adb -s p7a shell true", (0, "", "")),
            ("fdroidcl repo", (0, "Name: f-droid\nURL: https://f-droid.org/repo\nEnabled: yes\n\n", "")),
        ],
    )
    assert res["changed"] is True
    assert not any("fdroidcl repo add" in c for c in cmds)


def test_fails_when_adb_unreachable(mocker):
    res, _cmds = run_module(
        mocker,
        {
            "repos": [{"name": "X", "address": "https://example.com/fdroid/repo"}],
            "device": "offline",
        },
        cmd_results=[("adb -s offline shell true", (1, "offline", ""))],
    )
    assert res["failed"] is True


def test_validate_fingerprint():
    assert mod.validate_fingerprint("")
    assert mod.validate_fingerprint("A" * 64)
    assert not mod.validate_fingerprint("ABC")


def test_removes_repo(mocker):
    res, cmds = run_module(
        mocker,
        {
            "repos": [
                {
                    "name": "IzzyOnDroid",
                    "address": "https://apt.izzysoft.de/fdroid/repo",
                    "state": "absent",
                }
            ],
            "device": "p7a",
        },
        cmd_results=[("adb -s p7a shell true", (0, "", ""))],
    )
    assert res["changed"] is True
    assert any("fdroidcl repo remove IzzyOnDroid" in c for c in cmds)


def test_setups_apply(mocker):
    res, cmds = run_module(
        mocker,
        {
            "repos": [],
            "setups": [{"name": "base-tools", "repos": ["IzzyOnDroid"], "apps": ["org.breezyweather"]}],
            "device": "p7a",
        },
        cmd_results=[("adb -s p7a shell true", (0, "", ""))],
    )
    assert res["changed"] is True
    assert any("fdroidcl setup apply base-tools" in c for c in cmds)
