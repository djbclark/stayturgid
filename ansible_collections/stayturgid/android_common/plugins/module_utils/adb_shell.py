# -*- coding: utf-8 -*-
"""Thin adb shell helpers for stayturgid.android_common modules."""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


def normalize_adb_output(text):
    return (text or "").replace("\r", "").strip()


def adb_connect(run_command, device):
    """Best-effort adb connect; ignored for USB serials."""
    if ":" not in device:
        return 0, "", ""
    return run_command(["adb", "connect", device])


def adb_shell(run_command, device, shell_cmd):
    return run_command(["adb", "-s", device, "shell", shell_cmd])


def package_installed(run_command, device, package):
    rc, out, _err = adb_shell(
        run_command,
        device,
        "pm list packages --user 0 %s" % package,
    )
    if rc != 0:
        return False
    needle = "package:%s" % package
    return needle in normalize_adb_output(out)


def pm_grant(run_command, device, package, permission):
    rc, out, err = adb_shell(
        run_command,
        device,
        "pm grant %s %s" % (package, permission),
    )
    combined = normalize_adb_output(out + err).lower()
    if rc == 0:
        return True, "granted"
    if "already" in combined:
        return False, "already"
    return False, combined or "failed"


def parse_appops_mode(output):
    text = normalize_adb_output(output).lower()
    if "allow" in text:
        return "allow"
    if "ignore" in text:
        return "ignore"
    if "deny" in text:
        return "deny"
    if "default" in text:
        return "default"
    return text


def appops_get(run_command, device, package, op):
    return adb_shell(
        run_command,
        device,
        "cmd appops get %s %s" % (package, op),
    )


def appops_set(run_command, device, package, op, mode):
    return adb_shell(
        run_command,
        device,
        "cmd appops set %s %s %s" % (package, op, mode),
    )


def deviceidle_whitelist(run_command, device):
    rc, out, _err = adb_shell(run_command, device, "dumpsys deviceidle whitelist")
    if rc != 0:
        return []
    return [line.strip() for line in normalize_adb_output(out).splitlines() if line.strip()]


def deviceidle_whitelisted(run_command, device, package):
    text = " ".join(deviceidle_whitelist(run_command, device))
    return package in text


def deviceidle_whitelist_add(run_command, device, package):
    return adb_shell(
        run_command,
        device,
        "dumpsys deviceidle whitelist +%s" % package,
    )


def standby_bucket_get(run_command, device, package):
    return adb_shell(run_command, device, "am get-standby-bucket %s" % package)


def standby_bucket_set(run_command, device, package, bucket):
    return adb_shell(
        run_command,
        device,
        "am set-standby-bucket %s %s" % (package, bucket),
    )


def dumpsys_package(run_command, device, package):
    return adb_shell(run_command, device, "dumpsys package %s" % package)


def parse_ungranted_runtime_permissions(dumpsys_output):
    """Return permission names still granted=false in dumpsys package output."""
    import re

    text = normalize_adb_output(dumpsys_output)
    perms = []
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        name = re.match(r"^((?:android|com)\.[\w.]+):$", stripped)
        if name:
            current = name.group(1)
            continue
        if current and stripped.startswith("granted="):
            if stripped == "granted=false":
                perms.append(current)
            current = None
    return sorted(set(perms))


def ungranted_runtime_permissions(run_command, device, package):
    rc, out, _err = dumpsys_package(run_command, device, package)
    if rc != 0:
        return []
    return parse_ungranted_runtime_permissions(out)


def settings_get(run_command, device, namespace, key):
    return adb_shell(
        run_command,
        device,
        "settings get %s %s" % (namespace, key),
    )


def settings_put(run_command, device, namespace, key, value):
    return adb_shell(
        run_command,
        device,
        "settings put %s %s %s" % (namespace, key, value),
    )
