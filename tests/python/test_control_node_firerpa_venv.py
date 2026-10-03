"""Guards for the two things a plain `just deploy` could not previously converge.

Both were fixed by hand on 2026-10-03 and neither would have come back on its own:
the hand-made ~/.venv-stayturgid-firerpa (no tracked requirements, nothing creating
it, yet a live launchd service points at its interpreter), and the ~/ops Claude
memory path (a real directory where every sibling is a symlink, so memory written
there is untracked).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible/roles/control_node"
DEFAULTS = ROLE / "defaults/main.yml"
VENV_TASKS = ROLE / "tasks/firerpa_venv.yml"
MEMORY_TASKS = ROLE / "tasks/ops_memory_link.yml"
AGENTS = ROLE / "tasks/agents.yml"
PREREQS = ROLE / "tasks/prereqs.yml"
REQUIREMENTS = REPO / "control/requirements-firerpa-venv.txt"
FIRERPA_DEFAULTS = REPO / "ansible_collections/stayturgid/firerpa/roles/firerpa/defaults/main.yml"


def _defaults() -> dict:
    return yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))


# --- the venv is tracked and converged ---------------------------------------


def test_the_venv_has_tracked_requirements_at_all():
    """It previously had none, which is why nothing could rebuild it."""
    assert REQUIREMENTS.is_file()


def test_requirements_pin_every_load_bearing_ceiling_exactly():
    text = REQUIREMENTS.read_text(encoding="utf-8")
    # Exact pins, not ranges: a resolver free to move inside a range is how a venv
    # behind a running service drifts.
    assert "mcp==1.28.1" in text, "mcp 2.x removes mcp.server.fastmcp and breaks firerpa_mcp.py"
    assert "grpcio==1.74.0" in text, "lamda caps grpcio at <=1.82.0 and 1.82.0 is yanked"
    assert "grpcio-tools==1.74.0" in text
    assert "protobuf==6.33.6" in text, "grpcio-tools 1.74.0 requires protobuf<7"


def test_the_client_is_fetched_from_the_fork_mirror_not_upstream():
    """uv rejects upstream's sdist: filename says lamda-client-py, metadata says lamda."""
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert "github.com/djbclark/lamda/releases/download/" in text
    assert "lamda-10.9.tar.gz" in text
    assert "lamda-client-py" not in text.split("# ")[-1], "do not point at upstream's rejected name"


def test_the_client_version_cannot_drift_from_the_pinned_server_version():
    """The whole point of the pin: client and server move together."""
    server = yaml.safe_load(FIRERPA_DEFAULTS.read_text(encoding="utf-8"))["firerpa_version"]
    client = _defaults()["stayturgid_firerpa_client_version"]
    assert client == server, f"client pin {client} != server pin {server}"
    assert f"lamda-{server}.tar.gz" in REQUIREMENTS.read_text(encoding="utf-8")


def test_the_venv_is_converged_from_that_file_and_verified_afterwards():
    tasks = yaml.safe_load(VENV_TASKS.read_text(encoding="utf-8"))
    names = [t["name"] for t in tasks]
    assert any("Create the FIRERPA control-node venv when absent" in n for n in names)
    assert any("Converge the FIRERPA control-node venv" in n for n in names)
    # A silent no-op would leave the live MCP service on a stale client.
    assert any(t.get("ansible.builtin.assert") for t in tasks), "convergence must be asserted"
    body = VENV_TASKS.read_text(encoding="utf-8")
    assert "--requirement" in body
    assert "importlib.metadata" in body, "this venv has no pip"


def test_the_venv_is_converged_before_the_plist_that_points_at_it():
    body = AGENTS.read_text(encoding="utf-8")
    assert body.index("firerpa_venv.yml") < body.index("firerpa-mcp.plist.j2")


# --- the memory symlink, and above all that it cannot destroy anything --------


def test_the_memory_link_is_converged_from_prereqs():
    assert "ops_memory_link.yml" in PREREQS.read_text(encoding="utf-8")


def test_the_memory_link_never_force_replaces_a_populated_directory():
    """Forcing would destroy untracked memory files -- the exact loss this prevents."""
    tasks = yaml.safe_load(MEMORY_TASKS.read_text(encoding="utf-8"))
    # Inspect parsed task arguments, not raw text: the file mentions `force: yes`
    # in a comment explaining why it is not used.
    for task in tasks:
        args = task.get("ansible.builtin.file") or {}
        assert not args.get("force"), f"{task['name']} must not force-replace a path"
    link = next(t for t in tasks if t["name"].startswith("Link the ~/ops Claude memory path"))
    when = " ".join(str(c) for c in link["when"])
    assert "OCCUPIED" not in when
    for state in ("ABSENT", "EMPTYDIR", "LINK"):
        assert state in when, f"{state} must be a safe-to-link state"


def test_an_occupied_memory_path_is_reported_rather_than_silently_skipped():
    tasks = yaml.safe_load(MEMORY_TASKS.read_text(encoding="utf-8"))
    warn = next(t for t in tasks if t["name"].startswith("Warn when"))
    assert "OCCUPIED" in " ".join(str(c) for c in warn["when"])


def test_only_an_empty_placeholder_directory_is_ever_removed():
    tasks = yaml.safe_load(MEMORY_TASKS.read_text(encoding="utf-8"))
    remove = next(t for t in tasks if t["name"].startswith("Remove the empty placeholder"))
    assert remove["ansible.builtin.file"]["state"] == "absent"
    assert "EMPTYDIR" in " ".join(str(c) for c in remove["when"])


def test_the_classifier_runs_in_check_mode_so_dry_runs_are_honest():
    tasks = yaml.safe_load(MEMORY_TASKS.read_text(encoding="utf-8"))
    probe = next(t for t in tasks if t["name"].startswith("Classify"))
    assert probe.get("check_mode") is False
    assert probe.get("changed_when") is False


def test_both_fixes_can_be_disabled_without_editing_tasks():
    defaults = _defaults()
    assert defaults["stayturgid_firerpa_venv_managed"] is True
    assert defaults["stayturgid_ops_memory_link_managed"] is True


def test_the_cfengine_pin_is_idempotent_not_changed_every_run():
    """The token PINNED is a substring of ALREADY_PINNED, so a bare `in` test on
    the no-op path reported changed on every deploy. Both conditions are required."""
    tasks = yaml.safe_load(PREREQS.read_text(encoding="utf-8"))
    pin = next(t for t in tasks if "CFEngine" in t["name"])
    changed = pin["changed_when"]
    assert isinstance(changed, list), "a single substring test matches ALREADY_PINNED too"
    joined = " ".join(changed)
    assert "'PINNED' in" in joined
    assert "'ALREADY_PINNED' not in" in joined
