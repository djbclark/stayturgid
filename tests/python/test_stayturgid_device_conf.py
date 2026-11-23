"""devices.conf parsing in control/lib/stayturgid_device.py (review L9)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control" / "lib"))
import stayturgid_device as sd


def test_iter_devices_conf_and_monitor_hosts(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("# c\noneui-device USB1 100.1 192.1\nstock-android-device USB2 100.2\nshort\n")
    rows = list(sd.iter_devices_conf(str(conf)))
    assert rows == [
        ("oneui-device", "USB1", "100.1", "192.1", "-"),
        ("stock-android-device", "USB2", "100.2", "-", "-"),
    ]
    mon = list(sd.iter_monitor_hosts(str(conf)))
    assert mon == [("oneui-device", "100.1", "192.1"), ("stock-android-device", "100.2", "-")]
    assert sd.device_row("oneui-device", str(conf)) == ("USB1", "100.1", "192.1")
    assert sd.device_row("nope", str(conf)) is None


def test_alias_for_host_reverse_lookup(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("# c\noneui-device USB1 100.1 192.1\nstock-android-device USB2 100.2\n")
    assert sd.alias_for_host("100.1", str(conf)) == "oneui-device"
    assert sd.alias_for_host("192.1", str(conf)) == "oneui-device"
    assert sd.alias_for_host("100.2", str(conf)) == "stock-android-device"
    assert sd.alias_for_host("9.9.9.9", str(conf)) is None


def test_device_flags_and_bool_defaults(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text(
        "# v4\n"
        "oneui-device USB1 100.1 192.1 OneUI Phone - alert_on_offline=true\n"
        "fireos-device USB2 100.2 - Fire Tablet - usb_heal=false\n"
        "stock-android-device USB3 100.3 - Stock Phone -\n"
    )
    assert sd.device_flags("oneui-device", str(conf)) == {"alert_on_offline": "true"}
    assert sd.device_flag_bool("oneui-device", "alert_on_offline", False, str(conf)) is True
    assert sd.device_flag_bool("oneui-device", "usb_heal", True, str(conf)) is True
    assert sd.device_flag_bool("fireos-device", "usb_heal", True, str(conf)) is False
    assert sd.device_flag_bool("fireos-device", "alert_on_offline", False, str(conf)) is False
    assert sd.device_flag_bool("stock-android-device", "alert_on_offline", False, str(conf)) is False
    assert sd.device_flag_bool("stock-android-device", "usb_heal", True, str(conf)) is True
    assert sd.device_flag_bool("missing", "usb_heal", True, str(conf)) is True
