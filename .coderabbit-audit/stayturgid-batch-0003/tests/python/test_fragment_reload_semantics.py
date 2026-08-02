"""Assert fragment-content-change reload detection (M1-F MF-4).

Caddy imports fragments at load and vector reads its fragment --config files
at start (no-copy, design §1.3); neither is tracked by the base config or
plist change registers. Each role's "Reload <app> on fragment-content
change" task is a self-contained shell script that hashes its fragment
inputs (passed in via `environment:`, not inline Jinja) against a recorded
state file. This test extracts that script verbatim from the role's
tasks/main.yml and runs it directly against a scratch directory (no ansible
execution) to prove a fragment byte edit flips changed=false -> changed=true.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLES_DIR = ROOT / "ansible" / "roles"


def _reload_task(app: str) -> dict:
    path = ROLES_DIR / f"serverapp_{app}" / "tasks" / "main.yml"
    tasks = yaml.safe_load(path.read_text(encoding="utf-8"))
    matches = [t for t in tasks if t.get("name", "") == f"Reload {app} on fragment-content change"]
    assert len(matches) == 1, f"expected exactly one fragment-reload task for {app}"
    return matches[0]


def _strip_raw_markers(script: str) -> str:
    # The role wraps the script body in {% raw %}/{% endraw %} so Ansible's
    # Jinja templar doesn't choke on bash's ${#arr[@]} (contains a literal
    # "{#"). Extracted verbatim, those markers are just inert text to bash.
    lines = [line for line in script.splitlines() if line.strip() not in {"{% raw %}", "{% endraw %}"}]
    return "\n".join(lines)


def _run(script: str, extra_env: dict) -> str:
    script = _strip_raw_markers(script)
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **extra_env},
    )
    return result.stdout.strip()


def test_caddy_fragment_byte_change_flips_reload(tmp_path: Path) -> None:
    frag_dir = tmp_path / "fragments" / "caddy"
    frag_dir.mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    frag_file = frag_dir / "stayturgid.caddy"
    frag_file.write_text("route /a { respond 200 }\n", encoding="utf-8")

    task = _reload_task("caddy")
    script = task["ansible.builtin.shell"]["cmd"]
    env = {
        "FRAGMENT_GLOB": str(frag_dir / "*.caddy"),
        "STATE_FILE": str(config_dir / ".fragments.sha256"),
    }
    assert set(task["environment"]) == {"FRAGMENT_GLOB", "STATE_FILE"}

    assert _run(script, env) == "changed"  # no prior state file
    assert _run(script, env) == "unchanged"  # same content, second run

    frag_file.write_text(frag_file.read_text(encoding="utf-8") + "# one more byte\n", encoding="utf-8")
    assert _run(script, env) == "changed"  # content edited
    assert _run(script, env) == "unchanged"  # settles again


def test_vector_fragment_byte_change_flips_reload(tmp_path: Path) -> None:
    frag_dir = tmp_path / "fragments" / "vector"
    frag_dir.mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    sources = frag_dir / "stayturgid_sources.yaml"
    sinks = frag_dir / "stayturgid_sinks.yaml"
    sources.write_text("sources: {}\n", encoding="utf-8")
    sinks.write_text("sinks: {}\n", encoding="utf-8")

    task = _reload_task("vector")
    script = task["ansible.builtin.shell"]["cmd"]
    env = {
        "FRAGMENT_CONFIGS": f"{sources},{sinks}",
        "STATE_FILE": str(config_dir / ".fragments.sha256"),
    }
    assert set(task["environment"]) == {"FRAGMENT_CONFIGS", "STATE_FILE"}

    assert _run(script, env) == "changed"  # no prior state file
    assert _run(script, env) == "unchanged"  # same content, second run

    sinks.write_text(sinks.read_text(encoding="utf-8") + "# one more byte\n", encoding="utf-8")
    assert _run(script, env) == "changed"  # content edited
    assert _run(script, env) == "unchanged"  # settles again
