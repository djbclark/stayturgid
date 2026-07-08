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
  apkeep_options:
    description: C(apkeep -o) options (e.g. C(arch=arm64-v8a) for APKPure).
    type: str
    default: arch=arm64-v8a
  apkeep_bin:
    type: str
    default: apkeep
  gplaycli_bin:
    type: str
    default: play/mac/gplaycli.py
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
  stayturgid.play.play_apps:
    device: p7a
    apps:
      - id: com.google.android.apps.authenticator2
    download_backend: apkeep
    apkeep_source: apk-pure

- name: Install from a local APK
  stayturgid.play.play_apps:
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
import zipfile

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_resolve import (
    resolve_adb,
)


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


def extract_xapk(xapk_path, dest_dir):
    """APKPure often ships .xapk (zip); pull base APK for adb install."""
    with zipfile.ZipFile(xapk_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".apk")]
        if not names:
            return None
        preferred = [n for n in names if "base" in os.path.basename(n).lower()]
        chosen = preferred[0] if preferred else names[0]
        out = os.path.join(dest_dir, os.path.basename(chosen))
        with zf.open(chosen) as src, open(out, "wb") as dst:
            dst.write(src.read())
        return out


def resolve_installable_apk(download_dir, pkg):
    apk = find_apk(download_dir, pkg)
    if apk:
        return apk
    xapk_patterns = [
        os.path.join(download_dir, "%s*.xapk" % pkg),
        os.path.join(download_dir, "**", "%s*.xapk" % pkg),
        os.path.join(download_dir, "*.xapk"),
        os.path.join(download_dir, "**", "*.xapk"),
    ]
    xapks = []
    for pat in xapk_patterns:
        xapks.extend(glob.glob(pat, recursive="**" in pat))
    for xapk in sorted(set(xapks), key=os.path.getmtime, reverse=True):
        extracted = extract_xapk(xapk, download_dir)
        if extracted:
            return extracted
    return find_apk(download_dir, pkg)


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
    ] + apkeep_auth_args(module)
    opts = (module.params.get("apkeep_options") or "").strip()
    if opts:
        cmd.extend(["-o", opts])
    cmd.append(dest)
    return run_cmd(module, cmd)


def download_gplaycli(module, pkg, dest):
    os.makedirs(dest, exist_ok=True)
    gpath = module.params["gplaycli_bin"]
    if not os.path.isabs(gpath):
        root = module.params.get("repo_root") or os.environ.get("STAYTURGID_REPO_ROOT", "")
        if root:
            gpath = os.path.join(root, gpath)
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

        apk = resolve_installable_apk(dest, pkg)
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
            apkeep_options=dict(type="str", default="arch=arm64-v8a"),
            apkeep_bin=dict(type="str", default="apkeep"),
            apkeep_accept_tos=dict(type="bool", default=False),
            gplaycli_bin=dict(type="str", default="play/mac/gplaycli.py"),
            gplaycli_config=dict(type="str", default=""),
            repo_root=dict(
                type="str",
                default="",
                description="Repo root when gplaycli_bin is a relative path.",
            ),
            download_dir=dict(type="str", default="/tmp/stayturgid-play-apps"),
            spoof_play_installer=dict(type="bool", default=True),
            installer_package=dict(type="str", default="com.android.vending"),
        ),
        supports_check_mode=True,
    )

    apps = module.params["apps"]
    device = resolve_adb(module.params["device"], module.run_command)
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
