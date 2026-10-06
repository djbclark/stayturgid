"""Unit tests for control/bin/usb_shizuku_heal.py: decision logic and heal steps with a fake adb."""

from __future__ import annotations

import os

import pytest
import usb_shizuku_heal as uh

SERIAL = "EXAMPLE-SERIAL-ONEUI"
RUNNING = 'Broadcast completed: result=1, data="RUNNING (binder=true, ADB: USB:on WiFi:5555)"'
CRASHED = 'Broadcast completed: result=1, data="CRASHED (exit 1)"'
HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
LISTEN = HEADER + "   0: 00000000000000000000000000000000:15B3 00000000000000000000000000000000:0000 0A 0 0 0 2000\n"
CLOSED = HEADER + "   0: 0100007F:CFF3 0100007F:15B3 01 0 0 0 10383\n"


class FakePhone:
    """Minimal adb: `devices`, /proc/net dump, HEADLESS_STATUS/START, tcpip, connect."""

    def __init__(self, usb="device", listening=False, running=False, start_works=True, tcpip_works=True):
        self.usb = usb
        self.listening = listening
        self.running = running
        self.start_works = start_works
        self.tcpip_works = tcpip_works
        self.calls: list[list[str]] = []

    def __call__(self, args, timeout):
        self.calls.append(list(args))
        if args == ["devices"]:
            rows = "" if self.usb is None else "%s\t%s\n" % (SERIAL, self.usb)
            return 0, "List of devices attached\n" + rows
        if args[0] == "connect":
            return 0, "connected to %s" % args[1]
        if args[0] == "disconnect":
            return 0, "disconnected %s" % args[1]
        assert args[:2] == ["-s", SERIAL]
        assert self.usb == "device", "acted on a non-authorised device"
        rest = args[2:]
        if rest[0] == "tcpip":
            if self.tcpip_works:
                self.listening = True
            return 0, "restarting in TCP mode port: 5555"
        cmd = rest[1]
        if cmd.startswith("cat /proc/net/tcp"):
            return 0, LISTEN if self.listening else CLOSED
        if uh.STATUS_ACTION in cmd:
            return 0, RUNNING if self.running else CRASHED
        if uh.START_ACTION in cmd:
            if self.start_works:
                self.running = True
            return 0, "Broadcast completed: result=0"
        raise AssertionError("unexpected adb call %r" % args)

    def did(self, word):
        return any(word in " ".join(c) for c in self.calls)


