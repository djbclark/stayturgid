#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: play_apps
short_description: Ensure Play apps are installed via apkeep/gplaycli + adb
description:
  - Downloads APKs on the control node (C(apkeep) or C(gplaycli)) and installs
    on a device with C(adb). Optionally spoofs C(com.android.vending) as installer.
  - Does not install Aurora Store — use the C(play_store) role / Obtainium first.
  - Google Play downloads require credentials on the control node (env vars or
    gplaycli.conf); see C(play/README.md).
options:
  apps:
    description: Apps to ensure.
    type: list
    elements: dict
    required: true
    suboptions:
      id:
        type: str
        required: true
        description: Android package name (app id).
      apk_path:
        type: str
        required: false
        description: Use this APK instead of downloading.
  device:
    description: ADB target or fleet alias (resolved on control node).
    type: str
    default: localhost:5555
  state:
    description: Target state.
    type: str
    choices: [present, absent]
    default: present
  download_backend:
    description: Downloader when C(apk_path) is omitted.
    type: str
    choices: [apkeep, gplaycli, none]
    default: apkeep
  apkeep_source:
    description: C(apkeep -d) source when backend is apkeep.
    type: str
    default: apk-pure
  apkeep_bin:
    type: str
    default: apkeep
  gplaycli_bin:
    type: str
    default: play/mac/gplaycli.sh
  gplaycli_config:
    type: str
    default: ""
  download_dir:
    type: str
    default: /tmp/stayturgid-play-apps
  spoof_play_installer:
    description: Pass C(-i com.android.vending) to adb install.
    type: bool
    default: true
  installer_package:
    type: str
    default: com.android.vending
author:
  - stayturgid project
"""

EXAMPLES = r"""
- name: Install a Play app (apk-pure mirror)
  stayturgid.fleet.play_apps:
    device: p7a
    apps:
      - id: com.google.android.apps.authenticator2
    download_backend: apkeep
    apkeep_source: apk-pure

- name: Install from a local APK
  stayturgid.fleet.play_apps:
    device: p7a
    apps:
      - id: com.example.app
        apk_path: /tmp/com.example.app.apk
    download_backend: none
"""

RETURN = r"""
changed:
  type: bool
installed:
  type: list
  elements: str
removed:
  type: list
  elements: str
device_resolved:
  type: str
output:
  type: list
  elements: str
