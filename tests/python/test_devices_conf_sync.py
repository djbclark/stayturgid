import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from control.lib import devices_conf_sync as dcs

INV = {
    "_meta": {
        "hostvars": {
            "t2e": {
                "ansible_host": "100.1.1.1",
                "device_usb_serial": "T2",
                "device_lan_ip": "10.0.0.5",
                "device_label": "Titan 2",
            },
            "m11": {
                "ansible_host": "10.0.0.9",
                "device_usb_serial": "HA2",
                "device_label": "Lenovo Idea Tab 11 (TB336FU)",
            },
        }
    }
}


def test_render_row_matches_the_template_columns():
    row = dcs.render_row("m11", INV["_meta"]["hostvars"]["m11"])
    assert row == "m11 HA2 10.0.0.9 - Lenovo Idea Tab 11 (TB336FU) -"


def test_refuses_a_row_without_a_usb_serial(tmp_path):
    import pytest

    for serial in (None, "", "-", "  "):
        with pytest.raises(ValueError, match="nodrive has no device_usb_serial"):
            dcs.render_row("nodrive", {"ansible_host": "10.0.0.7", "device_usb_serial": serial})
    conf = tmp_path / "devices.conf"
    inv = {"_meta": {"hostvars": {"nodrive": {"ansible_host": "10.0.0.7"}}}}
    with pytest.raises(ValueError):
        dcs.ensure_aliases(inv, ["nodrive"], conf)
    assert not conf.exists()  # nothing half-written


def test_appends_only_missing_hosts_and_keeps_existing_rows(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("# header\nt2e T2 100.1.1.1 10.0.0.5 Titan 2 -\n", encoding="utf-8")
    assert dcs.ensure_aliases(INV, ["t2e", "m11"], conf) == ["m11"]
    lines = conf.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# header"
    assert lines.count("t2e T2 100.1.1.1 10.0.0.5 Titan 2 -") == 1
    assert lines[-1].startswith("m11 HA2 ")
    assert dcs.ensure_aliases(INV, ["t2e", "m11"], conf) == []


def test_creates_the_file_when_absent(tmp_path):
    conf = tmp_path / "sub" / "devices.conf"
    assert dcs.ensure_aliases(INV, ["m11"], conf) == ["m11"]
    assert conf.read_text(encoding="utf-8").startswith("m11 HA2 ")
