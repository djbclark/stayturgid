"""Unit tests for fleet app privilege helpers."""

import os
import sys

import pytest

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "ansible_collections", "stayturgid", "android_common")
)
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import adb_shell
import fleet_privileges as fp

SAMPLE_DUMPSYS = """
runtime permissions:
  android.permission.POST_NOTIFICATIONS:
    granted=true
  android.permission.CAMERA:
    granted=false
  com.termux.permission.RUN_COMMAND:
    granted=false
"""


def test_parse_ungranted_runtime_permissions():
    perms = adb_shell.parse_ungranted_runtime_permissions(SAMPLE_DUMPSYS)
    assert "android.permission.CAMERA" in perms
    assert "com.termux.permission.RUN_COMMAND" in perms
    assert "android.permission.POST_NOTIFICATIONS" not in perms


def test_parse_permission_granted_supports_android_dump_formats():
    assert adb_shell.parse_permission_granted(SAMPLE_DUMPSYS, "android.permission.POST_NOTIFICATIONS")
    assert not adb_shell.parse_permission_granted(SAMPLE_DUMPSYS, "android.permission.CAMERA")
    inline = "android.permission.POST_NOTIFICATIONS: granted=true, flags=[ USER_SET]"
    assert adb_shell.parse_permission_granted(inline, "android.permission.POST_NOTIFICATIONS")


def test_ensure_permission_skips_launch_when_already_granted():
    calls = []

    def run(cmd):
        joined = " ".join(cmd)
        calls.append(joined)
        if "dumpsys package" in joined:
            return (
                0,
                "android.permission.POST_NOTIFICATIONS: granted=true, flags=[]",
                "",
            )
        return (0, "", "")

    changed, status = fp.ensure_permission(
        run,
        "dev",
        "com.termux.api",
        "android.permission.POST_NOTIFICATIONS",
    )
    assert changed is False
    assert status == "already"
    assert not any("monkey" in call or "pm grant" in call for call in calls)


def test_ensure_permission_skips_undeclared_legacy_permission():
    calls = []

    def run(cmd):
        joined = " ".join(cmd)
        calls.append(joined)
        if "dumpsys package" in joined:
            return (0, "android.permission.POST_NOTIFICATIONS\n", "")
        return (0, "", "")

    changed, status = fp.ensure_permission(
        run,
        "dev",
        "org.autojs.autojs6",
        "android.permission.READ_EXTERNAL_STORAGE",
    )
    assert changed is False
    assert status == "not_requested"
    assert not any("monkey" in call or "pm grant" in call for call in calls)


def test_deviceidle_whitelisted_detects_package():
    def run(_cmd):
        return (0, "user,org.autojs.autojs6,com.termux\n", "")

    assert adb_shell.deviceidle_whitelisted(run, "dev", "com.termux") is True
    assert adb_shell.deviceidle_whitelisted(run, "dev", "com.missing") is False


def test_apply_profile_skips_missing_package():
    def run(cmd):
        joined = " ".join(cmd)
        if "pm list packages" in joined:
            return (0, "", "")
        return (0, "", "")

    changed, results = fp.apply_profile(
        run,
        "dev",
        {"package": "com.missing", "battery_unrestricted": True},
    )
    assert changed is False
    assert results[0]["status"] == "skipped"


@pytest.mark.parametrize("bucket", ["5", "10"])
def test_battery_unrestricted_accepts_numeric_active_bucket(bucket):
    calls = []

    def run(cmd):
        joined = " ".join(cmd)
        calls.append(joined)
        if "pm list packages" in joined:
            return (0, "package:com.termux\n", "")
        if joined.endswith("dumpsys deviceidle whitelist"):
            return (0, "user,com.termux,1000\n", "")
        if "cmd appops get" in joined:
            return (0, "Mode: allow\n", "")
        if "am get-standby-bucket" in joined:
            return (0, bucket + "\n", "")
        return (0, "", "")

    changed, _results = fp.apply_profile(
        run,
        "dev",
        {"package": "com.termux", "battery_unrestricted": True},
    )
    assert changed is False
    assert not any("am set-standby-bucket" in call for call in calls)


def test_battery_optimized_removes_whitelist_and_denies_background():
    calls = []

    def run(cmd):
        joined = " ".join(cmd)
        calls.append(joined)
        if "pm list packages" in joined:
            return (0, "package:com.aurora.store\n", "")
        # GET whitelist (no +/- package suffix on the shell fragment).
        if joined.endswith("dumpsys deviceidle whitelist"):
            return (0, "user,com.aurora.store,1000\n", "")
        if "dumpsys deviceidle whitelist -com.aurora.store" in joined:
            return (0, "", "")
        if "appops get" in joined:
            return (0, "Mode: allow\n", "")
        if "appops set" in joined:
            return (0, "", "")
        return (0, "", "")

    changed, results = fp.apply_profile(
        run,
        "dev",
        {"package": "com.aurora.store", "battery_unrestricted": False},
        skip_missing=True,
    )
    assert changed is True
    joined = " ".join(calls)
    assert "whitelist -com.aurora.store" in joined
    assert any("appops set com.aurora.store RUN_IN_BACKGROUND ignore" in c for c in calls)
    assert any("appops set com.aurora.store RUN_ANY_IN_BACKGROUND ignore" in c for c in calls)
    items = results[0]["items"]
    assert any(i.get("status") == "unwhitelisted" for i in items)
