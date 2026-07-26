#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_apk
short_description: Install an APK on a device via adb with failure parsing
description:
  - Installs an APK from a local path, a URL, or a GitHub release
    (C(gh release download)) with C(adb install -r).
  - Parses C(INSTALL_FAILED_*) / C(Failure) output — adb can exit 0 while the
    install actually failed.
  - Idempotent by package presence; set C(force=true) to reinstall, or
    C(version_name) to upgrade only when the installed version differs.
options:
  device:
    description: ADB device serial or C(host:5555) target.
    type: str
    required: true
  package:
    description: Package id used for the idempotence check.
    type: str
    required: true
  apk_path:
    description: Local APK file to install.
    type: path
  url:
    description: Download URL for the APK (fetched to a temp file).
    type: str
  gh_repo:
    description: GitHub C(owner/repo) to download a release asset from (needs C(gh) CLI).
    type: str
  gh_pattern:
    description: Asset glob for C(gh release download --pattern).
    type: str
  gh_tag:
    description: Release tag (default latest).
    type: str
  version_name:
    description: Expected versionName; install only when the device differs.
    type: str
  checksum:
    description:
      - Expected SHA-256 digest of the APK before any optional resigning.
      - Accepts either the bare hexadecimal digest or C(sha256:<digest>).
    type: str
  force:
    description: Install even when the package is already present.
    type: bool
    default: false
  clean:
    description:
      - Uninstall the package before installing (only when an install is
        actually happening; the already-installed idempotency check still
        short-circuits first).
      - Forces the installer to re-extract native libs. Needed on Fire OS 8,
        which does not re-extract libs on an in-place C(adb install -r)
        upgrade, leaving native-lib-dependent components (e.g. shizuku_server
        loading librish.so) broken until a fresh install.
    type: bool
    default: false
  installer:
    description: Installer package to spoof (C(adb install -i), e.g. com.android.vending).
    type: str
  extra_args:
    description: Extra C(adb install) arguments.
    type: list
    elements: str
    default: []
  connect:
    description: Run C(adb connect) before other operations (for wireless targets).
    type: bool
    default: true
  resign:
    description:
      - Resign the downloaded APK with a debug keystore before installing.
      - Required for unsigned fork builds (operator/Obtainium, operator/Shizuku, etc.).
    type: bool
    default: false
  apksigner_bin:
    description: Path to C(apksigner) (Android SDK build-tools). Ignored unless I(resign=true).
    type: path
  keystore:
    description: Debug keystore path. Ignored unless I(resign=true).
    type: path
  keystore_pass:
    description: Keystore password. Ignored unless I(resign=true).
    type: str
    default: android
  key_alias:
    description: Key alias in the keystore. Ignored unless I(resign=true).
    type: str
    default: androiddebugkey
  install_timeout:
    description: >-
      Seconds before C(adb install) is killed. Without this, a stuck install
      (e.g. an on-device confirmation dialog nobody is present to tap) hangs
      forever — this ansible-core's C(run_command) has no timeout of its own.
    type: int
    default: 180
"""

EXAMPLES = r"""
- name: Install a local APK
  stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: com.example.app
    apk_path: /tmp/app.apk
  delegate_to: localhost

- name: Install latest Shizuku from a GitHub release
  stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: moe.shizuku.privileged.api
    gh_repo: thedjchi/Shizuku
    gh_pattern: "*.apk"
  delegate_to: localhost

- name: Install fork build with resign
  stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: moe.shizuku.privileged.api
    gh_repo: operator/Shizuku
    gh_pattern: "*universal*"
    resign: true
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when an install ran.
  type: bool
reason:
  description: Install outcome or skip reason.
  type: str
