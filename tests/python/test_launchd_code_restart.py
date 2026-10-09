"""#224: a KeepAlive launchd agent must restart when only its checkout code changed.

Two mechanisms carry this: ``serverapp_landing`` (its own two agents) and the
control-node ``launchd_ensure.yml`` (any service entry with ``code_paths``).
Both hash the tracked files the agent executes and compare with the hash
recorded after its last restart. These tests pin down:

1. The listed paths cover every ``control/`` module the entry script imports
   at run time, transitively (review 2.1a on 7c57bbc found landing missing
   two; this computes the closure from the sources instead of trusting a list).
2. The control-node hash script, run verbatim against a scratch checkout,
   flips only on a tracked code edit and settles once the hash is recorded.
3. The task shapes: the restart skips labels another path already restarted
   this run, the health wait covers a code restart, and the hash is recorded
   only after that wait.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "control"
CONTROL_NODE = ROOT / "ansible" / "roles" / "control_node"
LANDING_TASKS = ROOT / "ansible" / "roles" / "serverapp_landing" / "tasks" / "main.yml"


# ── import closure ─────────────────────────────────────────────────────────


def _local_imports(path: Path) -> set[Path]:
    """Files under control/ that *path* imports, by any of the three spellings
    the scripts use: ``import control.lib.x``, ``from control.lib import x``,
    and the bare ``import x`` / ``from x import y`` that the sys.path shims
    (``control/lib``, ``control/bin``) resolve."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):  # nested too: landing/state.py imports lazily
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    found: set[Path] = set()
    for name in names:
        parts = name.split(".")
        candidates: list[Path] = []
        if parts[0] == "control":
            candidates.append(ROOT.joinpath(*parts).with_suffix(".py"))
            candidates.append(ROOT.joinpath(*parts, "__init__.py"))
        else:
            candidates.extend(CONTROL / sub / f"{parts[0]}.py" for sub in ("lib", "bin"))
        found.update(c.resolve() for c in candidates if c.is_file())
    return found


def import_closure(entry: Path) -> set[str]:
    seen: set[Path] = set()
    todo = [entry.resolve()]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        todo.extend(_local_imports(current))
    return {p.relative_to(ROOT).as_posix() for p in seen}


def _covered(code_paths: list[str], module: str) -> bool:
    """A directory entry covers every file under it; a file entry only itself."""
    return any(module == entry or module.startswith(entry.rstrip("/") + "/") for entry in code_paths)


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find(tasks: list[dict], substring: str) -> dict:
    matches = [t for t in tasks if substring in t.get("name", "")]
    assert len(matches) == 1, f"expected exactly one task matching {substring!r}, got {len(matches)}"
    return matches[0]


def _as_text(when) -> str:
    return " ".join(str(w) for w in when) if isinstance(when, list) else str(when)


CONTROL_NODE_AGENTS = {
    # defaults key -> entry script (the first path is the script the plist runs)
    "stayturgid_dashboard_code_paths": "control/bin/dashboard.py",
    "stayturgid_firerpa_mcp_code_paths": "control/bin/firerpa_mcp.py",
}


def test_control_node_code_paths_cover_each_agents_import_closure() -> None:
    defaults = _load(CONTROL_NODE / "defaults" / "main.yml")
    for key, entry in CONTROL_NODE_AGENTS.items():
        code_paths = defaults[key]
        assert code_paths[0] == entry, f"{key}: first entry must be the script the plist runs"
        for path in code_paths:
            assert (ROOT / path).is_file(), f"{key}: {path} is not a file in the checkout"
        missing = sorted(m for m in import_closure(ROOT / entry) if not _covered(code_paths, m))
        assert not missing, (
            f"{key} misses modules {entry} imports at run time; add them to "
            f"ansible/roles/control_node/defaults/main.yml: {missing}"
        )


def test_control_node_code_paths_are_wired_into_the_service_list() -> None:
    text = (CONTROL_NODE / "tasks" / "agents_ensure.yml").read_text(encoding="utf-8")
    for key in CONTROL_NODE_AGENTS:
        assert f"'code_paths': {key}" in text, f"{key} is defined but no service entry carries it"
    assert "mac_launchd_code_repo_root" in text
    assert "mac_launchd_code_state_dir" in text


def test_landing_code_paths_cover_both_agents_import_closure() -> None:
    task = _find(_load(LANDING_TASKS), "Hash landing code the agents execute")
    code_paths = task["environment"]["CODE_PATHS"].split()
    for entry in ("control/landing/landing.py", "control/landing/discover.py"):
        missing = sorted(m for m in import_closure(ROOT / entry) if not _covered(code_paths, m))
        assert not missing, f"landing CODE_PATHS misses modules {entry} imports at run time: {missing}"


# ── the control-node hash script, run verbatim ────────────────────────────


