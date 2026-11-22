"""termux_sshd restart_stale and termux_ssh_probe module behaviour.

p7a, 2026-11-21: an openssh upgrade left sshd's listener running from the replaced binary and every
login was reset before the banner. ``restart_stale`` restarts such a listener; the probe proves a login
gets as far as key exchange.
"""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import termux_ssh_probe as probe_mod
import termux_sshd as mod

from ansible_collections.stayturgid.termux.plugins.module_utils import ssh_probe

STALE = "stale deleted-exe\nsupervised=yes\n"
STALE_BARE = "stale older-than-binary\nsupervised=no\n"
FRESH = "fresh\nsupervised=yes\n"


def run(mocker, tmp_path, args, verdicts, restart_rc=0, check_mode=False):
    """Run termux_sshd.main() with the stale check answering from ``verdicts`` (last one repeats)."""
    prefix = tmp_path / "termux"
    (prefix / "bin").mkdir(parents=True, exist_ok=True)
    args = dict(args, termux_prefix=str(prefix), _ansible_check_mode=check_mode)
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", json.dumps({"ANSIBLE_MODULE_ARGS": args}).encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    mocker.patch.object(mod.time, "sleep", lambda _s: None)

    seen = {"restarts": 0, "warnings": [], "checks": 0}
    queue = list(verdicts)

    def fake_run_command(self, cmd, *a, **kw):
        script = cmd[-1]
        if 'sv" restart sshd' in script:
            seen["restarts"] += 1
            return restart_rc, "", "sv: fail: boom" if restart_rc else ""
        if "STAYTURGID_PROC" in script:
            seen["checks"] += 1
            return 0, (queue.pop(0) if len(queue) > 1 else queue[0]), ""
        return 0, "", ""

    result = {}

    def fake_exit(self, **kw):
        result.update(kw, failed=False)
        raise SystemExit(0)

    def fake_fail(self, **kw):
        result.update(kw, failed=True)
        raise SystemExit(1)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fake_fail)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.warn", lambda self, msg: seen["warnings"].append(msg))
    with pytest.raises(SystemExit):
        mod.main()
    return result, seen


def test_a_stale_runit_listener_is_restarted_and_reported_changed(mocker, tmp_path):
    out, seen = run(mocker, tmp_path, dict(restart_stale=True, ensure_running=False), [STALE, FRESH])
    assert out["failed"] is False
    assert out["changed"] is True and out["stale_restarted"] is True
    assert out["stale_listener"] == "stale deleted-exe"
    assert seen["restarts"] == 1


def test_a_fresh_listener_is_left_alone(mocker, tmp_path):
    out, seen = run(mocker, tmp_path, dict(restart_stale=True, ensure_running=False), [FRESH])
    assert out["changed"] is False and out["stale_restarted"] is False
    assert out["stale_listener"] == "fresh"
    assert seen["restarts"] == 0


def test_an_unknown_verdict_never_restarts(mocker, tmp_path):
    out, seen = run(mocker, tmp_path, dict(restart_stale=True, ensure_running=False), ["unknown no-pidfile\n"])
    assert out["changed"] is False and seen["restarts"] == 0


def test_a_stale_bare_listener_is_warned_about_not_restarted(mocker, tmp_path):
    out, seen = run(mocker, tmp_path, dict(restart_stale=True, ensure_running=False), [STALE_BARE])
    assert out["changed"] is False and out["stale_restarted"] is False
    assert out["stale_listener"] == "stale older-than-binary"
    assert seen["restarts"] == 0
    assert any("not supervised by runit" in w for w in seen["warnings"])


def test_check_mode_reports_the_restart_without_doing_it(mocker, tmp_path):
    out, seen = run(mocker, tmp_path, dict(restart_stale=True, ensure_running=False), [STALE], check_mode=True)
    assert out["changed"] is True and out["stale_restarted"] is True
    assert seen["restarts"] == 0


def test_a_listener_still_stale_after_the_restart_fails_the_task(mocker, tmp_path):
    out, seen = run(mocker, tmp_path, dict(restart_stale=True, ensure_running=False), [STALE])
    assert out["failed"] is True
    assert "still stale after sv restart" in out["msg"]
    assert seen["restarts"] == 1


def test_a_failed_sv_restart_fails_the_task(mocker, tmp_path):
    out, _seen = run(mocker, tmp_path, dict(restart_stale=True, ensure_running=False), [STALE], restart_rc=1)
    assert out["failed"] is True and "sv restart sshd failed" in out["msg"]


def test_restart_stale_is_off_by_default(mocker, tmp_path):
    out, seen = run(mocker, tmp_path, dict(ensure_running=False), [STALE])
    assert out["changed"] is False and out["stale_listener"] == "" and seen["checks"] == 0


# --- termux_ssh_probe -------------------------------------------------------------------------


def run_probe(mocker, args, outcome):
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", json.dumps({"ANSIBLE_MODULE_ARGS": args}).encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    calls = []

    def fake_probe(host, port, timeout, retries, delay):
        calls.append((host, port, timeout, retries, delay))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    result = {}
    mocker.patch.object(probe_mod, "probe", fake_probe)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.exit_json",
        lambda self, **kw: (result.update(kw, failed=False), (_ for _ in ()).throw(SystemExit(0))),
    )
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json",
        lambda self, **kw: (result.update(kw, failed=True), (_ for _ in ()).throw(SystemExit(1))),
    )
    with pytest.raises(SystemExit):
        probe_mod.main()
    return result, calls


def test_probe_module_passes_a_healthy_sshd_and_is_never_changed(mocker):
    out, calls = run_probe(mocker, dict(host="m11", retries=5), ("SSH-2.0-OpenSSH_10.6", 2))
    assert out["failed"] is False and out["changed"] is False
    assert out["banner"] == "SSH-2.0-OpenSSH_10.6" and out["attempts"] == 2
    assert calls == [("m11", 8022, 8.0, 5, 3.0)]


def test_probe_module_fails_the_play_on_a_kex_reset(mocker):
    err = ssh_probe.ProbeError("kex_exchange_identification: connection reset on m11:8022 (after 5 attempts)")
    out, _calls = run_probe(mocker, dict(host="m11", port=8022), err)
    assert out["failed"] is True and "kex_exchange_identification" in out["msg"]


def test_probe_module_runs_in_check_mode_too(mocker):
    out, calls = run_probe(mocker, dict(host="m11", _ansible_check_mode=True), ("SSH-2.0-OpenSSH_10.6", 1))
    assert out["failed"] is False and calls
