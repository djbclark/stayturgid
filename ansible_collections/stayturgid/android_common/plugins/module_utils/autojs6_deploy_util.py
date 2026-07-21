# -*- coding: utf-8 -*-
"""AutoJs6 project deploy over adb (shared by module + control/bin/deploy.py)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import shutil
import tempfile

from ansible_collections.stayturgid.android_common.plugins.module_utils import adb_shell

DEFAULT_TARGET = "/sdcard/stayturgid/autojs6"
DEFAULT_DEVICE_JSON_DEST = "/sdcard/stayturgid/state/device.json"

# Stale project copies outside the ASCII canonical target confuse operators and
# AutoJs6 (Chinese-locale default sample dir is 脚本/Scripts). Never deploy there;
# remove leftover trees on each deploy so main.js is only under DEFAULT_TARGET.
STALE_PROJECT_MIRRORS = (
    "/sdcard/Scripts/stayturgid",
    "/storage/emulated/0/Scripts/stayturgid",
    # AutoJs6 Chinese UI "Scripts" folder name (U+811A U+672C)
    "/sdcard/\u811a\u672c/stayturgid",
    "/storage/emulated/0/\u811a\u672c/stayturgid",
)

VERIFY_SHELL = (
    "test -f '{target}/lib/shizuku_shell.js' "
    "&& test -f '{target}/lib/comonitor.js' "
    "&& test -f '{target}/scripts/shizuku-probe.js' "
    "&& test ! -d '{target}/lib/lib'"
)


def project_src_dir(repo_root):
    return os.path.join(os.path.expanduser(repo_root), "device", "autojs6")


def verify_shell_cmd(target):
    return VERIFY_SHELL.format(target=target)


def verify_deploy(run_command, device, target):
    rc, _out, err = adb_shell.adb_shell(run_command, device, verify_shell_cmd(target))
    if rc == 0:
        return True, ""
    return False, (
        "deploy incomplete — missing lib/shizuku_shell.js, lib/comonitor.js, "
        "or scripts/shizuku-probe.js (or nested lib/lib) on device"
        + (": %s" % err.strip() if err and err.strip() else "")
    )


def adb_push(run_command, device, local, remote):
    return run_command(["adb", "-s", device, "push", str(local), remote])


def _staged_dir_without_ts_sources(local_dir):
    """Copy local_dir into a scratch dir, excluding *.ts.

    Rhino/AutoJs6 loads the compiled .js siblings only (every require() in the
    generated output uses an explicit .js extension); the committed .ts source
    is for git review/debugging, not device use. Pushing the raw source dir
    with `adb push` would ship .ts alongside .js to every device with no
    on-device purpose. Returns (scratch_root, staged_dir) — caller must clean
    up scratch_root.
    """
    scratch_root = tempfile.mkdtemp(prefix="stayturgid-deploy-")
    staged_dir = os.path.join(scratch_root, os.path.basename(local_dir))
    shutil.copytree(local_dir, staged_dir, ignore=shutil.ignore_patterns("*.ts"))
    return scratch_root, staged_dir


def deploy_project(run_command, device, repo_root, target=DEFAULT_TARGET, check_mode=False):
    """Wipe lib/scripts, push project tree, verify. Returns (ok, message, changed)."""
    src = project_src_dir(repo_root)
    for name in ("project.json", "main.js", "lib", "scripts", "fleet_profile.json"):
        path = os.path.join(src, name)
        if not os.path.exists(path):
            return False, "missing source path: %s" % path, False

    if check_mode:
        return True, "", True

    rc, _out, err = adb_shell.adb_shell(
        run_command,
        device,
        "rm -rf '%s/lib' '%s/scripts'" % (target, target),
    )
    if rc != 0:
        return False, "failed to wipe remote lib/scripts: %s" % (err.strip() or rc), False

    for local_name in ("project.json", "main.js", "fleet_profile.json"):
        local = os.path.join(src, local_name)
        rc, _out, err = adb_push(run_command, device, local, "%s/%s" % (target, local_name))
        if rc != 0:
            return False, "adb push %s failed: %s" % (local_name, err.strip() or rc), False

    for dir_name in ("lib", "scripts"):
        local = os.path.join(src, dir_name)
        scratch_root, staged = _staged_dir_without_ts_sources(local)
        try:
            rc, _out, err = adb_push(run_command, device, staged, "%s/%s" % (target, dir_name))
        finally:
            shutil.rmtree(scratch_root, ignore_errors=True)
        if rc != 0:
            return False, "adb push %s/ failed: %s" % (dir_name, err.strip() or rc), False

    ok, msg = verify_deploy(run_command, device, target)
    if not ok:
        return False, msg, True

    # Retire non-canonical / non-ASCII project mirrors (see STALE_PROJECT_MIRRORS).
    for mirror in STALE_PROJECT_MIRRORS:
        if os.path.normpath(mirror) == os.path.normpath(target):
            continue
        adb_shell.adb_shell(run_command, device, "rm -rf '%s'" % mirror)

    return True, "", True


def push_device_json(
    run_command,
    device,
    local_path,
    dest=DEFAULT_DEVICE_JSON_DEST,
    check_mode=False,
):
    """Push rendered device.json to shared state on device."""
    local_path = os.path.expanduser(local_path)
    if not os.path.isfile(local_path):
        return False, "device_json not found: %s" % local_path, False

    if check_mode:
        return True, "", True

    state_dir = os.path.dirname(dest)
    rc, _out, err = adb_shell.adb_shell(run_command, device, "mkdir -p '%s'" % state_dir)
    if rc != 0:
        return False, "mkdir %s failed: %s" % (state_dir, err.strip() or rc), False

    rc, _out, err = adb_push(run_command, device, local_path, dest)
    if rc != 0:
        return False, "adb push device.json failed: %s" % (err.strip() or rc), False
    return True, "", True
