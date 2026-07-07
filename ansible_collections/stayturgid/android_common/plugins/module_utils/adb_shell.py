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
