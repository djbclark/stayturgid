#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: fdroid_repo_push
short_description: Push F-Droid repos to on-device clients via fdroidrepos intents
description:
  - Fires C(fdroidrepos://) VIEW intents for each repo, trying installed client
    components in preference order (Neo Store > Droid-ify > F-Droid).
  - Falls back from explicit component to implicit intent per component when the
    activity name is stale.
  - Optionally runs C(fdroidcl update) to sync the control-node index with the
    connected device after pushing.
options:
  device:
    description: ADB device serial or C(host:5555).
    type: str
    required: true
  repos:
    description: Repo dicts with C(name), C(address), optional C(fingerprint), C(state).
    type: list
    elements: dict
    required: true
  sync_index:
    description: Run C(fdroidcl update) after pushing intents.
    type: bool
    default: true
"""

EXAMPLES = r"""
- stayturgid.fdroid.fdroid_repo_push:
    device: "{{ adb_target }}"
    repos: "{{ stayturgid_fdroid_repos }}"
  delegate_to: localhost
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_packages import (
    fdroid_components_for_device,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
    resolve_adb,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
)
from ansible_collections.stayturgid.fdroid.plugins.module_utils.fdroid_uri import (
    fdroidrepos_uri,
)


def _fdroidcl_env(device):
    import os
    env = os.environ.copy()
    env["ANDROID_SERIAL"] = device
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    return env


def am_start_failed(rc, output):
    text = (output or "").lower()
    return rc != 0 or "error" in text or "exception" in text or "does not exist" in text


def push_uri(run_command, device, uri, component=None):
    parts = ["am", "start", "-a", "android.intent.action.VIEW", "-d", "'%s'" % uri]
    if component:
        parts += ["-n", "'%s'" % component]
    rc, out, err = adb_shell(run_command, device, " ".join(parts))
    return rc, normalize_adb_output(out + "\n" + err)


def push_repo(run_command, device, uri, components):
    """Try each installed client component, then implicit per component."""
    for component in components:
        rc, output = push_uri(run_command, device, uri, component=component)
        if not am_start_failed(rc, output):
            return True, component, "explicit"
        rc, output = push_uri(run_command, device, uri, component=None)
        if not am_start_failed(rc, output):
            return True, None, "implicit"
    return False, None, "failed"


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            repos=dict(type="list", elements="dict", required=True),
            sync_index=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    device = resolve_adb(module.params["device"], module.run_command)
    repos = [
        r for r in module.params["repos"]
        if r.get("state", "present") == "present" and r.get("address")
    ]
    results = []

    if module.check_mode:
        module.exit_json(changed=bool(repos), results=[])

    adb_connect(module.run_command, device)
    components = fdroid_components_for_device(
        module.run_command, device, connect=False
    )
    if not components:
        module.exit_json(changed=False, skipped=True, reason="no fdroid client installed")

    for spec in repos:
        uri = fdroidrepos_uri(spec.get("address"), spec.get("fingerprint"))
        ok, component, mode = push_repo(module.run_command, device, uri, components)
        if not ok:
            module.fail_json(
                msg="fdroidrepos intent failed for %s" % spec.get("name"),
                uri=uri,
            )
        results.append(
            dict(
                name=spec.get("name"),
                uri=uri,
                component=component,
                mode=mode,
            )
        )

    if module.params["sync_index"] and repos:
        rc, out, err = module.run_command(
            ["fdroidcl", "update"],
            environ_update=_fdroidcl_env(device),
        )
        if rc != 0:
            module.warn("fdroidcl update after repo push failed: %s" % (err or out))

    module.exit_json(changed=True, results=results, clients_found=len(components))


if __name__ == "__main__":
    main()
