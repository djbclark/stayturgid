"""A wireless adb endpoint is only trusted when it is the inventory's device (ro.serialno == usb serial).

Regression: hd8's stale inventory LAN IP 192.168.1.157 is now held by m11 (serial HA2PMV18); resolve_adb("hd8")
returned m11 and an install landed on the wrong tablet. Every resolver that tries the LAN address first must
check identity, skip a mismatch and log it.
"""

from __future__ import annotations

import subprocess

import access_monitor as am
import adb_reconnect as ar
import fire_help_monitor as fhm
import fleet_health as fh
import stayturgid_device as sd

HD8_USB = "HD8SERIAL1"
M11_USB = "HA2PMV18"
STALE_LAN = "192.168.1.157:5555"
HD8_TS = "100.64.0.8:5555"


def fake_adb(serials: dict[str, str], listed: str = ""):
    """Stand-in for subprocess.run of adb: `serials` maps endpoint -> ro.serialno it answers with."""

    def run(args, **_kw):
        args = list(args)
        rest = args[1:]
        if rest[:1] == ["devices"]:
            return subprocess.CompletedProcess(args, 0, listed, "")
        if rest[:1] == ["connect"]:
            ok = rest[1] in serials
            return subprocess.CompletedProcess(args, 0, "connected to %s" % rest[1] if ok else "failed", "")
        if rest[:2] == ["-s", rest[1]] and rest[2:5] == ["shell", "getprop", "ro.serialno"]:
            if rest[1] in serials:
                return subprocess.CompletedProcess(args, 0, serials[rest[1]] + "\n", "")
            return subprocess.CompletedProcess(args, 1, "", "error: device not found")
        return subprocess.CompletedProcess(args, 1, "", "")

    return run


# --------------------------------------------------------------------------
# control/lib/stayturgid_device.py
# --------------------------------------------------------------------------
def test_endpoint_identity_accepts_the_right_device(monkeypatch):
    monkeypatch.setattr(sd, "_run", lambda args, **kw: fake_adb({STALE_LAN: HD8_USB})(args))
    assert sd.endpoint_identity_ok(STALE_LAN, HD8_USB)


def test_endpoint_identity_rejects_and_reports_another_device(monkeypatch):
    monkeypatch.setattr(sd, "_run", lambda args, **kw: fake_adb({STALE_LAN: M11_USB})(args))
    said: list[str] = []
    assert not sd.endpoint_identity_ok(STALE_LAN, HD8_USB, report=said.append)
    assert said and M11_USB in said[0] and HD8_USB in said[0] and STALE_LAN in said[0]


def test_endpoint_identity_rejects_an_unreadable_serial(monkeypatch):
    monkeypatch.setattr(sd, "_run", lambda args, **kw: fake_adb({})(args))
    said: list[str] = []
    assert not sd.endpoint_identity_ok(STALE_LAN, HD8_USB, report=said.append)
    assert "could not read" in said[0]


def test_endpoint_identity_refuses_a_wireless_endpoint_without_a_known_serial(monkeypatch):
    monkeypatch.setattr(sd, "_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call adb")))
    said: list[str] = []
    assert not sd.endpoint_identity_ok(STALE_LAN, "-", report=said.append)
    assert not sd.endpoint_identity_ok(STALE_LAN, "")
    assert said and "no USB serial" in said[0] and STALE_LAN in said[0]


def test_resolve_adb_uses_no_wireless_endpoint_for_a_row_without_a_serial(tmp_path, monkeypatch, capsys):
    conf = tmp_path / "devices.conf"
    conf.write_text("noserial - 100.64.0.9 192.168.1.50\n")
    monkeypatch.setattr(sd, "_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call adb")))
    assert sd.resolve_adb("noserial", str(conf)) == "noserial"  # bare alias: nothing to connect to
    assert "no USB serial" in capsys.readouterr().err


