"""The running collector restarts when its version is older than the pin.

Ansible's version test, not a string compare: 0.163.10 is newer than 0.163.2.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/tasks/otelcol.yml"
REMEMBER = "Remember whether the running otelcol-contrib is older than the deployed version"
RESTART = "Restart otelcol-contrib when the running version is older than the deployed one"

pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed")

# (probe stdout, should restart). 0.163.10 is the case a string compare gets wrong.
CASES = [
    ("otelcol-contrib version 0.162.0", True),
    ("otelcol-contrib version 0.163.1", True),
    ("otelcol-contrib version 0.163.2", False),
    ("otelcol-contrib version 0.163.10", False),
    ("otelcol-contrib version 0.164.0", False),
    ("not a version", False),
    ("", False),
]


def test_older_running_collector_restarts_and_a_newer_one_does_not(tmp_path: Path) -> None:
    loaded = yaml.safe_load(TASKS.read_text())
    chosen = [task for task in loaded if task.get("name") in {REMEMBER, RESTART}]
    assert [task["name"] for task in chosen] == [REMEMBER, RESTART]
    prefix = tmp_path / "prefix"
    bindir = prefix / "bin"
    bindir.mkdir(parents=True)
    (bindir / "bash").symlink_to("/bin/bash")

    plays = []
    logs = []
    for index, (stdout, _expect) in enumerate(CASES):
        log = tmp_path / f"log-{index}"
        logs.append(log)
        boot = tmp_path / f"boot-{index}.sh"
        boot.write_text("#!/bin/sh\nprintf '%s\\n' \"${1:-start}\" >> " + shlex.quote(str(log)) + "\n")
        boot.chmod(0o755)
        plays.append(
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "stayturgid_otelcol_enabled": True,
                    "_otelcol_version": "0.163.2",
                    "stayturgid_otelcol_boot_script": str(boot),
                    "stayturgid_otelcol_pid_file": str(tmp_path / "otelcol.pid"),
                    "termux_prefix": str(prefix),
                },
                "tasks": [
                    {
                        "name": "Seed the running otelcol-contrib probe",
                        "ansible.builtin.set_fact": {"_otelcol_running_probe": {"stdout": stdout}},
                    },
                    *chosen,
                ],
            }
        )

    playbook = tmp_path / "play.yml"
    playbook.write_text(yaml.safe_dump(plays))
    utf8 = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
    env = {
        **os.environ,
        "LC_ALL": utf8,
        "LANG": utf8,
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
        "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
    }
    done = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=180,
        check=False,
    )
    output = done.stdout + done.stderr
    assert done.returncode == 0, output[-2000:]
    for (_stdout, expect), log in zip(CASES, logs, strict=True):
        if expect:
            text = log.read_text()
            assert "stop" in text and "start" in text, text
        else:
            assert not log.exists(), log.read_text() if log.exists() else ""