"""

import glob
import os
import re

from ansible.module_utils.basic import AnsibleModule

DEVICES_CONF = os.path.expanduser("~/.config/stayturgid/devices.conf")
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)


def device_row(alias):
    try:
        with open(DEVICES_CONF, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts and parts[0] == alias:
                    return tuple((parts[1:] + ["-", "-", "-"])[:3])
    except OSError:
        pass
    return None


def resolve_device(alias, module):
    row = device_row(alias)
    if row:
        usb, ts_ip, _lan = row
        if usb != "-":
            rc, out, _err = module.run_command(["adb", "devices"])
            if rc == 0 and ("%s\tdevice" % usb) in (out or ""):
                return usb
        if ts_ip and ts_ip != "-":
            return "%s:5555" % ts_ip
    return alias


def run_cmd(module, cmd):
    rc, out, err = module.run_command(cmd)
    text = ((out or "") + ("\n" + err if err else "")).strip()
    return rc, text


def package_installed(module, device, pkg):
    rc, out = run_cmd(
        module,
        ["adb", "-s", device, "shell", "pm", "list", "packages", "--user", "0", pkg],
    )
    return rc == 0 and ("package:%s" % pkg) in (out or "")


def find_apk(download_dir, pkg):
    patterns = [
        os.path.join(download_dir, "%s*.apk" % pkg),
        os.path.join(download_dir, "**", "%s*.apk" % pkg),
        os.path.join(download_dir, "*.apk"),
        os.path.join(download_dir, "**", "*.apk"),
    ]
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat, recursive="**" in pat))
    found = sorted(set(found), key=os.path.getmtime, reverse=True)
    return found[0] if found else None


def apkeep_auth_args(module):
    args = []
    email = os.environ.get("GPLAY_EMAIL", "")
    aas = os.environ.get("GPLAY_AAS_TOKEN", "")
    auth = os.environ.get("GPLAY_AUTH_TOKEN", "")
    oauth = os.environ.get("GPLAY_OAUTH_TOKEN", "")
    if email:
        args.extend(["-e", email])
    if aas:
        args.extend(["-t", aas])
    if auth:
        args.extend(["--auth-token", auth])
    if oauth:
        args.extend(["--oauth-token", oauth])
    if module.params.get("apkeep_accept_tos"):
        args.append("--accept-tos")
    return args


def download_apkeep(module, pkg, dest):
    os.makedirs(dest, exist_ok=True)
    cmd = [
        module.params["apkeep_bin"],
        "-a",
        pkg,
        "-d",
        module.params["apkeep_source"],
        "-r",
        "1",
    ] + apkeep_auth_args(module) + [dest]
    return run_cmd(module, cmd)


def download_gplaycli(module, pkg, dest):
    os.makedirs(dest, exist_ok=True)
    gpath = module.params["gplaycli_bin"]
    if not os.path.isabs(gpath):
        gpath = os.path.join(REPO_ROOT, gpath)
    cmd = [gpath, "-y", "-d", pkg, "-l", dest]
    cfg = module.params.get("gplaycli_config") or ""
    if cfg:
        cmd.extend(["-c", os.path.expanduser(cfg)])
    return run_cmd(module, cmd)


def install_apk(module, device, apk, spoof, installer):
    cmd = ["adb", "-s", device, "install", "-r"]
    if spoof:
        cmd.extend(["-i", installer])
    cmd.append(apk)
    return run_cmd(module, cmd)


def uninstall_pkg(module, device, pkg):
    return run_cmd(module, ["adb", "-s", device, "uninstall", "--user", "0", pkg])


def ensure_present(module, device, spec, outputs):
    pkg = spec["id"]
    if package_installed(module, device, pkg):
        return False

    if module.check_mode:
        return True

    apk = spec.get("apk_path")
    if apk:
        apk = os.path.expanduser(apk)
        if not os.path.isfile(apk):
            module.fail_json(msg="apk_path not found for %s: %s" % (pkg, apk))
    else:
        backend = module.params["download_backend"]
        dest = os.path.expanduser(module.params["download_dir"])
        if backend == "none":
            module.fail_json(
                msg="app %s missing and download_backend=none (set apk_path)" % pkg
            )
        if backend == "apkeep":
            src = module.params["apkeep_source"]
            if src == "google-play" and not (
                os.environ.get("GPLAY_AAS_TOKEN")
                or os.environ.get("GPLAY_AUTH_TOKEN")
            ):
                module.fail_json(
                    msg="google-play download needs GPLAY_AAS_TOKEN or GPLAY_AUTH_TOKEN "
                    "(and usually GPLAY_EMAIL) — see play/README.md",
                )
            rc, out = download_apkeep(module, pkg, dest)
            outputs.append(out)
            if rc != 0:
                module.fail_json(msg="apkeep download failed for %s" % pkg, rc=rc, output=out)
        elif backend == "gplaycli":
            rc, out = download_gplaycli(module, pkg, dest)
            outputs.append(out)
            if rc != 0:
                module.fail_json(
                    msg="gplaycli download failed for %s (configure gplaycli.conf?)"
                    % pkg,
                    rc=rc,
                    output=out,
                )
        else:
            module.fail_json(msg="unknown download_backend: %s" % backend)

        apk = find_apk(dest, pkg)
        if not apk:
            module.fail_json(
                msg="no APK found for %s under %s after download" % (pkg, dest),
                output=outputs,
            )

    rc, out = install_apk(
        module,
        device,
        apk,
        module.params["spoof_play_installer"],
        module.params["installer_package"],
    )
    outputs.append(out)
    if rc != 0:
        module.fail_json(msg="adb install failed for %s" % pkg, rc=rc, output=out)
    return True


def ensure_absent(module, device, pkg, outputs):
    if not package_installed(module, device, pkg):
        return False
    if module.check_mode:
        return True
    rc, out = uninstall_pkg(module, device, pkg)
    outputs.append(out)
    if rc != 0:
        module.fail_json(msg="adb uninstall failed for %s" % pkg, rc=rc, output=out)
    return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            apps=dict(type="list", elements="dict", required=True),
            device=dict(type="str", default="localhost:5555"),
            state=dict(type="str", default="present", choices=["present", "absent"]),
            download_backend=dict(
                type="str",
                default="apkeep",
                choices=["apkeep", "gplaycli", "none"],
            ),
            apkeep_source=dict(type="str", default="apk-pure"),
            apkeep_bin=dict(type="str", default="apkeep"),
            apkeep_accept_tos=dict(type="bool", default=False),
            gplaycli_bin=dict(type="str", default="play/mac/gplaycli.sh"),
            gplaycli_config=dict(type="str", default=""),
            download_dir=dict(type="str", default="/tmp/stayturgid-play-apps"),
            spoof_play_installer=dict(type="bool", default=True),
            installer_package=dict(type="str", default="com.android.vending"),
        ),
        supports_check_mode=True,
    )

    apps = module.params["apps"]
    device = resolve_device(module.params["device"], module)
    outputs = []
    changed = False
    installed, removed = [], []

    rc, out = run_cmd(module, ["adb", "connect", device])
    outputs.append("adb connect %s: rc=%s %s" % (device, rc, out))
    rc, out = run_cmd(module, ["adb", "-s", device, "shell", "true"])
    if rc != 0:
        module.fail_json(msg="adb device %s not reachable" % device, adb_output=out)

    state = module.params["state"]
    for spec in apps:
        pkg = spec.get("id")
        if not pkg:
            module.fail_json(msg="each app requires 'id' (package name)")
        if state == "absent":
            if ensure_absent(module, device, pkg, outputs):
                changed = True
                removed.append(pkg)
        else:
            if ensure_present(module, device, spec, outputs):
                changed = True
                installed.append(pkg)

    module.exit_json(
        changed=changed,
        installed=installed,
        removed=removed,
        device_resolved=device,
        output=outputs,
    )


if __name__ == "__main__":
    main()
