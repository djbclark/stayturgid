# -*- coding: utf-8 -*-
"""Thin adb shell helpers for stayturgid.android_common modules."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type


try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_timeout import (
        DEFAULT_FAST_TIMEOUT,
        run_command_with_timeout,
    )
except ImportError:
    import os
    import sys

    _mod_dir = os.path.dirname(os.path.abspath(__file__))
    if _mod_dir not in sys.path:
        sys.path.insert(0, _mod_dir)
    # Same names as the collection import above (non-collection load path); mypy
    # would flag the rebinding as no-redef.
    from adb_timeout import (  # type: ignore[no-redef]
        DEFAULT_FAST_TIMEOUT,
        run_command_with_timeout,
    )


def normalize_adb_output(text):
    return (text or "").replace("\r", "").strip()


def adb_connect(run_command, device, timeout=DEFAULT_FAST_TIMEOUT):
    """Best-effort adb connect; ignored for USB serials."""
    if ":" not in device:
        return 0, "", ""
    return run_command_with_timeout(run_command, ["adb", "connect", device], timeout=timeout)


def adb_shell(run_command, device, shell_cmd, timeout=DEFAULT_FAST_TIMEOUT):
    return run_command_with_timeout(run_command, ["adb", "-s", device, "shell", shell_cmd], timeout=timeout)


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


MONKEY_LAUNCH_KEEPING_ROTATION = (
    "r=$(settings get system accelerometer_rotation 2>/dev/null); "
    "monkey -p %s -c android.intent.category.LAUNCHER 1 2>/dev/null; rc=$?; "
    'case "$r" in 0|1) settings put system accelerometer_rotation "$r" ;; esac; exit $rc'
)


def monkey_launch(run_command, device, package):
    """Force-start an app via monkey so its permission controller initializes.

    Android 13+ (SDK 33+) requires the permission controller to have run
    at least once before ``pm grant`` takes effect for POST_NOTIFICATIONS.
    Without this, ``pm grant`` returns 0 (success) but the permission
    stays ``granted=false`` in dumpsys.  Calling monkey with the LAUNCHER
    category is the lightest way to un-stop the package.

    monkey releases the rotation lock when it exits (thawRotation), which
    turned auto-rotate back on at every deploy; the setting is read first and
    put back afterwards.
    """
    return adb_shell(run_command, device, MONKEY_LAUNCH_KEEPING_ROTATION % package)


def pm_grant(run_command, device, package, permission):
    if permission_granted(run_command, device, package, permission):
        return False, "already"
    if not permission_requested(run_command, device, package, permission):
        return False, "not_requested"
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


def parse_permission_granted(dumpsys_output, permission):
    """Return whether user 0 has ``permission`` in package dump output."""
    current = False
    needle = permission + ":"
    for line in normalize_adb_output(dumpsys_output).splitlines():
        stripped = line.strip()
        if stripped.startswith(needle):
            suffix = stripped[len(needle) :]
            if "granted=true" in suffix:
                return True
            if "granted=false" in suffix:
                return False
            current = True
            continue
        if current and stripped.startswith("granted="):
            return stripped == "granted=true"
        if stripped == "--":
            break
    return False


def permission_granted(run_command, device, package, permission):
    rc, out, _err = dumpsys_package(run_command, device, package)
    return rc == 0 and parse_permission_granted(out, permission)


def permission_requested(run_command, device, package, permission):
    rc, out, _err = dumpsys_package(run_command, device, package)
    if rc != 0:
        return False
    needle = permission + ":"
    return any(
        line.strip() == permission or line.strip().startswith(needle) for line in normalize_adb_output(out).splitlines()
    )


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


def deviceidle_whitelist_remove(run_command, device, package):
    return adb_shell(
        run_command,
        device,
        "dumpsys deviceidle whitelist -%s" % package,
    )


def standby_bucket_get(run_command, device, package):
    return adb_shell(run_command, device, "am get-standby-bucket %s" % package)


def standby_bucket_set(run_command, device, package, bucket):
    return adb_shell(run_command, device, "am set-standby-bucket %s %s" % (package, bucket))


def dumpsys_package(run_command, device, package):
    return adb_shell(run_command, device, "dumpsys package %s" % package)


def parse_ungranted_runtime_permissions(dumpsys_output):
    """Return permission names still granted=false in dumpsys package output.

    Only user 0 counts (fleet apps run there; work profiles and private spaces
    follow as later ``User N:`` blocks or ``--``-separated sections). Two
    layouts exist: the older one puts ``name:`` and ``granted=...`` on separate
    lines; current Android prints ``name: granted=false, flags=[...]`` on one
    line under ``runtime permissions:``. Reading only the older layout made
    grant_all_runtime a silent no-op on every current device (2026-09-30).
    """
    import re

    text = normalize_adb_output(dumpsys_output)
    perms = []
    current = None
    in_user0 = True  # first section is user 0
    in_runtime = False
    for line in text.splitlines():
        stripped = line.strip()
        # Section separator between user profiles
        if stripped == "--":
            in_user0 = False
            continue
        user = re.match(r"^User (\d+):", stripped)
        if user:
            in_user0 = user.group(1) == "0"
            in_runtime = False
            continue
        if not in_user0:
            continue
        if stripped.endswith("permissions:"):
            in_runtime = stripped == "runtime permissions:"
            continue
        inline = re.match(r"^(\w+(?:\.\w+)+): granted=(true|false)\b", stripped)
        if inline:
            if in_runtime and inline.group(2) == "false":
                perms.append(inline.group(1))
            continue
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


TAILNET_PREFIX_FIRST_OCTET = 100
TAILNET_SECOND_OCTET_RANGE = range(64, 128)  # 100.64.0.0/10, Tailscale's CGNAT block


def is_tailnet_ipv4(addr):
    """True when ``addr`` is a dotted IPv4 inside 100.64.0.0/10."""
    parts = (addr or "").strip().split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False
    if any(o < 0 or o > 255 for o in octets):
        return False
    return octets[0] == TAILNET_PREFIX_FIRST_OCTET and octets[1] in TAILNET_SECOND_OCTET_RANGE


def parse_tailnet_ipv4(ip_addr_output):
    """Tailnet IPv4 held by a tunN/tailscaleN interface in ``ip -4 -o addr show`` output.

    Android gives Tailscale's VpnService whatever TUN index is free, so any tunN
    (or tailscale0) counts. Returns None when no such interface holds an address
    in 100.64.0.0/10, which is the state of an installed but never-logged-in or
    disconnected client.
    """
    for line in normalize_adb_output(ip_addr_output).splitlines():
        fields = line.split()
        if "inet" not in fields:
            continue
        idx = fields.index("inet")
        if idx < 1 or idx + 1 >= len(fields):
            continue
        iface = fields[idx - 1]
        if not (iface.startswith("tun") or iface.startswith("tailscale")):
            continue
        addr = fields[idx + 1].split("/", 1)[0]
        if is_tailnet_ipv4(addr):
            return addr
    return None


def device_tailnet_ipv4(run_command, device):
    rc, out, _err = adb_shell(run_command, device, "ip -4 -o addr show 2>/dev/null")
    if rc != 0:
        return None
    return parse_tailnet_ipv4(out)
