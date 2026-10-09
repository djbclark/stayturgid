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


def _run_nightly(monkeypatch, tmp_path, stdout, rc, argv=None, send_ok=True):
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
    monkeypatch.setattr(nightly.hermes_notify, "notify", lambda title, msg: notices.append(msg) or send_ok)
    monkeypatch.setattr(nightly.subprocess, "run", lambda command, **kwargs: _Result(rc, stdout=stdout))
    code = nightly.main(argv or [])
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
    # One run-level notice (review-2 4.1a), and only once while it keeps failing the same way.
    assert len(notices) == 1 and "did not complete" in notices[0] and "could not be parsed" in notices[0]
    code, records, notices = _run_nightly(monkeypatch, tmp_path, "ERROR! the playbook could not be parsed", rc=4)
    assert notices == []


_HD8_DOWN = 'fatal: [hd8]: UNREACHABLE! => {"msg": "timed out", "unreachable": true}\n...ignoring\n'
_CLEAN = "PLAY RECAP ***\np7a : ok=5 changed=1 unreachable=0 failed=0\n"


def _state(tmp_path):
    import json

    return json.loads((tmp_path / "state" / "termux-pkg-nightly.json").read_text(encoding="utf-8"))


def test_run_level_failure_is_not_an_ok_again(monkeypatch, tmp_path):
    """review-2 4.1a: a run that dies before any host ran is not a recovery."""
    _, _, notices = _run_nightly(monkeypatch, tmp_path, _HD8_DOWN, rc=0)
    assert len(notices) == 1 and "hd8 unreachable" in notices[0]

    _, _, notices = _run_nightly(monkeypatch, tmp_path, "ERROR! couldn't resolve module/action", rc=4)
    assert not any("OK again" in n for n in notices)
    assert len(notices) == 1 and "did not complete" in notices[0]
    assert _state(tmp_path)["failing"] == ["hd8:unreachable"]  # per-host set kept

    # The next completed run reports that the job runs again, with the host set as it now is.
    _, _, notices = _run_nightly(monkeypatch, tmp_path, _HD8_DOWN, rc=0)
    assert len(notices) == 1 and "runs again" in notices[0] and "hd8 unreachable" in notices[0]
    _, _, notices = _run_nightly(monkeypatch, tmp_path, _HD8_DOWN, rc=0)
    assert notices == []


def test_limited_run_is_not_compared_with_fleet_state(monkeypatch, tmp_path):
    """review-2 4.1b: `HOSTS=s24` must not announce hd8 recovered, nor overwrite the state."""
    _run_nightly(monkeypatch, tmp_path, _HD8_DOWN, rc=0)
    before = _state(tmp_path)
    for argv in (["--limit", "s24"], None):
        if argv is None:
            monkeypatch.setenv("HOSTS", "s24")
        _, _, notices = _run_nightly(monkeypatch, tmp_path, _CLEAN, rc=0, argv=argv)
        assert notices == []
        assert _state(tmp_path) == before
    monkeypatch.delenv("HOSTS")
    _, _, notices = _run_nightly(monkeypatch, tmp_path, "ERROR! broken", rc=4, argv=["--limit", "s24"])
    assert notices == [] and _state(tmp_path) == before


def test_failed_send_does_not_mark_the_change_as_notified(monkeypatch, tmp_path):
    """review-2 4.1c: a dead Hermes gateway must not swallow the alert."""
    _, _, notices = _run_nightly(monkeypatch, tmp_path, _HD8_DOWN, rc=0, send_ok=False)
    assert len(notices) == 1
    assert not (tmp_path / "state" / "termux-pkg-nightly.json").exists()
    _, _, notices = _run_nightly(monkeypatch, tmp_path, _HD8_DOWN, rc=0)  # gateway back
    assert len(notices) == 1 and "hd8 unreachable" in notices[0]
    _, _, notices = _run_nightly(monkeypatch, tmp_path, "ERROR! broken", rc=4, send_ok=False)
    assert len(notices) == 1
    _, _, notices = _run_nightly(monkeypatch, tmp_path, "ERROR! broken", rc=4)
    assert len(notices) == 1 and "did not complete" in notices[0]


def test_notify_reports_whether_the_send_worked(monkeypatch):
    import shutil

    from control.lib import hermes_notify

    monkeypatch.setattr(hermes_notify, "_hermes_bin", lambda: shutil.which("true"))
    assert hermes_notify.notify("t", "m") is True
    monkeypatch.setattr(hermes_notify, "_hermes_bin", lambda: shutil.which("false"))
    assert hermes_notify.notify("t", "m") is False
    monkeypatch.setattr(hermes_notify, "_hermes_bin", lambda: "/nonexistent/hermes")
    assert hermes_notify.notify("t", "m") is False


