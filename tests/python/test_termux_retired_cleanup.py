"""The retired-file cleanup in termux_userland is one round-trip (#166).

It replaced two `file: state=absent` loops (~12 s of an idempotent s24 deploy,
every entry already gone). These tests run the task's script verbatim with
bash against a scratch $HOME, with RETIRED rendered from the role defaults
through the same Jinja expression the task uses, so no device or ansible run
is needed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml
from ansible.plugins.filter.core import FilterModule
from jinja2 import Environment

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"


def _task() -> dict:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    matches = [t for t in tasks if t.get("name") == "Remove retired scripts from the device"]
    assert len(matches) == 1
    return matches[0]


def _retired(defaults: dict) -> str:
    env = Environment()
    env.filters.update(FilterModule().filters())
    expr = _task()["environment"]["RETIRED"].strip()
    assert expr.startswith("{{") and expr.endswith("}}")
    return env.from_string(expr).render(**defaults)


def _run(home: Path, retired: str, dry_run: bool) -> subprocess.CompletedProcess:
    script = _task()["ansible.builtin.shell"]["cmd"]
    env = {**os.environ, "TERMUX_HOME": str(home), "DRY_RUN": "1" if dry_run else "0", "RETIRED": retired}
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)


@pytest.fixture
def defaults() -> dict:
    return yaml.safe_load((ROLE / "defaults/main.yml").read_text(encoding="utf-8"))


def test_retired_list_covers_both_old_loops(defaults: dict) -> None:
    lines = _retired(defaults).splitlines()
    assert lines[: len(defaults["stayturgid_retired_scripts"])] == defaults["stayturgid_retired_scripts"]
    assert [f".stayturgid/bin/{name}" for name in defaults["stayturgid_retired_py_scripts"]] == lines[
        len(defaults["stayturgid_retired_scripts"]) :
    ]


def test_idempotent_run_reports_none(tmp_path: Path, defaults: dict) -> None:
    result = _run(tmp_path, _retired(defaults), dry_run=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "none"


def test_removes_present_entries_and_keeps_everything_else(tmp_path: Path, defaults: dict) -> None:
    bin_dir = tmp_path / ".stayturgid/bin"
    bin_dir.mkdir(parents=True)
    old_root = tmp_path / defaults["stayturgid_retired_scripts"][0]
    old_root.write_text("x")
    old_py = bin_dir / defaults["stayturgid_retired_py_scripts"][0]
    old_py.write_text("x")
    keep = bin_dir / "stayturgid_repair.py"
    keep.write_text("x")

    dry = _run(tmp_path, _retired(defaults), dry_run=True)
    assert dry.returncode == 0, dry.stderr
    assert dry.stdout.startswith("removed:")
    assert old_root.exists() and old_py.exists()  # check mode deletes nothing

    real = _run(tmp_path, _retired(defaults), dry_run=False)
    assert real.returncode == 0, real.stderr
    assert real.stdout.startswith("removed:")
    assert not old_root.exists() and not old_py.exists()
    assert keep.exists()
    assert _run(tmp_path, _retired(defaults), dry_run=False).stdout.strip() == "none"


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside", ".stayturgid/../../outside"])
def test_refuses_paths_that_escape_home(tmp_path: Path, bad: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("x")
    result = _run(home, bad, dry_run=False)
    assert result.returncode == 2
    assert "refusing unsafe retired path" in result.stderr
    assert outside.exists()
