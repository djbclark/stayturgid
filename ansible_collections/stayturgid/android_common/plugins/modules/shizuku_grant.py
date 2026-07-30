#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: shizuku_grant
short_description: Grant Shizuku API access to an app via the privileged adb shell
description:
  - Grants C(moe.shizuku.manager.permission.API_V23) with C(pm grant) and adds the
    app's uid to Shizuku's C(shizuku.json) authorization file, preserving all
    other entries.
  - Runs on the control node against an adb target with a privileged shell
    (Shizuku adbd, uid 2000).
  - Fails rather than clobbering C(shizuku.json) when the file exists but cannot
    be read.
options:
  device:
    description: ADB device serial or C(host:5555) target with privileged shell.
    type: str
    required: true
  package:
    description: App package to authorize (e.g. org.stayturgid.agent, com.termux).
    type: str
    required: true
  connect:
    description: Run C(adb connect) before other operations (for wireless targets).
    type: bool
    default: true
  shizuku_json:
    description: Path to Shizuku's authorization file on the device.
    type: str
    default: /data/local/tmp/shizuku/shizuku.json
  staging_path:
    description: Shared-storage staging path used when pushing the patched file.
    type: str
    default: /sdcard/Download/shizuku-grant.json
"""

EXAMPLES = r"""
- name: Grant Shizuku to Neo Store
  stayturgid.android_common.shizuku_grant:
    device: "{{ adb_target }}"
    package: com.machiav3lli.fdroid
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when shizuku.json was updated.
  type: bool
uid:
  description: Resolved app uid.
  type: str
"""

import os
import tempfile

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.shizuku import (
    SHIZUKU_PERMISSION,
    parse_uid,
    patch_shizuku_json,
)

try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_timeout import (
        DEFAULT_SLOW_TIMEOUT,
        run_command_with_timeout,
    )
except ImportError:
    import os
    import sys

    _mod_utils = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "module_utils")
    if _mod_utils not in sys.path:
        sys.path.insert(0, _mod_utils)
    from adb_timeout import (
        DEFAULT_SLOW_TIMEOUT,
        run_command_with_timeout,
    )


def read_shizuku_json(run_command, device, path):
    """(text, ok). Missing file is ok (fresh config); unreadable is not."""
    rc, _out, _err = adb_shell(run_command, device, "test -f %s" % path)
    if rc != 0:
        return "", True
    rc, out, _err = adb_shell(run_command, device, "cat %s" % path)
    text = normalize_adb_output(out)
    if rc != 0 or not text:
        return "", False
    return text, True


def push_shizuku_json(module, device, content, staging, path):
    tmp = tempfile.NamedTemporaryFile("w", dir=module.tmpdir, delete=False)
    try:
        tmp.write(content)
        tmp.close()
        rc, _out, err = run_command_with_timeout(
            module.run_command,
            ["adb", "-s", device, "push", tmp.name, staging],
            timeout=DEFAULT_SLOW_TIMEOUT,
            get_bin_path_fn=module.get_bin_path,
        )
        if rc != 0:
            return False, "adb push failed: %s" % normalize_adb_output(err)
    finally:
        os.unlink(tmp.name)
    rc, _out, err = adb_shell(
        module.run_command,
        device,
        "cp %s %s && chmod 666 %s" % (staging, path, path),
    )
    if rc != 0:
        return False, "install into %s failed: %s" % (path, normalize_adb_output(err))
    return True, "installed"


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            package=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
            shizuku_json=dict(type="str", default="/data/local/tmp/shizuku/shizuku.json"),
            staging_path=dict(type="str", default="/sdcard/Download/shizuku-grant.json"),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    pkg = module.params["package"]
    json_path = module.params["shizuku_json"]

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    rc, _out, _err = adb_shell(module.run_command, device, "true")
    if rc != 0:
        module.fail_json(msg="no adb shell on %s — connect device and ensure Shizuku adbd is up" % device)

    rc, out, _err = adb_shell(module.run_command, device, "pm list packages -U %s" % pkg)
    uid = parse_uid(out if rc == 0 else "")
    if not uid:
        module.fail_json(msg="%s not installed on %s" % (pkg, device))

    current, ok = read_shizuku_json(module.run_command, device, json_path)
    if not ok:
        module.fail_json(msg="unreadable %s — aborting to avoid clobbering existing grants" % json_path)

    patched = patch_shizuku_json(current, uid, pkg)
    json_changed = patched.strip() != (current or "").strip()

    if module.check_mode:
        module.exit_json(changed=json_changed, uid=uid)

    # pm grant is idempotent and cheap; always ensure it.
    adb_shell(module.run_command, device, "pm grant %s %s" % (pkg, SHIZUKU_PERMISSION))

    if json_changed:
        pushed, msg = push_shizuku_json(module, device, patched, module.params["staging_path"], json_path)
        if not pushed:
            module.fail_json(msg=msg)

    module.exit_json(changed=json_changed, uid=uid)


if __name__ == "__main__":
    main()
