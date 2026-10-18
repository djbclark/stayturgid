"""The awake/unlocked gate before Termux's first adb connect (2026-10-17).

Termux's first `adb connect localhost:5555` raises the "Allow USB debugging?" dialog,
and Samsung drops it silently on the lock screen (`startConfirmation:
isLockScreenMode`): the s24's dialog was lost that way and nobody was ever asked. So
`just bootstrap-ssh` (and deploy-termux, through the termux_screen_ready module)
checks `dumpsys window` isKeyguardShowing and `dumpsys power` mWakefulness first,
pings once when the phone is locked or asleep, and waits for it.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ansible_collections/stayturgid/termux/plugins/module_utils"))

import termux_run_as as tr

LOCKED_ASLEEP = "    isKeyguardShowing=true\n  mWakefulness=Asleep\nmWakefulness=1\n"
LOCKED_AWAKE = "    isKeyguardShowing=true\n  mWakefulness=Awake\n"
UNLOCKED_ASLEEP = "    isKeyguardShowing=false\n  mWakefulness=Asleep\n"
READY = "    isKeyguardShowing=false\n  mWakefulness=Awake\n"


class Phone:
    """adb fake: answers the screen-state shell from a script of dumps, records every call."""

    def __init__(self, *dumps):
        self.dumps = list(dumps)
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if tr.SCREEN_STATE_SHELL in cmd:
            dump = self.dumps.pop(0) if len(self.dumps) > 1 else self.dumps[0]
            return 0, dump, ""
        return 0, "", ""

    def typed(self):
        return [c for c in self.calls if "input" in c]


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.parametrize(
    ("dump", "expected"),
    [
        (LOCKED_ASLEEP, (False, False)),
        (LOCKED_AWAKE, (True, False)),
        (UNLOCKED_ASLEEP, (False, True)),
        (READY, (True, True)),
        ("", (None, None)),
        ("mWakefulness=1\nisKeyguardShowing=maybe\n", (None, None)),
        ("  mWakefulness=Dreaming\n    isKeyguardShowing=false\n", (False, True)),
    ],
)
def test_parse_screen_state(dump, expected):
    assert tr.parse_screen_state(dump) == expected


def test_only_a_phone_that_says_asleep_or_locked_blocks():
    assert tr.screen_ready(True, True)
    assert tr.screen_ready(None, None), "an unreadable state must not block"
    assert tr.screen_ready(True, None)
    assert not tr.screen_ready(False, True)
    assert not tr.screen_ready(True, False)


def test_adb_failure_reads_as_unknown_and_proceeds():
    def broken(cmd):
        return 1, "", "error: no devices"

    pings = []
    assert tr.wait_for_unlocked_screen(broken, "S", notify=pings.append) is False
    assert pings == []


def test_ready_phone_does_not_ping_or_wait():
    clock, pings = Clock(), []
    phone = Phone(READY)
    assert tr.wait_for_unlocked_screen(phone, "S", host="t2e", notify=pings.append, sleep=clock.sleep) is False
    assert pings == [] and clock.sleeps == []


def test_locked_phone_pings_once_then_proceeds_when_unlocked():
    clock, pings = Clock(), []
    phone = Phone(LOCKED_ASLEEP, LOCKED_ASLEEP, LOCKED_AWAKE, READY)
    waited = tr.wait_for_unlocked_screen(
        phone, "100.1.2.3:5555", host="t2e", notify=pings.append, sleep=clock.sleep, clock=clock
    )
    assert waited is True
    assert pings == ["stayturgid: unlock t2e for bootstrap-ssh"]
    assert clock.sleeps == [10, 10, 10], "polls every 10 s"


def test_ping_names_the_device_when_no_host_is_given():
    clock, pings = Clock(), []
    tr.wait_for_unlocked_screen(
        Phone(UNLOCKED_ASLEEP, READY), "SERIAL1", notify=pings.append, sleep=clock.sleep, clock=clock
    )
    assert pings == ["stayturgid: unlock SERIAL1 for bootstrap-ssh"]


def test_never_unlocked_fails_after_ten_minutes_with_a_clear_message():
    clock, pings = Clock(), []
    phone = Phone(LOCKED_AWAKE)
    with pytest.raises(RuntimeError) as exc:
        tr.wait_for_unlocked_screen(phone, "S", host="s24", notify=pings.append, sleep=clock.sleep, clock=clock)
    message = str(exc.value)
    assert "s24 is still locked after 600 s" in message
    assert "wake and unlock it, then re-run" in message
    assert pings == ["stayturgid: unlock s24 for bootstrap-ssh"], "one ping, no loop"
    assert clock.now == 600 and len(clock.sleeps) == 60


def test_message_says_asleep_and_locked_when_both():
    clock = Clock()
    with pytest.raises(RuntimeError) as exc:
        tr.wait_for_unlocked_screen(
            Phone(LOCKED_ASLEEP), "S", notify=lambda _m: None, sleep=clock.sleep, clock=clock, timeout_s=20
        )
    assert "asleep and locked" in str(exc.value)


def test_default_notify_is_looked_up_at_call_time(monkeypatch):
    pings = []
    monkeypatch.setattr(tr, "ping_operator", pings.append)
    clock = Clock()
    tr.wait_for_unlocked_screen(Phone(LOCKED_AWAKE, READY), "S", host="p7a", sleep=clock.sleep, clock=clock)
    assert pings == ["stayturgid: unlock p7a for bootstrap-ssh"]


def test_ping_operator_swallows_a_missing_hermes_ping(monkeypatch):
    monkeypatch.setattr(tr, "HERMES_PING", "/nonexistent/hermes-ping")
    tr.ping_operator("stayturgid: unlock t2e for bootstrap-ssh")


def test_typing_sshd_waits_for_the_unlock_and_never_types_while_locked(monkeypatch):
    clock = Clock()
    pings = []
    monkeypatch.setattr(tr, "ping_operator", pings.append)
    monkeypatch.setattr(tr.time, "sleep", clock.sleep)
    monkeypatch.setattr(tr.time, "monotonic", clock)
    monkeypatch.setattr(tr, "inversion_state", lambda *_a: "1")
    monkeypatch.setattr(tr, "sshd_domain", lambda *_a: "u:r:untrusted_app_27:s0")
    phone = Phone(LOCKED_AWAKE, LOCKED_AWAKE, READY)
    assert tr.start_sshd_from_app(phone, "S", host="t2e") is True
    assert pings == ["stayturgid: unlock t2e for bootstrap-ssh (typing sshd into Termux)"]
    typing = [i for i, c in enumerate(phone.calls) if "input" in c]
    polls = [i for i, c in enumerate(phone.calls) if tr.SCREEN_STATE_SHELL in c]
    assert typing and min(typing) > max(polls), "no keystroke before the last locked reading"


def test_bootstrap_device_waits_before_any_install_or_sshd_step(monkeypatch):
    clock = Clock()
    pings = []
    order = []
    monkeypatch.setattr(tr, "ping_operator", pings.append)
    monkeypatch.setattr(tr.time, "sleep", clock.sleep)
    monkeypatch.setattr(tr.time, "monotonic", clock)
    monkeypatch.setattr(tr, "termux_installed", lambda *_a, **_k: True)
    monkeypatch.setattr(tr, "run_as_available", lambda *_a, **_k: True)
    monkeypatch.setattr(tr, "ensure_openssh", lambda *_a, **_k: order.append("openssh") or False)
    monkeypatch.setattr(tr, "push_authorized_keys", lambda *_a, **_k: order.append("keys") or False)
    monkeypatch.setattr(tr, "ensure_sshd", lambda *_a, **_k: order.append("sshd") or False)
    phone = Phone(LOCKED_ASLEEP, READY)

    def run(cmd):
        result = phone(cmd)
        if tr.SCREEN_STATE_SHELL in cmd:
            order.append("screen:" + ("ready" if result[1] == READY else "locked"))
        return result

    tr.bootstrap_device(run, "S", ["ssh-ed25519 AAA k"], connect=False, host="t2e")
    assert order == ["screen:locked", "screen:ready", "openssh", "keys", "sshd"]
    assert pings == ["stayturgid: unlock t2e for bootstrap-ssh"]


def test_check_mode_never_waits_or_pings(monkeypatch):
    pings = []
    monkeypatch.setattr(tr, "ping_operator", pings.append)
    monkeypatch.setattr(tr, "termux_installed", lambda *_a, **_k: True)
    monkeypatch.setattr(tr, "run_as_available", lambda *_a, **_k: True)
    monkeypatch.setattr(tr, "ensure_openssh", lambda *_a, **_k: False)
    monkeypatch.setattr(tr, "push_authorized_keys", lambda *_a, **_k: False)
    monkeypatch.setattr(tr, "ensure_sshd", lambda *_a, **_k: False)
    phone = Phone(LOCKED_ASLEEP)
    tr.bootstrap_device(phone, "S", ["ssh-ed25519 AAA k"], connect=False, check_mode=True)
    assert pings == [] and not any(tr.SCREEN_STATE_SHELL in c for c in phone.calls)


def test_bootstrap_alias_passes_the_alias_as_the_ping_name(monkeypatch):
    sys.path.insert(0, str(REPO / "control/lib"))
    boot = importlib.import_module("termux_ssh_bootstrap")
    seen = {}
    monkeypatch.setattr(boot.tr, "bootstrap_device", lambda *_a, **k: seen.update(k))
    monkeypatch.setattr(boot, "discover_pubkey_paths", lambda *_a, **_k: [])
    monkeypatch.setattr(boot, "read_pubkey_lines", lambda *_a, **_k: ["ssh-ed25519 AAA k"])
    boot.bootstrap_alias("t2e", lambda alias: "100.1.2.3:5555", forward=False, verify_alias="")
    assert seen["host"] == "t2e"


# adbkey_state: the deploy-termux gate only waits when Termux's key is not yet authorised.

PUB = "QAAAAPubBlobAAAA u0_a601@localhost\n"


def _key_phone(*, pub, dumpsys, run_as=True):
    def run(cmd):
        joined = " ".join(cmd)
        if "run-as" in joined and joined.rstrip().endswith("true"):
            return (0 if run_as else 1), "", ""
        if "run-as" in joined and "adbkey.pub" in joined:
            return (0, pub, "") if pub is not None else (1, "", "No such file")
        if "dumpsys adb" in joined:
            return 0, dumpsys, ""
        return 0, "", ""

    return run


def test_adbkey_state_authorized_when_the_blob_is_in_dumpsys_adb():
    phone = _key_phone(pub=PUB, dumpsys="user_keys:\n  QAAAAPubBlobAAAA u0_a601@localhost\n")
    assert tr.adbkey_state(phone, "S") == "authorized"


def test_adbkey_state_unauthorized_when_the_blob_is_absent():
    phone = _key_phone(pub=PUB, dumpsys="user_keys:\n  QAAAAOldKeyZZZZ u0_a601@localhost\n")
    assert tr.adbkey_state(phone, "S") == "unauthorized"


def test_adbkey_state_no_key_on_a_fresh_termux():
    assert tr.adbkey_state(_key_phone(pub=None, dumpsys=""), "S") == "no-key"


def test_adbkey_state_unknown_when_run_as_does_not_work():
    assert tr.adbkey_state(_key_phone(pub=None, dumpsys="", run_as=False), "S") == "unknown"


# The module: skip when authorised, wait otherwise, fail after the timeout.


class FakeModule:
    def __init__(self, params, check_mode=False):
        self.params = params
        self.check_mode = check_mode
        self.run_command = lambda cmd: (0, "", "")

    def exit_json(self, **kw):
        raise SystemExit(("ok", kw))

    def fail_json(self, **kw):
        raise SystemExit(("fail", kw))


def _run_module(monkeypatch, params, *, key_state, waits=None, check_mode=False):
    mod = importlib.import_module("ansible_collections.stayturgid.termux.plugins.modules.termux_screen_ready")
    monkeypatch.setattr(mod, "AnsibleModule", lambda **_k: FakeModule(params, check_mode))
    monkeypatch.setattr(mod, "adbkey_state", lambda *_a, **_k: key_state)
    calls = []

    def fake_wait(*_a, **k):
        calls.append(k)
        if isinstance(waits, Exception):
            raise waits
        return bool(waits)

    monkeypatch.setattr(mod, "wait_for_unlocked_screen", fake_wait)
    with pytest.raises(SystemExit) as exit_info:
        mod.main()
    status, result = exit_info.value.args[0]
    return status, result, calls


BASE = {
    "device": "100.1.2.3:5555",
    "host": "s24",
    "purpose": "deploy-termux",
    "timeout": 600,
    "poll_interval": 10,
    "only_unless_key_authorized": True,
}


def test_module_skips_when_termux_key_is_already_authorised(monkeypatch):
    status, result, calls = _run_module(monkeypatch, dict(BASE), key_state="authorized")
    assert status == "ok" and result["checked"] is False and calls == []


def test_module_waits_when_the_key_is_new(monkeypatch):
    status, result, calls = _run_module(monkeypatch, dict(BASE), key_state="no-key", waits=True)
    assert status == "ok" and result["checked"] is True and result["waited"] is True
    assert calls[0]["host"] == "s24" and calls[0]["timeout_s"] == 600 and calls[0]["poll_s"] == 10


def test_module_fails_with_the_wait_message_after_the_timeout(monkeypatch):
    status, result, _calls = _run_module(
        monkeypatch, dict(BASE), key_state="unauthorized", waits=RuntimeError("s24 is still locked after 600 s")
    )
    assert status == "fail" and "still locked" in result["msg"]


def test_module_checks_even_an_authorised_key_when_asked(monkeypatch):
    params = dict(BASE, only_unless_key_authorized=False)
    status, result, calls = _run_module(monkeypatch, params, key_state="authorized", waits=False)
    assert status == "ok" and result["checked"] is True and len(calls) == 1


def test_module_skips_without_a_device_and_in_check_mode(monkeypatch):
    assert _run_module(monkeypatch, dict(BASE, device=""), key_state="no-key")[1]["checked"] is False
    assert _run_module(monkeypatch, dict(BASE), key_state="no-key", check_mode=True)[1]["checked"] is False


def test_deploy_gate_task_precedes_the_first_termux_adb_connect():
    import yaml

    role = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/tasks/main.yml"
    names = [t.get("name", "") for t in yaml.safe_load(role.read_text())]
    gate = names.index("Wait for an unlocked screen before Termux's first adb connect")
    assert gate < names.index("Grant Termux permissions via privileged shell")
    task = yaml.safe_load(role.read_text())[gate]
    assert task["delegate_to"] == "localhost"
    assert "stayturgid_no_local_adb" in task["when"]


def test_bootstrap_playbooks_pass_the_host_name_for_the_ping():
    import yaml

    for name in ("bootstrap.yml", "preflight.yml"):
        plays = yaml.safe_load((REPO / "ansible/playbooks/fleet" / name).read_text())
        tasks = [task for play in plays for task in play["tasks"] if "stayturgid.termux.termux_ssh_bootstrap" in task]
        assert [t["stayturgid.termux.termux_ssh_bootstrap"]["host"] for t in tasks] == ["{{ inventory_hostname }}"], (
            name
        )


def test_hermes_ping_default_is_the_user_bin_script():
    assert tr.HERMES_PING == os.path.expanduser("~/.local/bin/hermes-ping")
