#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: termux_pkg
short_description: Manage Termux packages with update/upgrade recovery
description:
  - Installs or upgrades packages on Termux over SSH with non-interactive apt/dpkg options.
  - Runs C(pkg update) and optional C(pkg upgrade) before install; uses C(--force-confold) for conffile prompts.
options:
  name:
    description: Package name or list of names.
    type: raw
    required: true
  state:
    description: Target state.
    type: str
    choices: [present, latest, absent]
    default: present
  update_cache:
    description: Run C(pkg update) before other operations.
    type: bool
    default: true
  upgrade:
    description: Run C(pkg upgrade -y) before install when C(state=present) or C(state=latest).
    type: bool
    default: true
  force_confold:
    description: Pass dpkg/apt options to keep existing conffiles without prompting.
    type: bool
    default: true
"""

RETURN = r"""
upgraded_packages:
  description:
    - C(name version) for each package apt set up during the upgrade step
      (upgraded or newly pulled in), from its C(Setting up) lines. Empty in
      check mode and when nothing was upgraded. Capped at 200 entries.
  returned: always
  type: list
  elements: str
index_update_failed:
  description:
    - True when C(pkg update) failed and the module continued with the cached
      package indexes. A host that keeps reporting this is upgrading against a
      stale or dead mirror (stayturgid#310).
  returned: always
  type: bool
"""

EXAMPLES = r"""
- name: Ensure Termux packages
  termux_pkg:
    name:
      - openssh
      - android-tools
    state: present
    update_cache: true
    upgrade: true
"""

import re

from ansible.module_utils.basic import AnsibleModule


def _shell(module, script):
    prefix = module.params.get("_termux_prefix", "/data/data/com.termux/files/usr")
    bash = prefix + "/bin/bash"
    env = ("export PATH=%s/bin:$PATH\nexport DEBIAN_FRONTEND=noninteractive\n") % prefix
    if module.params["force_confold"]:
        env += "export APT_OPTS='-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold'\n"
    else:
        env += "export APT_OPTS=''\n"
    cmd = env + script
    return module.run_command([bash, "-c", cmd], use_unsafe_shell=False)


def _pkg_list(module, names):
    if names is None:
        return []
    if isinstance(names, str):
        return [names]
    return list(names)


# `Setting up openssh (10.2p1-1) ...` — one line per package apt configured.
_SETTING_UP_RE = re.compile(r"^Setting up (\S+) \(([^)]+)\)", re.MULTILINE)
_MAX_UPGRADED = 200


def _setting_up(output):
    """`name version` for each package apt set up, in order, without repeats."""
    seen = []
    for name, version in _SETTING_UP_RE.findall(output or ""):
        entry = "%s %s" % (name, version)
        if entry not in seen:
            seen.append(entry)
    return seen[:_MAX_UPGRADED]


def _installed(module, pkg):
    rc, out, err = _shell(
        module,
        "dpkg-query -W -f='${Status}' '%s' 2>/dev/null | grep -q 'install ok installed'" % pkg,
    )
    return rc == 0


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type="raw", required=False, default=[]),
            state=dict(type="str", default="present", choices=["present", "latest", "absent"]),
            update_cache=dict(type="bool", default=True),
            upgrade=dict(type="bool", default=True),
            force_confold=dict(type="bool", default=True),
            _termux_prefix=dict(type="str", default="/data/data/com.termux/files/usr"),
        ),
        supports_check_mode=True,
    )

    names = _pkg_list(module, module.params["name"])
    state = module.params["state"]
    changed = False
    messages = []
    # Reported on every exit so the nightly can record them per host (#310).
    report = {"upgraded_packages": [], "index_update_failed": False}

    # update/upgrade mutate the device — skip both in check mode.
    if module.params["update_cache"] and not module.check_mode:
        rc, out, err = _shell(module, "pkg update")
        if rc != 0:
            # Mirror sync hiccups are routine; apt keeps the old indexes
            # ("They have been ignored, or old ones used instead"), so warn
            # and continue — a truly unusable cache fails at install below.
            module.warn("pkg update failed (rc=%s, mirror sync?) — continuing with cached package indexes" % rc)
            messages.append("pkg update failed; used cached indexes")
            report["index_update_failed"] = True
        elif "Fetched" in out or "Get:" in out:
            changed = True

    if module.params["upgrade"] and state in ("present", "latest") and not module.check_mode:
        rc, out, err = _shell(
            module,
            "apt-get -y $APT_OPTS full-upgrade 2>&1 || pkg upgrade -y",
        )
        if rc != 0:
            module.fail_json(msg="pkg upgrade failed", rc=rc, stdout=out, stderr=err, **report)
        report["upgraded_packages"] = _setting_up(out)
        if re.search(r"[1-9][0-9]* upgraded", out):
            changed = True
            messages.append("upgraded packages")

    if not names:
        module.exit_json(changed=changed, msg=messages or "update/upgrade complete", **report)

    if state == "absent":
        for pkg in names:
            if _installed(module, pkg):
                if module.check_mode:
                    changed = True
                    continue
                rc, out, err = _shell(module, "pkg uninstall -y %s" % pkg)
                if rc != 0:
                    module.fail_json(msg="failed to remove %s" % pkg, stdout=out, stderr=err)
                changed = True
        module.exit_json(changed=changed, msg=messages, **report)

    missing = [p for p in names if not _installed(module, p)]
    need_upgrade = state == "latest"

    if not missing and not need_upgrade:
        module.exit_json(changed=changed, msg="All requested packages already installed", **report)

    if module.check_mode:
        module.exit_json(changed=True, would_install=missing, **report)

    if missing or need_upgrade:
        # Cache was already refreshed above when update_cache is set — no
        # need to re-run update/upgrade before the install.
        install_list = " ".join(names if need_upgrade else missing)
        rc, out, err = _shell(module, "pkg install -y %s" % install_list)
        if rc != 0:
            module.fail_json(msg="pkg install failed", rc=rc, stdout=out, stderr=err)
        changed = True
        messages.append("installed: %s" % install_list)

    module.exit_json(changed=changed, msg=messages, **report)


if __name__ == "__main__":
    main()