"""

import hashlib
import os
import tempfile

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
    package_installed,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.apk_install import (
    parse_install_result,
)


def installed_version(run_command, device, package):
    rc, out, _err = adb_shell(run_command, device, "dumpsys package %s | grep versionName" % package)
    if rc != 0:
        return None
    text = normalize_adb_output(out)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            return line.split("=", 1)[1]
    return None


def download_url(module, url):
    resp, info = fetch_url(module, url)
    if info.get("status") != 200 or resp is None:
        module.fail_json(msg="download failed (%s): %s" % (info.get("status"), url))
    tmp = tempfile.NamedTemporaryFile("wb", dir=module.tmpdir, suffix=".apk", delete=False)
    tmp.write(resp.read())
    tmp.close()
    return tmp.name


def download_gh_release(module, repo, pattern, tag):
    gh = module.get_bin_path("gh", required=True)
    destdir = tempfile.mkdtemp(dir=module.tmpdir)
    cmd = [gh, "release", "download"]
    if tag:
        cmd.append(tag)
    cmd += ["--repo", repo, "--pattern", pattern or "*.apk", "--dir", destdir]
    rc, _out, err = module.run_command(cmd)
    if rc != 0:
        module.fail_json(msg="gh release download failed: %s" % err.strip())
    apks = sorted(f for f in os.listdir(destdir) if f.lower().endswith(".apk"))
    if not apks:
        module.fail_json(msg="no .apk asset matched %r in %s" % (pattern, repo))
    return os.path.join(destdir, apks[0])


def verify_sha256(module, apk_path, expected):
    if not expected:
        return
    wanted = expected.removeprefix("sha256:").lower()
    digest = hashlib.sha256()
    with open(apk_path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != wanted:
        module.fail_json(msg="APK checksum mismatch: expected sha256:%s, got sha256:%s" % (wanted, actual))


def resign_apk(module, apk_path):
    apksigner = module.params.get("apksigner_bin")
    if not apksigner:
        home = os.path.expanduser("~")
        apksigner = os.path.join(home, "Library", "Android", "sdk", "build-tools", "36.0.0", "apksigner")
    if not os.path.isfile(apksigner):
        module.fail_json(
            msg="apksigner not found at %s; set apksigner_bin or install Android SDK build-tools" % apksigner
        )

    keystore = module.params.get("keystore")
    if not keystore:
        home = os.path.expanduser("~")
        keystore = os.path.join(home, ".android", "debug.keystore")
    if not os.path.isfile(keystore):
        module.fail_json(msg="debug keystore not found at %s" % keystore)

    keystore_pass = module.params.get("keystore_pass", "android")
    key_alias = module.params.get("key_alias", "androiddebugkey")

    cmd = [
        apksigner,
        "sign",
        "--ks",
        keystore,
        "--ks-pass",
        "pass:" + keystore_pass,
        "--ks-key-alias",
        key_alias,
        apk_path,
    ]
    rc, _out, err = module.run_command(cmd)
    if rc != 0:
        module.fail_json(msg="apksigner sign failed: %s" % err.strip())


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            package=dict(type="str", required=True),
            apk_path=dict(type="path"),
            url=dict(type="str"),
            gh_repo=dict(type="str"),
            gh_pattern=dict(type="str"),
            gh_tag=dict(type="str"),
            version_name=dict(type="str"),
            checksum=dict(type="str"),
            force=dict(type="bool", default=False),
            clean=dict(type="bool", default=False),
            installer=dict(type="str"),
            extra_args=dict(type="list", elements="str", default=[]),
            install_user=dict(type="str", default="0"),
            work_profile=dict(type="bool", default=False),
            work_profile_user=dict(type="str", default="10"),
            connect=dict(type="bool", default=True),
            resign=dict(type="bool", default=False),
            apksigner_bin=dict(type="path"),
            keystore=dict(type="path"),
            keystore_pass=dict(type="str", default="android", no_log=True),
            key_alias=dict(type="str", default="androiddebugkey"),
            install_timeout=dict(type="int", default=180),
        ),
        required_one_of=[["apk_path", "url", "gh_repo"]],
        mutually_exclusive=[["apk_path", "url", "gh_repo"]],
        supports_check_mode=True,
    )

    device = module.params["device"]
    package = module.params["package"]

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    present = package_installed(module.run_command, device, package)
    if present and not module.params["force"]:
        if module.params["version_name"]:
            current = installed_version(module.run_command, device, package)
            if current == module.params["version_name"]:
                module.exit_json(changed=False, reason="version %s already installed" % current)
        else:
            module.exit_json(changed=False, reason="already installed")

    if module.check_mode:
        module.exit_json(changed=True, reason="would install")

    if module.params["apk_path"]:
        apk = module.params["apk_path"]
        if not os.path.isfile(apk):
            module.fail_json(msg="apk_path not found: %s" % apk)
    elif module.params["url"]:
        apk = download_url(module, module.params["url"])
    else:
        apk = download_gh_release(
            module,
            module.params["gh_repo"],
            module.params["gh_pattern"],
            module.params["gh_tag"],
        )

    verify_sha256(module, apk, module.params["checksum"])

    if module.params["resign"]:
        resign_apk(module, apk)

    user = module.params.get("install_user", "0")
    # This ansible-core's AnsibleModule.run_command() has no timeout param at
    # all, so `adb install` can hang indefinitely — confirmed live: a stuck
    # install (likely an on-device confirmation dialog nobody was there to
    # tap) blocked a deploy for 90+ minutes with no error. Wrap with the
    # coreutils timeout(1) binary (same pattern used on-device in
    # stayturgid_battery_alarm.py) so a stuck install fails loudly instead of
    # hanging the whole fleet deploy.
    timeout_bin = module.get_bin_path("timeout", required=True)

    # Clean reinstall: uninstall before install so the installer re-extracts
    # native libs. Fire OS 8 does not re-extract libs on an in-place upgrade
    # (`adb install -r`), which leaves e.g. shizuku_server unable to load
    # librish.so from the extracted lib dir; a fresh install always extracts.
    # Only runs when we are actually installing (the already-installed
    # idempotency check above has already returned), so steady-state deploys
    # with an unchanged version never uninstall.
    if module.params["clean"] and present:
        module.run_command(
            [timeout_bin, str(module.params["install_timeout"]), "adb", "-s", device, "uninstall", package]
        )

    cmd = [timeout_bin, str(module.params["install_timeout"]), "adb", "-s", device, "install", "-r", "--user", user]
    if module.params["installer"]:
        cmd += ["-i", module.params["installer"]]
    cmd += module.params["extra_args"]
    cmd.append(apk)

    rc, out, err = module.run_command(cmd)
    if rc == 124:
        module.fail_json(
            msg="adb install timed out after %ss (device may be showing an install confirmation dialog)"
            % module.params["install_timeout"]
        )
    ok, reason = parse_install_result(out + "\n" + err)
    if rc != 0 or not ok:
        module.fail_json(msg="adb install failed: %s" % reason)

    if module.params["work_profile"]:
        wp_cmd = [
            timeout_bin,
            str(module.params["install_timeout"]),
            "adb",
            "-s",
            device,
            "install",
            "-r",
            "--user",
            module.params["work_profile_user"],
            apk,
        ]
        rc2, _out2, _err2 = module.run_command(wp_cmd)
        if rc2 == 0:
            reason += " (also installed for user %s)" % module.params["work_profile_user"]
        else:
            module.warn("work profile install failed (rc=%d) — app may not be available in work profile" % rc2)

    module.exit_json(changed=True, reason=reason)


if __name__ == "__main__":
    main()
