"""Where the stale-sshd-listener restart and the kex probe are wired in (p7a, 2026-11-21).

An `openssh` upgrade under a running listener made every login reset before the banner. Three
guards: the bootstrap's `ensure_sshd` (tested in test_termux_ssh_bootstrap.py), the role/nightly
restart when the listener outlived its binary, and a handshake probe from the control node after
bootstrap and after the role. These tests pin the playbook wiring.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"
PLAYBOOKS = REPO / "ansible/playbooks/fleet"

RESTART = "Restart a sshd listener that outlived its binary"
PROBE = "Probe sshd banner and key exchange from the control node"


def _load(path: Path):
    return yaml.safe_load(path.read_text())


def _names(tasks):
    return [t.get("name") for t in tasks]


def _task(tasks, name):
    return next(t for t in tasks if t.get("name") == name)


def _assert_restart_task(task):
    args = task["stayturgid.termux.termux_sshd"]
    assert args["restart_stale"] is True
    # Only the listener check: the role's other termux_sshd work stays where it is.
    assert args["ensure_running"] is False
    assert "failed_when" not in task and "ignore_errors" not in task


def _assert_probe_task(task):
    args = task["stayturgid.termux.termux_ssh_probe"]
    assert task["delegate_to"] == "localhost"
    assert "ansible_host" in args["host"]
    assert "ansible_port" in args["port"] and "8022" in args["port"]
    assert args["retries"] >= 3
    # A kex reset must fail the play, not warn.
    assert "failed_when" not in task and "ignore_errors" not in task


def test_role_restarts_a_stale_listener_right_after_the_package_steps():
    tasks = _load(ROLE / "tasks/main.yml")
    names = _names(tasks)
    restart = _task(tasks, RESTART)
    _assert_restart_task(restart)
    assert names.index("Ensure Termux packages are installed") < names.index(RESTART)
    # Before anything else that can fail the play and leave a stale listener behind.
    assert names.index(RESTART) < names.index("Re-pin Termux main mirror after pkg operations")
    # State-based: no `when` on the upgrade result or on the openssh package.
    assert "when" not in restart


def test_role_no_longer_relies_on_a_hup_handler_after_the_upgrade():
    upgrade = _task(_load(ROLE / "tasks/main.yml"), "Update and upgrade all Termux packages (if >24h since last)")
    assert "notify" not in upgrade
    # ca.yml's config reload keeps its own handler.
    assert any(h["name"] == "reload sshd" for h in _load(ROLE / "handlers/main.yml"))


def test_nightly_upgrade_restarts_then_probes_and_no_longer_swallows_failures():
    play = _load(PLAYBOOKS / "termux-pkg-upgrade.yml")[0]
    tasks = play["tasks"]
    names = _names(tasks)
    assert "Reload sshd after an upgrade" not in names
    _assert_restart_task(_task(tasks, RESTART))
    _assert_probe_task(_task(tasks, PROBE))
    upgrade = names.index("Update package indexes and full-upgrade Termux packages")
    assert upgrade < names.index(RESTART) < names.index(PROBE) < names.index("Report nightly Termux pkg result")
    # Unreachable hosts reach later tasks (ignore_unreachable): neither may run on them.
    for name in (RESTART, PROBE):
        assert "is not unreachable" in _task(tasks, name)["when"]


def test_fleet_play_probes_after_the_roles_and_their_handlers():
    play = _load(PLAYBOOKS / "fleet.yml")[0]
    # post_tasks run after the roles' handlers are flushed.
    _assert_probe_task(_task(play["post_tasks"], PROBE))
    assert "tags" not in _task(play["post_tasks"], PROBE)  # a tag-limited run (apks, quirks) stays free of it


def test_bootstrap_play_probes_after_the_bootstrap_module():
    tasks = _load(PLAYBOOKS / "bootstrap.yml")[0]["tasks"]
    names = _names(tasks)
    probe = _task(tasks, PROBE)
    _assert_probe_task(probe)
    assert names.index("Bootstrap Termux authorized_keys and sshd") < names.index(PROBE)
    # Only when the bootstrap itself ran (it is skipped when SSH already worked).
    assert probe["when"] == _task(tasks, "Bootstrap Termux authorized_keys and sshd")["when"]
