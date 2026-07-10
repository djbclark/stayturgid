"""Unit tests for fleet app privilege helpers."""
import os
import sys

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "ansible_collections", "stayturgid", "android_common")
)
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import adb_shell  # noqa: E402
import fleet_privileges as fp  # noqa: E402


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
