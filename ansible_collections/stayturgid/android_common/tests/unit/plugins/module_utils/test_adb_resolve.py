"""Unit tests for the adb_resolve module_util (control-node ADB target picker)."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import adb_resolve as ar


def _listing(*lines):
    """Fake run_command: 'adb devices' returns lines; connect/shell succeed."""

    def run(cmd):
        if len(cmd) >= 2 and cmd[0].endswith("timeout"):
            cmd = cmd[2:]
        if cmd[:2] == ["adb", "devices"]:
            return 0, ("\n".join(lines) + "\n") if lines else "", ""
        if cmd[:2] == ["adb", "connect"]:
            return 0, "connected to %s" % cmd[2], ""
        if len(cmd) >= 4 and cmd[:2] == ["adb", "-s"] and cmd[3] == "shell":
            return 0, "EXAMPLE-SERIAL-ONEUI\n", ""
        return 1, "", ""

    return run


def _conf(tmp_path, text):
    conf = tmp_path / "devices.conf"
    conf.write_text(text)
    return str(conf)


def test_device_row_parses_and_pads(tmp_path):
    conf = _conf(tmp_path, "# comment\noneui-device RFCX 100.0.0.11 192.0.2.9\nstock-android-device ONLYUSB\n")
    assert ar.device_row("oneui-device", conf) == ("RFCX", "100.0.0.11", "192.0.2.9")
    assert ar.device_row("stock-android-device", conf) == ("ONLYUSB", "-", "-")
    assert ar.device_row("missing", conf) is None


def test_wireless_endpoints_lan_before_tailscale():
    assert ar.wireless_endpoints(("RFCX", "100.0.0.11", "192.0.2.9")) == [
        "192.0.2.9:5555",
        "100.0.0.11:5555",
    ]
    assert ar.wireless_endpoints(("RFCX", "-", "-")) == []


def test_adb_online_matches_only_device_state():
    listing = "192.0.2.9:5555\tdevice\n100.0.0.11:5555\toffline\n"
    assert ar.adb_online(listing, "192.0.2.9:5555") is True
    assert ar.adb_online(listing, "100.0.0.11:5555") is False


def test_resolve_unknown_alias_passes_through(tmp_path):
    conf = _conf(tmp_path, "oneui-device RFCX - -\n")
    assert ar.resolve_adb("raw:5555", _listing(), conf) == "raw:5555"


def test_resolve_prefers_online_usb(tmp_path):
    conf = _conf(tmp_path, "oneui-device EXAMPLE-SERIAL-ONEUI 100.0.0.11 192.0.2.9\n")
    assert ar.resolve_adb("oneui-device", _listing("EXAMPLE-SERIAL-ONEUI\tdevice"), conf) == "EXAMPLE-SERIAL-ONEUI"


def test_resolve_matches_ro_serialno_when_ip_drifts(tmp_path):
    conf = _conf(tmp_path, "oneui-device EXAMPLE-SERIAL-ONEUI 100.0.0.11 192.0.2.55\n")
    # USB serial not directly listed, but a drifted IP reports the same ro.serialno
    assert ar.resolve_adb("oneui-device", _listing("192.0.2.99:5555\tdevice"), conf) == "192.0.2.99:5555"


def test_match_usb_serial_mdns_id_with_spaces(tmp_path):
    conf = _conf(tmp_path, "stock-android-device EXAMPLE-SERIAL-STOCK 100.0.0.12 192.0.2.9\n")
    listing = "adb-EXAMPLE-SERIAL-STOCK-JIE0Dg (2)._adb-tls-connect._tcp\tdevice\n100.0.0.12:5555\tdevice\n"

    def run(cmd):
        if len(cmd) >= 2 and cmd[0].endswith("timeout"):
            cmd = cmd[2:]
        if cmd[:2] == ["adb", "devices"]:
            return 0, listing, ""
        if len(cmd) >= 5 and cmd[:2] == ["adb", "-s"] and cmd[3] == "shell":
            return 0, "EXAMPLE-SERIAL-STOCK\n", ""
        return 1, "", ""

    assert (
        ar.resolve_adb("stock-android-device", run, conf) == "adb-EXAMPLE-SERIAL-STOCK-JIE0Dg (2)._adb-tls-connect._tcp"
    )


def test_resolve_static_fallback_without_run_command(tmp_path, monkeypatch):
    # A row with a serial: the static guess is Tailscale only, never the LAN address.
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: True)
    conf = _conf(tmp_path, "stock-android-device SERIAL1 100.0.0.11 192.0.2.9\n")
    assert ar.resolve_adb("stock-android-device", None, conf) == "100.0.0.11:5555"


def test_resolve_refuses_every_wireless_endpoint_for_a_row_without_a_serial(tmp_path, monkeypatch):
    # No serial, no identity check: no endpoint is guessed, probed or connected, with or without a runner.
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: (_ for _ in ()).throw(AssertionError("probe")))
    conf = _conf(tmp_path, "stock-android-device - 100.0.0.11 192.0.2.9\n")

    def boom(cmd):
        raise AssertionError("must not run adb: %r" % (cmd,))

    assert ar.resolve_adb("stock-android-device", None, conf) == "stock-android-device"
    assert ar.resolve_adb("stock-android-device", boom, conf) == "stock-android-device"


def test_connect_wireless_skips_unreachable(monkeypatch):
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: False)
    calls = []
    ar.connect_wireless(lambda cmd: calls.append(cmd) or (0, "", ""), "192.0.2.9:5555")
    assert calls == []  # never issued the blocking adb connect


def test_connect_wireless_connects_when_reachable(monkeypatch):
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: True)
    calls = []

    def run(cmd):
        raw_cmd = cmd[2:] if len(cmd) >= 2 and cmd[0].endswith("timeout") else cmd
        calls.append(raw_cmd)
        if raw_cmd[:2] == ["adb", "devices"]:
            return 0, "192.0.2.9:5555\tdevice\n", ""
        return 0, "", ""

    assert ar.connect_wireless(run, "192.0.2.9:5555") is True
    assert ["adb", "connect", "192.0.2.9:5555"] in calls


def test_resolve_gates_connect_behind_probe(tmp_path, monkeypatch):
    conf = _conf(tmp_path, "stock-android-device USB 100.0.0.12 192.0.2.9\n")
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: ep == "100.0.0.12:5555")
    seen = []

    def run(cmd):
        raw_cmd = cmd[2:] if len(cmd) >= 2 and cmd[0].endswith("timeout") else cmd
        seen.append(raw_cmd)
        if raw_cmd[:2] == ["adb", "devices"]:
            if any(c[:2] == ["adb", "connect"] for c in seen):
                return 0, "100.0.0.12:5555\tdevice\n", ""
            return 0, "", ""
        return 0, "", ""

    assert ar.resolve_adb("stock-android-device", run, conf) == "100.0.0.12:5555"
    assert ["adb", "connect", "192.0.2.9:5555"] not in seen
    assert ["adb", "connect", "100.0.0.12:5555"] in seen


# --- wrong-device hazard: a stale LAN IP may now belong to another phone -----------------------------
HD8_USB = "HD8SERIAL1"
OTHER_USB = "HA2PMV18"
STALE_LAN = "192.168.1.157:5555"
HD8_TS = "100.64.0.8:5555"


def _by_endpoint(serials, listed=""):
    """Fake run_command: `serials` maps adb endpoint -> the ro.serialno it answers with."""

    connected = []

    def run(cmd):
        if len(cmd) >= 2 and cmd[0].endswith("timeout"):
            cmd = cmd[2:]
        if cmd[:2] == ["adb", "devices"]:
            return 0, listed + "".join("%s\tdevice\n" % ep for ep in connected), ""
        if cmd[:2] == ["adb", "connect"]:
            if cmd[2] in serials:
                connected.append(cmd[2])
                return 0, "connected to %s" % cmd[2], ""
            return 0, "failed", ""
        if cmd[:2] == ["adb", "-s"] and cmd[3:6] == ["shell", "getprop", "ro.serialno"]:
            if cmd[2] in serials:
                return 0, serials[cmd[2]] + "\n", ""
            return 1, "", "device not found"
        return 1, "", ""

    return run


def test_resolve_skips_a_lan_endpoint_held_by_another_device(tmp_path, monkeypatch, capsys):
    conf = _conf(tmp_path, "hd8 %s 100.64.0.8 192.168.1.157\n" % HD8_USB)
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: True)
    run = _by_endpoint({STALE_LAN: OTHER_USB, HD8_TS: HD8_USB})
    assert ar.resolve_adb("hd8", run, conf) == HD8_TS
    err = capsys.readouterr().err
    assert STALE_LAN in err and OTHER_USB in err and HD8_USB in err  # the skip is logged


def test_resolve_skips_an_already_listed_endpoint_of_another_device(tmp_path, monkeypatch):
    conf = _conf(tmp_path, "hd8 %s 100.64.0.8 192.168.1.157\n" % HD8_USB)
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: True)
    listed = "List of devices attached\n%s\tdevice\n" % STALE_LAN
    run = _by_endpoint({STALE_LAN: OTHER_USB, HD8_TS: HD8_USB}, listed=listed)
    assert ar.resolve_adb("hd8", run, conf) == HD8_TS


def test_resolve_never_returns_the_wrong_device_when_the_right_one_is_down(tmp_path, monkeypatch):
    conf = _conf(tmp_path, "hd8 %s 100.64.0.8 192.168.1.157\n" % HD8_USB)
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: ep == STALE_LAN)
    run = _by_endpoint({STALE_LAN: OTHER_USB})
    # Tailscale is the stable identity; the stale LAN address is never the guess.
    assert ar.resolve_adb("hd8", run, conf) == HD8_TS
    assert ar.resolve_adb("hd8", None, conf) == HD8_TS


def test_resolve_rejects_an_endpoint_whose_serial_cannot_be_read(tmp_path, monkeypatch):
    conf = _conf(tmp_path, "hd8 %s 100.64.0.8 192.168.1.157\n" % HD8_USB)
    monkeypatch.setattr(ar, "tcp_reachable", lambda ep, timeout=None: True)

    def run(cmd):
        if len(cmd) >= 2 and cmd[0].endswith("timeout"):
            cmd = cmd[2:]
        if cmd[:2] == ["adb", "devices"]:
            return 0, "", ""
        if cmd[:2] == ["adb", "connect"]:
            return 0, "connected to %s" % cmd[2], ""
        return 1, "", "unauthorized"

    assert not ar.endpoint_identity_ok(run, STALE_LAN, HD8_USB, report=lambda m: None)
    assert ar.resolve_adb("hd8", run, conf) == HD8_TS  # nothing verified: Tailscale guess, never the LAN one


def test_endpoint_identity_without_a_known_serial_refuses(monkeypatch):
    def boom(cmd):
        raise AssertionError("must not run adb")

    said = []
    assert not ar.endpoint_identity_ok(boom, STALE_LAN, "-", report=said.append)
    assert not ar.endpoint_identity_ok(boom, STALE_LAN, "")
    assert said and "no USB serial" in said[0]
