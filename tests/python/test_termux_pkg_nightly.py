"""The nightly launchd runner must use the same site-overlay precedence."""

import termux_pkg_nightly as nightly
from ansible_context import AnsibleContext


def test_nightly_runner_uses_resolved_site_config(monkeypatch, tmp_path):
    context = AnsibleContext(
        config=tmp_path / "site" / "ansible.cfg",
        inventory=tmp_path / "site" / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="site overlay",
    )
    seen = {}

    monkeypatch.setattr(nightly, "resolve_ansible_context", lambda repo: context)
    monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(nightly, "LOG", tmp_path / "logs" / "nightly.log")
    monkeypatch.setattr(nightly, "trim_log", lambda: None)

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    assert nightly.main(["--check", "--limit", "oneui-device"]) == 0
    assert seen["command"] == [
        "ansible-playbook",
        str(nightly.PLAYBOOK),
        "-e",
        f"stayturgid_repo_root={nightly.REPO_ROOT}",
        "--limit",
        "oneui-device",
        "--check",
        "--diff",
    ]
    assert seen["env"]["ANSIBLE_CONFIG"] == str(context.config)
    assert seen["env"]["STAYTURGID_ROOT"] == str(nightly.REPO_ROOT)


def test_nightly_blocked_by_concurrent_deploy(monkeypatch, tmp_path):
    """A deploy_fleet.py run already holding the fleet lock must block the
    nightly job rather than racing it (stayturgid issue #58)."""
    context = AnsibleContext(
        config=tmp_path / "site" / "ansible.cfg",
        inventory=tmp_path / "site" / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="site overlay",
    )
    logged = []

    monkeypatch.setattr(nightly, "resolve_ansible_context", lambda repo: context)
    monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(nightly, "LOG", tmp_path / "logs" / "nightly.log")
    monkeypatch.setattr(nightly, "trim_log", lambda: None)
    monkeypatch.setattr(nightly, "log", lambda msg: logged.append(msg))

    def fake_run(command, **kwargs):
        raise AssertionError("ansible-playbook must not run while the fleet lock is held")

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    with nightly.fleet_lock("deploy_fleet.py s24"):
        rc = nightly.main(["--limit", "oneui-device"])

    assert rc == 3
    assert any("already running" in msg for msg in logged)
