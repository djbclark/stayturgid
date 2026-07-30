#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_ui
short_description: Run a named screen-control UI task via repo Python scripts
description:
  - Orchestrates existing Mac/on-device UI automation scripts (AutoJs6
    drawer). Implementation stays in Python per ADR 002 — this module is
    not check-mode-idempotent over UI state.
  - UI tasks do not run in check mode (C(skipped=true)).
options:
  host:
    description: Fleet inventory hostname or adb alias passed to the script.
    type: str
    required: true
  task:
    description: Named UI task to run.
    type: str
    required: true
    choices:
      - enable_autojs6_drawer
  repo_root:
    description: stayturgid repository root on the control node.
    type: path
    required: true
  retries:
    description: Retry count when the script exits non-zero.
    type: int
    default: 0
  retry_delay:
    description: Seconds between retries.
    type: int
    default: 3
  python:
    description: Python interpreter for the script (defaults to current interpreter).
    type: path
"""

EXAMPLES = r"""
- name: Enable AutoJs6 fleet drawer
  stayturgid.android_common.android_ui:
    host: stock-android-device
    task: enable_autojs6_drawer
    repo_root: "{{ stayturgid_repo_root }}"
    retries: 2
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when the script ran successfully (UI tasks always report changed on success).
  type: bool
skipped:
  description: True in check mode when the task was not executed.
  type: bool
rc:
  description: Script exit code (0 on success).
  type: int
task:
  description: Task name that was requested.
  type: str
cmd:
  description: argv executed on the control node.
  type: list
"""

import os
import subprocess
import sys
import time

from ansible.module_utils.basic import AnsibleModule

TASK_SCRIPTS = {
    "enable_autojs6_drawer": "control/tools/autojs6/enable_autojs6_shizuku.py",
}


def build_argv(python, repo_root, task, host):
    rel = TASK_SCRIPTS[task]
    script = os.path.join(repo_root, rel)
    if not os.path.isfile(script):
        raise ValueError("script not found: %s" % script)
    return [python, script, host]


def run_script(argv, retries, retry_delay):
    attempt = 0
    last_rc = 1
    while attempt <= retries:
        proc = subprocess.run(argv, cwd=os.path.dirname(argv[1]))
        last_rc = proc.returncode
        if last_rc == 0:
            return last_rc
        if attempt >= retries:
            break
        time.sleep(max(0, retry_delay))
        attempt += 1
    return last_rc


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(type="str", required=True),
            task=dict(
                type="str",
                required=True,
                choices=sorted(TASK_SCRIPTS.keys()),
            ),
            repo_root=dict(type="path", required=True),
            retries=dict(type="int", default=0),
            retry_delay=dict(type="int", default=3),
            python=dict(type="path", default=sys.executable),
        ),
        supports_check_mode=True,
    )

    task = module.params["task"]
    if module.check_mode:
        module.exit_json(
            changed=False,
            skipped=True,
            task=task,
            msg="UI tasks do not run in check mode (ADR 002)",
        )

    repo_root = os.path.expanduser(module.params["repo_root"])
    try:
        argv = build_argv(
            module.params["python"],
            repo_root,
            task,
            module.params["host"],
        )
    except ValueError as exc:
        module.fail_json(msg=str(exc), task=task)

    rc = run_script(argv, module.params["retries"], module.params["retry_delay"])
    if rc != 0:
        module.fail_json(
            msg="UI task %s failed with rc=%s" % (task, rc),
            task=task,
            cmd=argv,
            rc=rc,
        )

    module.exit_json(changed=True, skipped=False, task=task, cmd=argv, rc=0)


if __name__ == "__main__":
    main()
