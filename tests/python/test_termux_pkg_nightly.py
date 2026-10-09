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
        secretspec_exec.BOUNDARY_BIN,
        "run",
        "--reason",
        secretspec_exec.RUN_REASON,
        "--",
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


def test_upgrade_playbook_continues_past_unreachable_hosts() -> None:
    """serial=1 + default max_fail_percentage=0 aborted remaining hosts when
    p7a timed out (2026-09-26 recap never reached t2e/hd8)."""
    import yaml

    plays = yaml.safe_load(nightly.PLAYBOOK.read_text(encoding="utf-8"))
    play = plays[0]
    assert play.get("ignore_unreachable") is True
    assert play.get("max_fail_percentage") == 100


# ── #310: per-host telemetry and a deduplicated Hermes notice ─────────────

_UNREACHABLE_AND_FAILED = """\
TASK [Update package indexes and full-upgrade Termux packages] ****************
fatal: [hd8]: UNREACHABLE! => {"changed": false, "msg": "Failed to connect to the host via ssh: ssh: connect to host 100.0.0.13 port 8022: Operation timed out", "unreachable": true}
...ignoring
fatal: [s24]: FAILED! => {"changed": false, "msg": "apt-get full-upgrade failed: E: Could not get lock"}
ok: [p7a]

PLAY RECAP *********************************************************************
hd8                        : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=4
p7a                        : ok=5    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
s24                        : ok=2    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
"""


def test_parse_host_failures_finds_ignored_unreachable_and_failed_hosts():
    failures = nightly.parse_host_failures(_UNREACHABLE_AND_FAILED)
    assert set(failures) == {"hd8", "s24"}
    assert failures["hd8"]["status"] == "unreachable"
    assert "Operation timed out" in failures["hd8"]["error"]
    assert failures["s24"] == {"status": "failed", "error": "apt-get full-upgrade failed: E: Could not get lock"}


def test_parse_host_failures_falls_back_to_the_recap():
    out = "PLAY RECAP ***\nt2e : ok=1 changed=0 unreachable=1 failed=0 skipped=0\nx : ok=1 changed=0 unreachable=0 failed=2\n"
    failures = nightly.parse_host_failures(out)
    assert failures["t2e"]["status"] == "unreachable"
    assert failures["x"]["status"] == "failed"


def test_parse_host_failures_is_empty_for_a_clean_run():
    assert nightly.parse_host_failures("PLAY RECAP ***\np7a : ok=5 changed=1 unreachable=0 failed=0\n") == {}


def _run_nightly(monkeypatch, tmp_path, stdout, rc):
    context = AnsibleContext(
        config=tmp_path / "site" / "ansible.cfg",
        inventory=tmp_path / "site" / "inventory" / "hosts.yml",
        collections_path=tmp_path / "collections",
        source="site overlay",
    )
    records, notices = [], []
    monkeypatch.setattr(nightly, "resolve_ansible_context", lambda repo: context)
    monkeypatch.setattr(nightly, "resolved_env", lambda repo: {"PATH": "/usr/bin:/bin"})
    monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(nightly, "LOG", tmp_path / "logs" / "nightly.log")
    monkeypatch.setattr(nightly, "STATE_PATH", tmp_path / "state" / "termux-pkg-nightly.json")
    monkeypatch.setattr(nightly, "trim_log", lambda: None)
    monkeypatch.setattr(nightly, "CHECK_UPDATES", Path("/nonexistent/check_termux_pkg_updates.py"))
    monkeypatch.setattr(nightly, "record_termux_pkg_error", lambda *a, **k: records.append((a, k)))
    monkeypatch.setattr(nightly.hermes_notify, "notify", lambda title, msg: notices.append(msg))
    monkeypatch.setattr(nightly.subprocess, "run", lambda command, **kwargs: _Result(rc, stdout=stdout))
    code = nightly.main([])
    return code, records, notices


def test_nightly_records_each_failing_host_and_notifies_once(monkeypatch, tmp_path):
    code, records, notices = _run_nightly(monkeypatch, tmp_path, _UNREACHABLE_AND_FAILED, rc=2)
    assert code == 1
    by_host = {k["host"]: a[0] for a, k in records}
    assert by_host == {"hd8": "unreachable", "s24": "upgrade"}
    assert len(notices) == 1 and "hd8 unreachable" in notices[0] and "s24 failed" in notices[0]

    # Same failing set the next night: telemetry again, Hermes silent.
    code, records, notices = _run_nightly(monkeypatch, tmp_path, _UNREACHABLE_AND_FAILED, rc=2)
    assert len(records) == 2 and notices == []

    # Recovery is a change too.
    clean = "PLAY RECAP ***\np7a : ok=5 changed=1 unreachable=0 failed=0\n"
    code, records, notices = _run_nightly(monkeypatch, tmp_path, clean, rc=0)
    assert code == 0 and records == []
    assert len(notices) == 1 and "OK again" in notices[0]


def test_unreachable_only_run_stays_rc0_but_is_recorded(monkeypatch, tmp_path):
    out = 'fatal: [hd8]: UNREACHABLE! => {"msg": "timed out", "unreachable": true}\n...ignoring\n'
    code, records, notices = _run_nightly(monkeypatch, tmp_path, out, rc=0)
    assert code == 0
    assert [(a[0], k["host"]) for a, k in records] == [("unreachable", "hd8")]
    assert len(notices) == 1


def test_nonzero_rc_without_a_host_still_records_one_run_level_error(monkeypatch, tmp_path):
    code, records, notices = _run_nightly(monkeypatch, tmp_path, "ERROR! the playbook could not be parsed", rc=4)
    assert code == 1
    assert len(records) == 1 and records[0][0][0] == "upgrade" and "host" not in records[0][1]
    assert notices == []  # no per-host set changed; the run-level record carries it
