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


def _block_with_restart(tasks, block_name):
    block = _task(tasks, block_name)
    # `always`, so a package failure after dpkg replaced openssh still restarts the listener
    # (the failure is raised afterwards): the next run could not connect to fix it.
    _assert_restart_task(_task(block["always"], RESTART))
    return block


def test_role_restarts_a_stale_listener_even_when_a_package_step_fails():
    tasks = _load(ROLE / "tasks/main.yml")
    block = _block_with_restart(tasks, "Upgrade and install Termux packages, then restart a stale sshd")
    assert _names(block["block"]) == [
        "Update and upgrade all Termux packages (if >24h since last)",
        "Ensure Termux packages are installed",
    ]
    names = _names(tasks)
    assert names.index(block["name"]) < names.index("Re-pin Termux main mirror after pkg operations")
    # State-based: no `when` on the upgrade result or on the openssh package.
    assert "when" not in _task(block["always"], RESTART)
    assert "rescue" not in block and "ignore_errors" not in block


def test_role_no_longer_relies_on_a_hup_handler_after_the_upgrade():
    block = _task(_load(ROLE / "tasks/main.yml"), "Upgrade and install Termux packages, then restart a stale sshd")
    upgrade = _task(block["block"], "Update and upgrade all Termux packages (if >24h since last)")
    assert "notify" not in upgrade
    # ca.yml's config reload keeps its own handler.
    assert any(h["name"] == "reload sshd" for h in _load(ROLE / "handlers/main.yml"))


def test_nightly_upgrade_restarts_in_always_and_probes_last_without_swallowing_failures():
    tasks = _load(PLAYBOOKS / "termux-pkg-upgrade.yml")[0]["tasks"]
    names = _names(tasks)
    assert "Reload sshd after an upgrade" not in names
    block = _block_with_restart(tasks, "Upgrade Termux packages, then restart a stale sshd")
    assert _names(block["block"]) == ["Update package indexes and full-upgrade Termux packages"]
    # Unreachable hosts reach later tasks (ignore_unreachable): neither may run on them.
    assert "is not unreachable" in _task(block["always"], RESTART)["when"]
    probe = _task(tasks, PROBE)
    _assert_probe_task(probe)
    assert "is not unreachable" in probe["when"]
    # Last: after the telemetry record, so a failed probe cannot make an upgraded host look skipped.
    assert names[-1] == PROBE
    assert names.index("Record this host's result on the control node for telemetry") < names.index(PROBE)


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
