"""Unit tests for control/lib/stayturgid_device.py — the shizuku.json patcher
and UI-XML parsing that were fragile python-in-bash / sed pipelines."""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "control", "lib"))
import stayturgid_device as dev  # noqa: E402

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_MOD = _REPO / "ansible_collections/stayturgid/android_common/plugins/module_utils/adb_resolve.py"
_spec = importlib.util.spec_from_file_location("adb_resolve", _MOD)
adb_resolve = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(adb_resolve)


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


def test_parse_switch_same_node_text():
    """Label on the Switch node itself (text after bounds/checked)."""
    xml = (
        '<node class="android.widget.Switch" checked="true" '
        'bounds="[1,2][3,4]" text="Shizuku access" />'
    )
    assert dev.parse_switch(xml, "Shizuku access") == (True, 2, 3)


def test_parse_switch_same_node_content_desc():
    xml = (
        '<node bounds="[10,20][30,40]" checked="false" '
        'class="android.widget.Switch" content-desc="Foreground service" />'
    )
    assert dev.parse_switch(xml, "Foreground service") == (False, 20, 30)


def test_parse_switch_before_label_by_y():
    """AutoJs6 drawer: Switch node precedes label text; match by Y center."""
    xml = (
        '<node class="android.widget.Switch" checked="true" '
        'bounds="[608,1010][730,1081]" />'
        '<node text="Shizuku access" bounds="[113,1020][571,1071]" />'
    )
    assert dev.parse_switch(xml, "Shizuku access") == (True, 669, 1045)


def test_parse_text_center():
    xml = '<node text="Allow" bounds="[100,200][300,400]" />'
    assert dev.parse_text_center(xml, "Allow") == (200, 300)
    assert dev.parse_text_center(xml, "Deny") is None


def test_parse_button_center():
    xml = '<node resource-id="android:id/button1" bounds="[50,60][150,120]" />'
    assert dev.parse_button_center(xml, "android:id/button1") == (100, 90)
    assert dev.parse_button_center(xml, "android:id/button2") is None


def test_parse_content_desc_center():
    xml = '<node content-desc="Open navigation drawer" bounds="[10,20][50,80]" />'
    assert dev.parse_content_desc_center(xml, "Open navigation drawer") == (30, 50)


def test_resolve_adb_and_ssh_host(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX 100.123 192.168.68.55\n")

    def fake_run(cmd, **kw):
        if cmd[:2] == ["adb", "devices"]:
            return type("R", (), {"returncode": 0, "stdout": "RFCX\tdevice\n", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(dev, "_run", fake_run)
    assert dev.resolve_adb("s24", str(conf)) == "RFCX"

    def offline(cmd, **kw):
        if cmd[:2] == ["adb", "devices"]:
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if cmd[:2] == ["adb", "connect"]:
            return type("R", (), {"returncode": 0, "stdout": "failed", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(dev, "_run", offline)
    monkeypatch.setattr(
        adb_resolve,
        "tcp_reachable",
        lambda ep, timeout=None: False,
    )
    assert dev.resolve_adb("s24", str(conf)) == "100.123:5555"
    # unknown alias passes through; ssh host only for known devices
    assert dev.resolve_adb("raw:5555", str(conf)) == "raw:5555"
    assert dev.resolve_ssh_host("s24", str(conf)) == "s24"
    assert dev.resolve_ssh_host("raw:5555", str(conf)) == ""

    # ts=- must not yield "-:5555"; fall back to alias when USB absent
    monkeypatch.setattr(
        dev,
        "_run",
        lambda a, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    conf.write_text("s24 RFCX - -\n")
    assert dev.resolve_adb("s24", str(conf)) == "s24"
    # lan fallback when tailscale missing
    conf.write_text("p7a - - 192.168.1.9\n")
    assert dev.resolve_adb("p7a", str(conf)) == "192.168.1.9:5555"


def test_read_shizuku_json_missing_ok():
    shell = dev.PrivShell.__new__(dev.PrivShell)
    shell.sh = lambda cmd: (0, "") if cmd == "true" else (1, "")
    text, ok = shell.read_shizuku_json("/data/shizuku.json")
    assert ok is True
    assert text == ""


def test_read_shizuku_json_unreadable_aborts():
    shell = dev.PrivShell.__new__(dev.PrivShell)

    def fake_sh(cmd):
        if cmd == "true":
            return 0, ""
        if cmd.startswith("test -f"):
            return 0, ""
        if cmd.startswith("cat"):
            return 0, ""
        return 1, ""

    shell.sh = fake_sh
    text, ok = shell.read_shizuku_json("/data/shizuku.json")
    assert ok is False
    assert text == ""


def test_read_shizuku_json_cat_failure_aborts():
    shell = dev.PrivShell.__new__(dev.PrivShell)

    def fake_sh(cmd):
        if cmd == "true":
            return 0, ""
        if cmd.startswith("test -f"):
            return 0, ""
        if cmd.startswith("cat"):
            return 1, ""
        return 1, ""

    shell.sh = fake_sh
    text, ok = shell.read_shizuku_json("/data/shizuku.json")
    assert ok is False
