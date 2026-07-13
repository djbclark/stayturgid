"""devices.conf parsing in control/lib/stayturgid_device.py (review L9)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control" / "lib"))
import stayturgid_device as sd  # noqa: E402


def test_iter_devices_conf_and_monitor_hosts(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("# c\ns24 USB1 100.1 192.1\np7a USB2 100.2\nshort\n")
    rows = list(sd.iter_devices_conf(str(conf)))
    assert rows == [
        ("s24", "USB1", "100.1", "192.1", "-"),
        ("p7a", "USB2", "100.2", "-", "-"),
    ]
    mon = list(sd.iter_monitor_hosts(str(conf)))
    assert mon == [("s24", "100.1", "192.1"), ("p7a", "100.2", "-")]
    assert sd.device_row("s24", str(conf)) == ("USB1", "100.1", "192.1")
    assert sd.device_row("nope", str(conf)) is None
