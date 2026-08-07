"""The nightly launchd runner must use the same site-overlay precedence."""

from pathlib import Path

import secretspec_exec
import termux_pkg_nightly as nightly
from ansible_context import AnsibleContext


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_nightly_runner_uses_resolved_site_config(monkeypatch, tmp_path):
    context = AnsibleContext(
        config=tmp_path / "site" / "ansible.cfg",
        inventory=tmp_path / "site" / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="site overlay",
    )
    seen = {}

    monkeypatch.setattr(nightly, "resolve_ansible_context", lambda repo: context)
    monkeypatch.setattr(
        nightly,
        "resolved_env",
        lambda repo: {"ANSIBLE_CONFIG": str(context.config), "STAYTURGID_ROOT": str(repo), "PATH": "/usr/bin:/bin"},
    )
    monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(nightly, "LOG", tmp_path / "logs" / "nightly.log")
    monkeypatch.setattr(nightly, "trim_log", lambda: None)

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        return _Result()

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    # --check skips the #152 pre-check so subprocess.run is only ansible-playbook.
    assert nightly.main(["--check", "--limit", "oneui-device"]) == 0
    assert seen["command"] == [
        secretspec_exec.sys.executable,
        secretspec_exec.HELPER_PATH,
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
    monkeypatch.setattr(
        nightly,
        "resolved_env",
        lambda repo: {"ANSIBLE_CONFIG": str(context.config), "STAYTURGID_ROOT": str(repo), "PATH": "/usr/bin:/bin"},
    )
    monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(nightly, "LOG", tmp_path / "logs" / "nightly.log")
    monkeypatch.setattr(nightly, "trim_log", lambda: None)
    monkeypatch.setattr(nightly, "log", lambda msg: logged.append(msg))
    # Pre-check (#152) must not block or race the fleet lock; stub the script
    # path so the pre-step is skipped and only the locked ansible path runs.
    monkeypatch.setattr(nightly, "CHECK_UPDATES", Path("/nonexistent/check_termux_pkg_updates.py"))

    def fake_run(command, **kwargs):
        raise AssertionError("ansible-playbook must not run while the fleet lock is held")

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    with nightly.fleet_lock("deploy_fleet.py s24"):
        rc = nightly.main(["--limit", "oneui-device"])

    assert rc == 3
    assert any("already running" in msg for msg in logged)


def test_nightly_runs_precheck_before_upgrade(monkeypatch, tmp_path):
    """Issue #152: pre-upgrade check_termux_pkg_updates.py runs (and may
    hermes-notify) before ansible-playbook when not in --check mode."""
    context = AnsibleContext(
        config=tmp_path / "site" / "ansible.cfg",
        inventory=tmp_path / "site" / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="site overlay",
    )
    calls = []
    fake_check = tmp_path / "check_termux_pkg_updates.py"
    fake_check.write_text("# stub\n")

    monkeypatch.setattr(nightly, "resolve_ansible_context", lambda repo: context)
    monkeypatch.setattr(
        nightly,
        "resolved_env",
        lambda repo: {"ANSIBLE_CONFIG": str(context.config), "STAYTURGID_ROOT": str(repo), "PATH": "/usr/bin:/bin"},
    )
    monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(nightly, "LOG", tmp_path / "logs" / "nightly.log")
    monkeypatch.setattr(nightly, "trim_log", lambda: None)
    monkeypatch.setattr(nightly, "CHECK_UPDATES", fake_check)

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return _Result(0, stdout="No Termux package updates available on s24")

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    assert nightly.main(["--limit", "s24"]) == 0
    assert len(calls) >= 2
    assert any("check_termux_pkg_updates.py" in str(c) for c in calls)
    assert any(c and "ansible-playbook" in c for c in calls)
    # Pre-check before ansible.
    pre_idx = next(i for i, c in enumerate(calls) if "check_termux_pkg_updates.py" in str(c))
    ap_idx = next(i for i, c in enumerate(calls) if c and "ansible-playbook" in c)
    assert pre_idx < ap_idx
    assert "--limit" in calls[pre_idx]
    assert "s24" in calls[pre_idx]


def test_nightly_continues_when_precheck_times_out(monkeypatch, tmp_path):
    """Pre-check TimeoutExpired must not block the upgrade playbook (#152)."""
    context = AnsibleContext(
        config=tmp_path / "site" / "ansible.cfg",
        inventory=tmp_path / "site" / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="site overlay",
    )
    calls = []
    fake_check = tmp_path / "check_termux_pkg_updates.py"
    fake_check.write_text("# stub\n")
    logged = []

    monkeypatch.setattr(nightly, "resolve_ansible_context", lambda repo: context)
    monkeypatch.setattr(
        nightly,
        "resolved_env",
        lambda repo: {"ANSIBLE_CONFIG": str(context.config), "STAYTURGID_ROOT": str(repo), "PATH": "/usr/bin:/bin"},
    )
    monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(nightly, "LOG", tmp_path / "logs" / "nightly.log")
    monkeypatch.setattr(nightly, "trim_log", lambda: None)
    monkeypatch.setattr(nightly, "CHECK_UPDATES", fake_check)
    monkeypatch.setattr(nightly, "log", lambda msg: logged.append(msg))

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if any("check_termux_pkg_updates.py" in str(part) for part in command):
            raise nightly.subprocess.TimeoutExpired(cmd=command, timeout=600)
        return _Result(0)

    monkeypatch.setattr(nightly.subprocess, "run", fake_run)

    assert nightly.main(["--limit", "s24"]) == 0
    assert any(c and "ansible-playbook" in c for c in calls)
    assert any("pre-check failed" in msg for msg in logged)
