# -*- coding: utf-8 -*-
"""Shared fleet app privilege application (Ansible module + Mac harden script)."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type

try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils import adb_shell
except ImportError:
    import adb_shell  # noqa: F401 — Mac CLI adds module_utils to sys.path

BATTERY_APPOPS = ("RUN_ANY_IN_BACKGROUND", "RUN_IN_BACKGROUND")
UNUSED_APPOPS = (("AUTO_REVOKE_PERMISSIONS_IF_UNUSED", "ignore"),)
STANDBY_BUCKET_ACTIVE = "active"


def ensure_appop(run_command, device, package, op, mode, check_mode=False):
    rc, out, _err = adb_shell.appops_get(run_command, device, package, op)
    current = adb_shell.parse_appops_mode(out if rc == 0 else "")
    if current == mode:
        return False, "already"
    if check_mode:
        return True, "would_set"
    rc, _out, err = adb_shell.appops_set(run_command, device, package, op, mode)
    if rc == 0:
        return True, "set"
    return False, adb_shell.normalize_adb_output(err) or "failed"


def ensure_permission(run_command, device, package, permission, check_mode=False):
    if check_mode:
        return True, "would_grant"
    changed, status = adb_shell.pm_grant(run_command, device, package, permission)
    return changed, status


def ensure_battery_unrestricted(run_command, device, package, check_mode=False):
    results = []
    changed = False
    if not adb_shell.deviceidle_whitelisted(run_command, device, package):
        if check_mode:
            results.append(dict(kind="deviceidle", status="would_whitelist"))
            changed = True
        else:
            rc, _out, err = adb_shell.deviceidle_whitelist_add(run_command, device, package)
            ok = rc == 0
            results.append(
                dict(
                    kind="deviceidle",
                    status="whitelisted" if ok else adb_shell.normalize_adb_output(err) or "failed",
                )
            )
            changed = changed or ok
    else:
        results.append(dict(kind="deviceidle", status="already"))

    for op in BATTERY_APPOPS:
        item_changed, status = ensure_appop(
            run_command, device, package, op, "allow", check_mode
        )
        changed = changed or item_changed
        results.append(dict(kind="appops", op=op, status=status))
    return changed, results


def ensure_disable_unused(run_command, device, package, check_mode=False):
    results = []
    changed = False
    for op, mode in UNUSED_APPOPS:
        item_changed, status = ensure_appop(
            run_command, device, package, op, mode, check_mode
        )
        changed = changed or item_changed
        results.append(dict(kind="appops", op=op, status=status))

    rc, out, _err = adb_shell.standby_bucket_get(run_command, device, package)
    current = adb_shell.normalize_adb_output(out).lower()
    if current == STANDBY_BUCKET_ACTIVE:
        results.append(dict(kind="standby_bucket", status="already"))
    elif check_mode:
        results.append(dict(kind="standby_bucket", status="would_set"))
        changed = True
    else:
        rc, _out, err = adb_shell.standby_bucket_set(
            run_command, device, package, STANDBY_BUCKET_ACTIVE
        )
        ok = rc == 0
        results.append(
            dict(
                kind="standby_bucket",
                status="active" if ok else adb_shell.normalize_adb_output(err) or "failed",
            )
        )
        changed = changed or ok
    return changed, results


def apply_profile(run_command, device, profile, check_mode=False, skip_missing=True):
    package = profile["package"]
    if skip_missing and not adb_shell.package_installed(run_command, device, package):
        return False, [dict(package=package, status="skipped")]

    results = []
    changed = False

    if profile.get("battery_unrestricted"):
        item_changed, items = ensure_battery_unrestricted(
            run_command, device, package, check_mode
        )
        changed = changed or item_changed
        results.extend(items)

    if profile.get("disable_unused_restrictions"):
        item_changed, items = ensure_disable_unused(
            run_command, device, package, check_mode
        )
        changed = changed or item_changed
        results.extend(items)

    for item in profile.get("appops") or []:
        item_changed, status = ensure_appop(
            run_command,
            device,
            package,
            item["op"],
            item.get("mode", "allow"),
            check_mode,
        )
        changed = changed or item_changed
        results.append(dict(kind="appops", op=item["op"], status=status))

    for permission in profile.get("permissions") or []:
        item_changed, status = ensure_permission(
            run_command, device, package, permission, check_mode
        )
        changed = changed or item_changed
        results.append(dict(kind="permission", permission=permission, status=status))

    if profile.get("grant_all_runtime"):
        perms = (
            ["would_scan"]
            if check_mode
            else adb_shell.ungranted_runtime_permissions(run_command, device, package)
        )
        for permission in perms:
            if permission == "would_scan":
                results.append(dict(kind="permission", permission="*", status="would_grant"))
                changed = True
                continue
            item_changed, status = ensure_permission(
                run_command, device, package, permission, check_mode
            )
            changed = changed or item_changed
            results.append(dict(kind="permission", permission=permission, status=status))

    return changed, [dict(package=package, items=results)]


def apply_profiles(run_command, device, profiles, check_mode=False, skip_missing=True, connect=True):
    if connect and not check_mode:
        adb_shell.adb_connect(run_command, device)
    results = []
    changed = False
    for profile in profiles:
        item_changed, profile_results = apply_profile(
            run_command, device, profile, check_mode, skip_missing
        )
        changed = changed or item_changed
        results.extend(profile_results)
    return changed, results
