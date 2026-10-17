"""The otelcol-contrib probe failure names its cause when sshd runs under run-as (2026-10-17).

`unexpected e_type: 2` from the pinned binary is the exec context: a child of a Termux
`sh` in the run-as SELinux domain (runas_app) gets it, the app's own domain does not.
That was misread as a model incompatibility twice (t2e 2026-09-20, s24 2026-10-03). The
role now reads the session's domain on a failed probe, fails with the real cause and
leaves a working boot integration in place. These tests run the real tasks with
ansible-playbook against localhost, starting at the probe.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"
OTELCOL_TASKS = ROLE / "tasks" / "otelcol.yml"
START_AT = "Probe installed otelcol-contrib runtime compatibility"

pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed")


def _run_probe(tmp_path: Path, context: str) -> tuple[int, str, Path]:
    """Run the role's otelcol tasks from the probe on with a binary that cannot run."""
    context_file = tmp_path / "attr_current"
    context_file.write_text(context)
    boot_script = tmp_path / "start-otelcol.sh"
    boot_script.write_text("#!/bin/sh\n")
    playbook = tmp_path / "play.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "stayturgid_otelcol_enabled": True,
                        "stayturgid_otelcol_version": "0.162.0",
                        "stayturgid_otelcol_binary": str(tmp_path / "no-such-otelcol-contrib"),
                        "stayturgid_otelcol_boot_script": str(boot_script),
                        "stayturgid_selinux_context_file": str(context_file),
                    },
                    "tasks": [{"ansible.builtin.import_tasks": str(OTELCOL_TASKS)}],
                }
            ]
        )
    )
    env = {
        **os.environ,
        "ANSIBLE_CALLBACK_RESULT_FORMAT": "json",
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
        "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
    }
    done = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", "--start-at-task", START_AT, str(playbook)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=120,
        check=False,
    )
    return done.returncode, done.stdout + done.stderr, boot_script


def _failure_message(stdout: str) -> str:
    """The `msg` of the first `fatal: [host]: FAILED! => {json}` result."""
    _head, marker, tail = stdout.partition("FAILED! => ")
    if not marker:
        return ""
    result, _end = json.JSONDecoder().raw_decode(tail)
    return str(result.get("msg", ""))


def test_run_as_session_gets_the_real_cause_and_keeps_the_boot_integration(tmp_path):
    rc, stdout, boot_script = _run_probe(tmp_path, "u:r:runas_app:s0:c127,c257,c512,c768\n")
    message = _failure_message(stdout)
    assert rc != 0
    assert "SELinux domain u:r:runas_app:s0:c127" in message
    assert "run-as" in message and "bootstrap-ssh" in message and "start_sshd_from_app" in message
    assert "not a model incompatibility" in message
    assert "cannot run on" not in message
    assert boot_script.exists(), "a failed probe under run-as must not remove a working boot integration"


def test_app_context_probe_failure_keeps_the_incompatibility_message_and_removes_the_boot_script(tmp_path):
    rc, stdout, boot_script = _run_probe(tmp_path, "u:r:untrusted_app_27:s0:c127,c257,c512,c768\n")
    message = _failure_message(stdout)
    assert rc != 0
    assert "cannot run on" in message
    assert "run-as" not in message
    assert not boot_script.exists()


def test_failure_tasks_sit_between_the_probe_and_the_boot_script_removal():
    names = [task.get("name", "") for task in yaml.safe_load(OTELCOL_TASKS.read_text())]
    probe = names.index(START_AT)
    context = names.index("Read the SELinux context of this session after an otelcol-contrib probe failure")
    fail = names.index("Fail an otelcol-contrib probe that ran under the run-as sshd with the real cause")
    remove = names.index("Remove otelcol-contrib boot integration after runtime incompatibility")
    assert probe < context < fail < remove