def test_usb_serial_for(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("hd8 %s 100.64.0.8 192.168.1.157\nnoserial - 100.64.0.9\n" % HD8_USB)
    assert sd.usb_serial_for("hd8", str(conf)) == HD8_USB
    assert sd.usb_serial_for("noserial", str(conf)) == "-"
    assert sd.usb_serial_for("unknown", str(conf)) == "-"


def test_resolve_adb_skips_the_stale_lan_ip_held_by_another_tablet(tmp_path, monkeypatch):
    """The incident: LAN tried first, held by m11; the real hd8 is reachable on Tailscale."""
    conf = tmp_path / "devices.conf"
    conf.write_text("hd8 %s 100.64.0.8 192.168.1.157\n" % HD8_USB)
    adb = fake_adb({STALE_LAN: M11_USB, HD8_TS: HD8_USB})
    monkeypatch.setattr(sd, "_run", lambda args, **kw: adb(args))
    from importlib import util

    mod_path = sd.os.path.join(
        sd.os.path.dirname(sd.os.path.dirname(sd.os.path.dirname(sd.os.path.abspath(sd.__file__)))),
        "ansible_collections/stayturgid/android_common/plugins/module_utils/adb_resolve.py",
    )
    spec = util.spec_from_file_location("_adb_resolve_t", mod_path)
    ar_mod = util.module_from_spec(spec)
    spec.loader.exec_module(ar_mod)
    monkeypatch.setattr(ar_mod, "tcp_reachable", lambda ep, timeout=None: True)

    def run_command(cmd):
        if cmd and cmd[0].endswith("timeout"):
            cmd = cmd[2:]
        r = adb(["adb", *cmd[1:]])
        return r.returncode, r.stdout, r.stderr

    assert ar_mod.resolve_adb("hd8", run_command, str(conf)) == HD8_TS


# --------------------------------------------------------------------------
# control/lib/fleet_health.py
# --------------------------------------------------------------------------
def test_fleet_health_adb_reachable_skips_a_lan_endpoint_that_is_another_device(monkeypatch):
    adb = fake_adb({STALE_LAN: M11_USB, HD8_TS: HD8_USB})
    monkeypatch.setattr(fh.subprocess, "run", lambda args, **kw: adb(args))
    monkeypatch.setattr(sd, "_run", lambda args, **kw: adb(args))
    assert fh.adb_reachable([STALE_LAN, HD8_TS], HD8_USB) == "adb:%s" % HD8_TS


def test_fleet_health_adb_reachable_checks_an_already_listed_endpoint_too(monkeypatch):
    listed = "List of devices attached\n%s\tdevice\n" % STALE_LAN
    adb = fake_adb({STALE_LAN: M11_USB}, listed=listed)
    monkeypatch.setattr(fh.subprocess, "run", lambda args, **kw: adb(args))
    monkeypatch.setattr(sd, "_run", lambda args, **kw: adb(args))
    assert fh.adb_reachable([STALE_LAN], HD8_USB) is None


def test_fleet_health_adb_reachable_refuses_every_endpoint_without_a_serial(monkeypatch):
    adb = fake_adb({STALE_LAN: M11_USB})
    monkeypatch.setattr(fh.subprocess, "run", lambda args, **kw: adb(args))
    monkeypatch.setattr(sd, "_run", lambda args, **kw: adb(args))
    assert fh.adb_reachable([STALE_LAN]) is None
    assert fh.adb_reachable([STALE_LAN], "-") is None


def test_fleet_health_resolve_path_looks_the_serial_up_by_name(monkeypatch):
    seen = {}

    def reachable(addrs, usb_serial="-"):
        seen["usb"] = usb_serial
        return None

    monkeypatch.setattr(fh, "adb_reachable", reachable)
    monkeypatch.setattr(fh, "tcp_open", lambda *a, **k: False)
    monkeypatch.setattr(fh, "_usb_serial", lambda name: HD8_USB)
    assert fh.resolve_path("hd8", "100.64.0.8", "192.168.1.157") is None
    assert seen["usb"] == HD8_USB


# --------------------------------------------------------------------------
# control/bin/access_monitor.py
# --------------------------------------------------------------------------
def test_access_monitor_adb_reachable_skips_another_device(monkeypatch):
    adb = fake_adb({STALE_LAN: M11_USB, HD8_TS: HD8_USB})
    monkeypatch.setattr(am.subprocess, "run", lambda args, **kw: adb(args))
    monkeypatch.setattr(sd, "_run", lambda args, **kw: adb(args))
    monkeypatch.setattr(am, "_access_log", lambda _level, _msg: None)
    assert am.adb_reachable([STALE_LAN, HD8_TS], HD8_USB) == "adb:%s" % HD8_TS


def test_access_monitor_check_device_passes_the_inventory_serial(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(am, "_usb_serial", lambda name: HD8_USB)
    monkeypatch.setattr(am, "_access_log", lambda _level, _msg: None)
    monkeypatch.setattr(am, "tcp_open", lambda *a, **k: False)
    seen = {}

    def reachable(addrs, usb_serial="-"):
        seen["usb"] = usb_serial
        return None

    monkeypatch.setattr(am, "adb_reachable", reachable)
    monkeypatch.setattr(am, "notify", lambda *a, **k: None)
    am.check_device("hd8", "100.64.0.8", "192.168.1.157")
    assert seen["usb"] == HD8_USB


# --------------------------------------------------------------------------
# control/bin/adb_reconnect.py
# --------------------------------------------------------------------------
def test_adb_reconnect_identity_ok_rejects_another_device(monkeypatch):
    monkeypatch.setattr(sd, "_run", lambda args, **kw: fake_adb({STALE_LAN: M11_USB})(args))
    logged: list[str] = []
    monkeypatch.setattr(ar, "log", lambda alias, msg: logged.append(msg))
    assert not ar.identity_ok(STALE_LAN, HD8_USB, "hd8")
    assert logged and M11_USB in logged[0]
    assert not ar.identity_ok(STALE_LAN, "-", "hd8")  # no serial, no identity check, no endpoint


def test_adb_reconnect_does_not_call_a_stale_address_connected(tmp_path, monkeypatch):
    """A cached LAN address answers 'connected' but is another phone: skip it, fall through to Tailscale."""
    conf = tmp_path / "devices.conf"
    conf.write_text("hd8 %s 100.64.0.8 192.168.1.157\n" % HD8_USB)
    monkeypatch.setattr(ar, "CONF", str(conf))
    monkeypatch.setattr(ar, "ROOT", str(tmp_path / ".config" / "stayturgid"))
    monkeypatch.setattr(ar.os.path, "exists", lambda p: p == ar.ADB)
    monkeypatch.setattr(ar, "trim_log", lambda *a, **k: None)
    monkeypatch.setattr(ar, "usb_heal", lambda alias: None)
    monkeypatch.setattr(ar, "is_connected", lambda addr: False)
    monkeypatch.setattr(ar, "discover_lan_ip", lambda s: None)
    monkeypatch.setattr(ar, "discover_mdns", lambda s: None)
    monkeypatch.setattr(ar, "notify", lambda m: None)
    monkeypatch.setattr(ar, "log", lambda *a: None)
    tried = []

    def adb(args, timeout=15):
        tried.append(args[1])
        return type("R", (), {"stdout": "connected to %s" % args[1]})()

    monkeypatch.setattr(ar, "adb", adb)
    monkeypatch.setattr(ar, "identity_ok", lambda addr, expected, alias: addr == HD8_TS and expected == HD8_USB)
    assert ar.main(["hd8"]) == 0
    assert tried == [STALE_LAN, HD8_TS]  # the stale LAN address was tried, rejected, never cached
    cached = tmp_path / ".config" / "stayturgid" / "state" / ("device_ip_%s" % HD8_USB)
    assert cached.read_text() == HD8_TS


# --------------------------------------------------------------------------
# control/bin/fire_help_monitor.py: the unattended 15-minute job that repairs hd8
# --------------------------------------------------------------------------
def test_fire_help_never_guesses_the_raw_lan_address_of_a_device_with_a_serial(monkeypatch):
    monkeypatch.setattr(fhm.dev, "resolve_adb", lambda name: name)  # nothing reachable: bare alias
    monkeypatch.setattr(fhm.dev, "usb_serial_for", lambda name: HD8_USB)
    assert fhm.adb_targets("hd8", "100.64.0.8", "192.168.1.157") == []  # no endpoint, no guess
    monkeypatch.setattr(fhm.dev, "resolve_adb", lambda name: HD8_USB)  # a USB serial is the identity itself
    assert fhm.adb_targets("hd8", "100.64.0.8", "192.168.1.157") == [HD8_USB]


def test_fire_help_has_no_endpoint_at_all_for_a_row_without_a_serial(monkeypatch):
    monkeypatch.setattr(fhm.dev, "resolve_adb", lambda name: (_ for _ in ()).throw(AssertionError("no adb")))
    monkeypatch.setattr(fhm.dev, "usb_serial_for", lambda name: "-")
    logged: list[str] = []
    monkeypatch.setattr(fhm, "log", logged.append)
    assert fhm.adb_targets("x", "100.64.0.8", "192.168.1.157") == []
    assert logged and "no USB serial" in logged[0]


def test_fire_help_does_not_repair_the_tablet_that_answers_on_a_stale_address(monkeypatch):
    """The wrong tablet answers adb connect: no wireless-debug toggle, no Shizuku/Handsets start on it."""
    monkeypatch.setattr(fhm, "adb_targets", lambda *a: [STALE_LAN])
    monkeypatch.setattr(fhm.fph, "_ensure_connected", lambda t: None)  # connected fine
    monkeypatch.setattr(fhm.dev, "usb_serial_for", lambda name: HD8_USB)
    monkeypatch.setattr(sd, "_run", lambda args, **kw: fake_adb({STALE_LAN: M11_USB})(args))
    logged: list[str] = []
    monkeypatch.setattr(fhm, "log", logged.append)
    monkeypatch.setattr(fhm, "read_state", lambda name: 0)
    monkeypatch.setattr(fhm, "write_state", lambda name, n: None)
    touched: list[str] = []
    for fn in ("ensure_wireless_debugging", "needs_help"):
        monkeypatch.setattr(fhm, fn, lambda *a, _fn=fn: touched.append(_fn) or ("up", "x"))
    monkeypatch.setattr(fhm.fph, "cmd_shizuku_start", lambda t: touched.append("shizuku") or 0)
    monkeypatch.setattr(fhm.fph, "cmd_handsets_start", lambda t, p: touched.append("handsets") or 0)
    fhm.help_host("hd8", "100.64.0.8", "192.168.1.157")
    assert touched == []
    assert any("adb connect failed all targets" in m for m in logged)
    assert any(M11_USB in m for m in logged)
