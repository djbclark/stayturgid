"""Unit tests for shared/mac/stayturgid_device.py — the shizuku.json patcher
and UI-XML parsing that were fragile python-in-bash / sed pipelines."""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "shared", "mac"))
import stayturgid_device as dev  # noqa: E402


def test_patch_preserves_other_apps():
    current = json.dumps({"version": 2, "packages": [
        {"uid": 10001, "flags": 2, "packages": ["com.other.app"]},
    ]})
    out = json.loads(dev.patch_shizuku_json(current, 10123, "org.autojs.autojs6"))
    uids = {e["uid"] for e in out["packages"]}
    assert uids == {10001, 10123}, "existing grant preserved, new one added"
    added = [e for e in out["packages"] if e["uid"] == 10123][0]
    assert added == {"uid": 10123, "flags": 2, "packages": ["org.autojs.autojs6"]}


def test_patch_replaces_same_uid():
    current = json.dumps({"version": 2, "packages": [
        {"uid": 10123, "flags": 2, "packages": ["old.pkg"]},
    ]})
    out = json.loads(dev.patch_shizuku_json(current, 10123, "new.pkg"))
    assert len(out["packages"]) == 1
    assert out["packages"][0]["packages"] == ["new.pkg"]


def test_patch_empty_and_malformed_start_fresh():
    for start in ("", "   ", "not json{"):
        out = json.loads(dev.patch_shizuku_json(start, 10123, "a.b"))
        assert out["version"] == 2
        assert out["packages"] == [{"uid": 10123, "flags": 2, "packages": ["a.b"]}]


def test_patch_output_is_compact():
    out = dev.patch_shizuku_json("", 5, "a.b")
    assert " " not in out  # separators=(",", ":")


def test_parse_uid():
    assert dev.parse_uid("package:org.autojs.autojs6 uid:10123") == "10123"
    assert dev.parse_uid("package:x.y.z  uid:0") == "0"
    assert dev.parse_uid("package:no.uid.here") is None
    assert dev.parse_uid("") is None


def test_parse_switch_checked_and_unchecked():
    xml = (
        '<node text="Use Dhizuku, Shizuku or Sui to install" />'
        '<node class="android.widget.Switch" checked="false" '
        'bounds="[900,1200][1000,1300]" />'
    )
    sw = dev.parse_switch(xml, "Use Dhizuku, Shizuku or Sui to install")
    assert sw == (False, 950, 1250)

    xml2 = xml.replace('checked="false"', 'checked="true"')
    assert dev.parse_switch(xml2, "Use Dhizuku, Shizuku or Sui to install")[0] is True


def test_parse_switch_bounds_before_checked():
    xml = (
        '<node text="Use Dhizuku, Shizuku or Sui to install" />'
        '<node class="android.widget.Switch" '
        'bounds="[10,20][30,40]" checked="true" />'
    )
    assert dev.parse_switch(xml, "Use Dhizuku, Shizuku or Sui to install") == (True, 20, 30)


def test_parse_switch_absent():
    assert dev.parse_switch("<node text='other' />", "missing label") is None
    assert dev.parse_switch("label present but no switch", "label") is None


def test_parse_button_center():
    xml = '<node resource-id="android:id/button1" bounds="[100,200][300,400]" />'
    assert dev.parse_button_center(xml, "android:id/button1") == (200, 300)
    assert dev.parse_button_center("<node />", "android:id/button1") is None


def test_resolve_adb_and_ssh_host(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX 100.123 192.168.68.55\n")
    # not plugged in -> tailscale ip:5555
    monkeypatch.setattr(dev, "_run", lambda a, **k: type("R", (), {"stdout": ""})())
    assert dev.resolve_adb("s24", str(conf)) == "100.123:5555"
    # plugged in -> usb serial
    monkeypatch.setattr(dev, "_run",
                        lambda a, **k: type("R", (), {"stdout": "RFCX\tdevice\n"})())
    assert dev.resolve_adb("s24", str(conf)) == "RFCX"
    # unknown alias passes through; ssh host only for known devices
    assert dev.resolve_adb("raw:5555", str(conf)) == "raw:5555"
    assert dev.resolve_ssh_host("s24", str(conf)) == "s24"
    assert dev.resolve_ssh_host("raw:5555", str(conf)) == ""

    # ts=- must not yield "-:5555"; fall back to alias when USB absent
    monkeypatch.setattr(dev, "_run", lambda a, **k: type("R", (), {"stdout": ""})())
    conf.write_text("s24 RFCX - -\n")
    assert dev.resolve_adb("s24", str(conf)) == "s24"
    # lan fallback when tailscale missing
    conf.write_text("p7a - - 192.168.1.9\n")
    assert dev.resolve_adb("p7a", str(conf)) == "192.168.1.9:5555"