def _control_node_tasks() -> list[dict]:
    return _load(CONTROL_NODE / "tasks" / "launchd_ensure.yml")


def _hash_script() -> str:
    task = _find(_control_node_tasks(), "Hash the checkout code each KeepAlive launchd agent executes")
    assert task.get("check_mode") is False  # read-only probe: a dry run still reports the pending restart
    assert task["changed_when"] == "_mac_launchd_code_probes.stdout_lines | last == 'changed'"
    return "\n".join(
        line
        for line in task["ansible.builtin.shell"]["cmd"].splitlines()
        if line.strip() not in {"{% raw %}", "{% endraw %}"}
    )


def test_control_node_code_hash_flips_only_on_a_tracked_code_edit(tmp_path: Path) -> None:
    script = _hash_script()
    repo = tmp_path / "repo"
    (repo / "control" / "bin").mkdir(parents=True)
    (repo / "control" / "lib").mkdir()
    (repo / "control" / "bin" / "dashboard.py").write_text("print('v1')\n")
    (repo / "control" / "lib" / "fleet_health.py").write_text("v1\n")
    (repo / "control" / "lib" / "unrelated.py").write_text("v1\n")
    git = ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "v1"], check=True)
    state = tmp_path / "com.example.dashboard.sha256"
    env = {
        **os.environ,
        "LABEL": "com.example.dashboard",
        "REPO_ROOT": str(repo),
        "CODE_PATHS": "control/bin/dashboard.py control/lib/fleet_health.py",
        "STATE_FILE": str(state),
    }

    def probe() -> tuple[str, str]:
        out = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=True)
        digest, verdict = out.stdout.split()
        return digest, verdict

    digest, verdict = probe()
    assert verdict == "changed"  # no state file yet: the first deploy after this lands restarts once
    state.write_text(digest + "\n")  # what the record task does after health passes
    assert probe()[1] == "unchanged"
    (repo / "control" / "bin" / "__pycache__").mkdir()
    (repo / "control" / "bin" / "__pycache__" / "dashboard.cpython-312.pyc").write_bytes(b"\x00")
    assert probe()[1] == "unchanged"  # runtime junk is not a code change
    (repo / "control" / "lib" / "unrelated.py").write_text("v2\n")
    assert probe()[1] == "unchanged"  # a module the agent never imports
    (repo / "control" / "lib" / "fleet_health.py").write_text("v2\n")
    digest, verdict = probe()
    assert verdict == "changed"  # the incident: code edited, plist untouched
    state.write_text(digest + "\n")
    assert probe()[1] == "unchanged"
    (repo / "control" / "lib" / "fleet_health.py").unlink()
    out = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert out.returncode != 0
    assert "com.example.dashboard code hash: tracked file(s) missing" in out.stderr
    assert "control/lib/fleet_health.py" in out.stderr


# ── task shapes ───────────────────────────────────────────────────────────


def test_control_node_code_restart_skips_labels_another_path_restarted() -> None:
    tasks = _control_node_tasks()
    restart = _find(tasks, "Restart launchd agents whose checkout code changed")
    assert restart["community.general.launchd"]["state"] == "restarted"
    assert restart["loop"] == "{{ _mac_launchd_code_stale }}"
    when_text = _as_text(restart["when"])
    assert "mac_launchd_reload_labels" in when_text  # a reloaded plist already restarted it
    assert "_restarted_this_run" in when_text
    already = restart["vars"]["_restarted_this_run"]
    for registered in (
        "_mac_launchd_load_results",
        "_mac_launchd_unknown_restart_results",
        "_mac_launchd_health_restart_results",
    ):
        assert registered in already, f"{registered} not excluded from the code restart"
    # Order: every other restart path first, then ours, then the health wait.
    names = [t["name"] for t in tasks]
    assert (
        names.index("Restart keepalive launchd agent when not running or HTTP health fails")
        < names.index(restart["name"])
        < names.index("Wait for HTTP health on keepalive launchd agents")
    )


def test_control_node_health_wait_covers_a_code_restart() -> None:
    wait = _find(_control_node_tasks(), "Wait for HTTP health on keepalive launchd agents")
    assert "_code_restarted" in _as_text(wait["when"])
    assert "_mac_launchd_code_stale" in wait["vars"]["_code_restarted"]


def test_control_node_records_the_hash_only_after_the_health_wait() -> None:
    tasks = _control_node_tasks()
    record = _find(tasks, "Record the checkout code hash each launchd agent now runs")
    assert "selectattr('changed')" in record["loop"]
    assert record["ansible.builtin.copy"]["content"] == "{{ item.stdout_lines | first }}\n"
    assert tasks.index(record) > tasks.index(_find(tasks, "Wait for HTTP health on keepalive launchd agents"))
    assert tasks.index(record) == len(tasks) - 1