@pytest.fixture
def env(tmp_path, monkeypatch):
    conf = tmp_path / "devices.conf"
    conf.write_text(
        "s24 %s 100.0.0.11 192.0.2.5 Galaxy S24 -\nhd8 FIRE-SERIAL 100.0.0.13 - Kindle Fire HD 8 -\n" % SERIAL
    )
    monkeypatch.setattr(uh, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(uh, "_log", lambda level, msg: None)
    notices: list[str] = []
    return {"conf": str(conf), "notices": notices, "notify": lambda t, m: notices.append(m)}


def run_pass(env, phone, alias="s24", dry_run=False):
    return uh.heal_alias(
        alias, dry_run=dry_run, run=phone, conf=env["conf"], notify=env["notify"], sleep=lambda s: None
    )


# ---- pure parsing / decision ----------------------------------------------------------


def test_parse_adb_devices():
    text = "List of devices attached\nA\tdevice\nB\tunauthorized\n100.1:5555\tdevice\n"
    assert uh.parse_adb_devices(text) == {"A": "device", "B": "unauthorized", "100.1:5555": "device"}


def test_parse_status():
    assert uh.parse_status(0, RUNNING).startswith("RUNNING")
    assert uh.parse_status(0, "Broadcast completed: result=0") == ""
    assert uh.parse_status(1, "error") is None
    assert uh.parse_status(124, "timeout") is None


def test_parse_listening():
    assert uh.parse_listening(0, LISTEN) is True
    assert uh.parse_listening(0, CLOSED) is False  # 15B3 as a remote port is not a listener
    assert uh.parse_listening(1, "") is None


@pytest.mark.parametrize(
    "usb,listening,status,cool,action",
    [
        (None, None, None, True, "none"),
        ("unauthorized", None, None, True, "skip"),
        ("offline", None, None, True, "skip"),
        ("device", None, "RUNNING", True, "skip"),
        ("device", True, None, True, "skip"),
        ("device", True, "RUNNING (x)", True, "none"),
        ("device", False, "RUNNING (x)", True, "heal"),
        ("device", True, "CRASHED (x)", True, "heal"),
        ("device", True, "", True, "heal"),
        ("device", False, "", False, "skip"),
    ],
)
def test_decide(usb, listening, status, cool, action):
    assert uh.decide("s24", "Galaxy S24", usb, listening, status, cool).action == action


def test_decide_steps():
    d = uh.decide("s24", "Galaxy S24", "device", False, "RUNNING (x)", True)
    assert (d.tcpip, d.start) == (True, False)
    d = uh.decide("s24", "Galaxy S24", "device", True, "CRASHED", True)
    assert (d.tcpip, d.start) == (False, True)


def test_decide_excludes_hd8_and_fire_labels():
    assert uh.decide("hd8", "x", "device", False, "", True).action == "skip"
    assert uh.decide("tablet", "Kindle Fire HD 8", "device", False, "", True).action == "skip"


# ---- full passes with a fake phone ------------------------------------------------------


def test_healthy_phone_no_action(env):
    phone = FakePhone(listening=True, running=True)
    out = run_pass(env, phone)
    assert ": none: healthy" in out
    assert not phone.did("tcpip") and not phone.did(uh.START_ACTION) and not phone.did("connect")
    assert env["notices"] == []


def test_not_on_usb_no_action(env):
    phone = FakePhone(usb=None)
    assert "not on USB" in run_pass(env, phone)
    assert phone.calls == [["devices"]]


def test_unauthorized_never_touched(env):
    phone = FakePhone(usb="unauthorized")
    out = run_pass(env, phone)
    assert "skip" in out and "not authorised" in out
    assert phone.calls == [["devices"]]


def test_hd8_never_touched(env):
    phone = FakePhone()
    assert "excluded" in run_pass(env, phone, alias="hd8")
    assert phone.calls == []


def test_dry_run_changes_nothing(env):
    phone = FakePhone(listening=False, running=False)
    out = run_pass(env, phone, dry_run=True)
    assert "would run: tcpip 5555, HEADLESS_START, connect" in out
    assert not phone.did("tcpip") and not phone.did(uh.START_ACTION)
    assert not os.path.exists(os.path.join(uh.STATE_DIR, "s24"))


def test_full_heal_this_mornings_case(env):
    phone = FakePhone(listening=False, running=False)
    out = run_pass(env, phone)
    assert "OK" in out
    ordered = [" ".join(c) for c in phone.calls]
    i_tcpip = next(i for i, c in enumerate(ordered) if " tcpip 5555" in c)
    i_start = next(i for i, c in enumerate(ordered) if uh.START_ACTION in c)
    i_conn = next(i for i, c in enumerate(ordered) if c.startswith("connect 100.0.0.11:5555"))
    i_disc = next(i for i, c in enumerate(ordered) if c.startswith("disconnect 100.0.0.11:5555"))
    assert i_tcpip < i_start < i_disc < i_conn
    assert len(env["notices"]) == 1 and "restored" in env["notices"][0]


def test_shizuku_only_down_skips_tcpip(env):
    phone = FakePhone(listening=True, running=False)
    assert "OK" in run_pass(env, phone)
    assert not phone.did("tcpip") and phone.did(uh.START_ACTION)


def test_port_only_closed_skips_start(env):
    phone = FakePhone(listening=False, running=True)
    assert "OK" in run_pass(env, phone)
    assert phone.did("tcpip") and not phone.did(uh.START_ACTION)


def test_rate_limited_to_one_attempt_per_10_min(env):
    phone = FakePhone(listening=False, running=False, start_works=False)
    assert "FAILED" in run_pass(env, phone)
    phone.calls.clear()
    out = run_pass(env, phone)
    assert "cooldown" in out
    assert not phone.did("tcpip") and not phone.did(uh.START_ACTION)


def test_failure_notifies_once_per_streak(env, monkeypatch):
    phone = FakePhone(listening=True, running=False, start_works=False)
    assert "FAILED" in run_pass(env, phone)
    monkeypatch.setattr(uh, "cooldown_ok", lambda alias, now=None: True)
    assert "FAILED" in run_pass(env, phone)
    assert len(env["notices"]) == 1 and "FAILED" in env["notices"][0]
    # Healthy pass clears the streak; the next failure notifies again.
    phone.running = True
    run_pass(env, phone)
    phone.running = False
    run_pass(env, phone)
    assert len(env["notices"]) == 2


def test_usb_not_back_after_tcpip_fails(env):
    phone = FakePhone(listening=False, running=True, tcpip_works=False)
    out = run_pass(env, phone)
    assert "FAILED" in out and "usb not back" in out
    assert not phone.did("connect")


def test_run_alias_honours_skip_env(env, monkeypatch):
    called = []
    monkeypatch.setattr(uh, "heal_alias", lambda alias: called.append(alias))
    monkeypatch.setenv(uh.SKIP_ENV, "1")
    uh.run_alias("s24")
    monkeypatch.delenv(uh.SKIP_ENV)
    uh.run_alias("s24")
    assert called == ["s24"]
