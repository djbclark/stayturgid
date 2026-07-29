import json
from unittest import mock

from control.lib.firerpa_fleet import get_fleet


def test_get_fleet_success():
    fake_inventory = {
        "stayturgid": {"hosts": ["s24", "p7a"]},
        "_meta": {
            "hostvars": {
                "s24": {
                    "ansible_host": "100.123.218.30",
                    "device_usb_serial": "RFCX219CHKA",
                    "firerpa_enabled": True,
                    "firerpa_runtime_status": "supported",
                    "firerpa_recovery_mode": "control-node-adb",
                    "firerpa_port": 65000,
                    "firerpa_certificate_device_path": "/data/local/tmp/firerpa/server/lamda.pem",
                },
                "p7a": {
                    "ansible_host": "100.65.230.108",
                    "firerpa_enabled": False,
                },
            }
        },
    }

    mock_result = mock.Mock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(fake_inventory)

    with mock.patch("subprocess.run", return_value=mock_result):
        fleet = get_fleet()

    assert len(fleet) == 2
    s24 = [t for t in fleet if t.alias == "s24"][0]
    p7a = [t for t in fleet if t.alias == "p7a"][0]

    assert s24.ip == "100.123.218.30"
    assert s24.usb_serial == "RFCX219CHKA"
    assert s24.enabled is True
    assert s24.runtime_status == "supported"
    assert s24.recovery_mode == "control-node-adb"
    assert s24.port == 65000

    assert p7a.ip == "100.65.230.108"
    assert p7a.enabled is False
    assert p7a.runtime_status == "supported"


def test_get_fleet_failure():
    mock_result = mock.Mock()
    mock_result.returncode = 1
    mock_result.stderr = "Error"

    with mock.patch("subprocess.run", return_value=mock_result):
        fleet = get_fleet()

    assert fleet == []