def test_broken_secretspec_boundary_is_recorded_and_notified(monkeypatch, tmp_path):
    """review-2 1.1a: BoundaryUnavailable used to escape as a bare traceback,
    with no termux_pkg_error record and no Hermes notice."""
    from control.lib import secretspec_exec as boundary

    def broken():
        raise boundary.BoundaryUnavailable("/var/db/sudo-secretspec exists but sudo-secretspec is not on PATH.")

    monkeypatch.setattr(boundary, "boundary_available", broken)
    code, records, notices = _run_nightly(monkeypatch, tmp_path, "", rc=0)
    assert code == 2
    assert len(records) == 1 and records[0][0][0] == "preflight" and "not on PATH" in records[0][0][1]
    assert len(notices) == 1 and "did not complete (preflight:" in notices[0]
    _, records, notices = _run_nightly(monkeypatch, tmp_path, "", rc=0)
    assert len(records) == 1 and notices == []  # telemetry nightly, Hermes once


def test_every_early_return_records_and_notifies_once(monkeypatch, tmp_path):
    """review-2 4.1d: lock, timeout, missing binary and preflight paths used to
    record telemetry only, so a nightly that never ran stayed silent."""
    import subprocess as sp

    from control.lib.ansible_context import AnsibleConfigError

    def raising(exc):
        def run(command, **kwargs):
            raise exc

        return run

    cases = {
        "timeout": (raising(sp.TimeoutExpired("ansible-playbook", 1)), 2, "upgrade", "timed out"),
        "missing": (raising(FileNotFoundError("ansible-playbook")), 2, "preflight", "not found on PATH"),
    }
    for name, (run, want_rc, phase, text) in cases.items():
        state_dir = tmp_path / name
        for attempt in (1, 2):
            context = AnsibleContext(
                config=state_dir / "ansible.cfg",
                inventory=state_dir / "hosts.yml",
                collections_path=state_dir / "collections",
                source="site overlay",
            )
            records, notices = [], []
            monkeypatch.setattr(nightly, "resolve_ansible_context", lambda repo, c=context: c)
            monkeypatch.setattr(nightly, "resolved_env", lambda repo: {"PATH": "/usr/bin:/bin"})
            monkeypatch.setattr(nightly, "require_inventory", lambda selected: None)
            monkeypatch.setattr(nightly, "LOG_DIR", state_dir / "logs")
            monkeypatch.setattr(nightly, "LOG", state_dir / "logs" / "nightly.log")
            monkeypatch.setattr(nightly, "STATE_PATH", state_dir / "state.json")
            monkeypatch.setattr(nightly, "trim_log", lambda: None)
            monkeypatch.setattr(nightly, "CHECK_UPDATES", Path("/nonexistent/check_termux_pkg_updates.py"))
            monkeypatch.setattr(nightly, "record_termux_pkg_error", lambda *a, **k: records.append((a, k)))
            monkeypatch.setattr(nightly.hermes_notify, "notify", lambda title, msg: notices.append(msg) or True)
            monkeypatch.setattr(nightly.subprocess, "run", run)
            assert nightly.main([]) == want_rc, name
            assert len(records) == 1 and records[0][0][0] == phase, name
            if attempt == 1:
                assert len(notices) == 1 and "did not complete" in notices[0] and text in notices[0], name
            else:
                assert notices == [], name  # same failure again: telemetry only

    # Preflight: a broken site config.
    def bad_context(repo):
        raise AnsibleConfigError("no inventory for this site")

    code, records, notices = _run_nightly(monkeypatch, tmp_path, "", rc=0)  # seed a clean state
    monkeypatch.setattr(nightly, "resolve_ansible_context", bad_context)
    assert notices == []
    assert nightly.main([]) == 2
    assert len(notices) == 1 and "did not complete (preflight:" in notices[0] and "no inventory" in notices[0]
    assert records[-1][0][0] == "preflight"

    # A limited or check run stays quiet, as for the other run-level failures.
    notices.clear()
    monkeypatch.setattr(nightly, "STATE_PATH", tmp_path / "quiet" / "state.json")
    assert nightly.main(["--limit", "s24"]) == 2
    assert nightly.main(["--check"]) == 2
    assert notices == []


def test_lock_held_nightly_notifies_once_with_a_stable_text(monkeypatch, tmp_path):
    """review-2 4.1d: the lock message names the holder; the notice must not."""
    notices = []
    _run_nightly(monkeypatch, tmp_path, _CLEAN, rc=0)
    monkeypatch.setattr(nightly.hermes_notify, "notify", lambda title, msg: notices.append(msg) or True)
    for holder in ("deploy_fleet.py s24", "deploy_fleet.py p7a"):
        with nightly.fleet_lock(holder):
            assert nightly.main([]) == 3
    assert len(notices) == 1 and "lock" in notices[0] and "skipped" in notices[0]
    assert "s24" not in notices[0]
