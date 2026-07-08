"""Parity tests for Ansible adb_resolve vs shared/mac/stayturgid_device."""
import os
import sys

from conftest import REPO

sys.path.insert(0, os.path.join(
    REPO, "ansible_collections", "stayturgid", "android_common", "plugins", "module_utils"
))

import adb_resolve  # noqa: E402


def _run(cmd):
    if cmd[:2] == ["adb", "devices"]:
        return 0, "RFCX\tdevice\n", ""
    return 0, "", ""


def test_resolve_adb_lan_fallback(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("p7a - - 192.168.1.9\n")
    assert adb_resolve.resolve_adb("p7a", _run, str(conf)) == "192.168.1.9:5555"


def test_resolve_adb_no_dash_tailscale(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX - -\n")

    def no_usb(_cmd):
        return 0, "", ""

    assert adb_resolve.resolve_adb("s24", no_usb, str(conf)) == "s24"
