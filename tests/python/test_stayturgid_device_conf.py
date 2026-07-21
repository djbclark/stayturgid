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
