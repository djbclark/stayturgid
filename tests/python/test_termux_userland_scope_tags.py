"""#166: the `scripts` deploy scope must select exactly the on-device code push.

`deploy_fleet.py --scope scripts` becomes `ansible-playbook --tags scripts`,
so a task that ships code the boot loop or repair script executes has to carry
the tag or a scripts-scoped deploy silently leaves it stale. These tests parse
the role instead of running ansible.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "ansible_collections" / "stayturgid" / "termux" / "roles" / "termux_userland" / "tasks" / "main.yml"

# Every task that lands code on the device, plus the directories it needs and
# the check that proves the result runs.
SCRIPTS_SCOPE = {
    "Ensure stayturgid home directory tree",
    "Deploy shell scripts / shims to ~/.stayturgid/bin",
    "Deploy Python runtime scripts to ~/.stayturgid/bin",
    "Ensure on-device lib directory exists",
    "Deploy shared libs to ~/.stayturgid/lib",
    "Deploy on-device UI data files",
    "Remove retired scripts from the device",
    "Ensure Termux boot directory exists",
    "Deploy boot scripts",
    "Remove retired boot scripts from device",
    "Deploy tasker recovery scripts",
    "Prune recover.d entries no longer in the repo",
    "Verify the repair script runs",
}

# Convergence that a code-only push must not pay for (and must not skip in a
# full deploy, so none of these may carry the tag either).
OUT_OF_SCOPE = {
    "Update and upgrade all Termux packages (if >24h since last)",
    "Ensure Termux packages are installed",
    "Configure fleet SSH keys and sshd",
    "Deploy CFEngine Build artifact to device",
    "Configure edge otelcol-contrib",
    "Grant Termux permissions via privileged shell",
}


def _tasks() -> list[dict]:
    return yaml.safe_load(TASKS.read_text(encoding="utf-8"))


def _tags(task: dict) -> set[str]:
    tags = task.get("tags", [])
    return set(tags) if isinstance(tags, list) else {tags}


def test_every_code_push_task_carries_the_scripts_tag() -> None:
    by_name = {t["name"]: t for t in _tasks()}
    for name in SCRIPTS_SCOPE:
        assert name in by_name, f"task renamed or removed: {name!r}; update SCRIPTS_SCOPE here and the role"
        assert "scripts" in _tags(by_name[name]), f"{name!r} ships code but is not in the scripts scope"


def test_convergence_tasks_stay_out_of_the_scripts_scope() -> None:
    by_name = {t["name"]: t for t in _tasks()}
    for name in OUT_OF_SCOPE:
        assert name in by_name, name
        assert "scripts" not in _tags(by_name[name]), f"{name!r} is not code and must not run in a scripts push"


def test_every_synchronize_task_is_in_the_scripts_scope() -> None:
    """A new rsync-based sync is on-device code or assets until proven otherwise."""
    for task in _tasks():
        if "ansible.posix.synchronize" in task:
            assert "scripts" in _tags(task), f"{task['name']!r} syncs files but is not in the scripts scope"


def test_rsync_path_fact_runs_under_any_tag_selection() -> None:
    """The synchronize tasks read ansible_rsync_path from this set_fact."""
    task = next(t for t in _tasks() if t["name"].startswith("Resolve local rsync path"))
    assert "always" in _tags(task)
