import sys
import types

# firerpa_heal.py hard-requires the real lamda-client hardware SDK at import
# time (sys.exit(1) on ImportError) -- not installed in CI/dev. Stub it so
# main()'s pure alias-resolution logic can be exercised without the package,
# then remove the stub again once the import completes: firerpa_heal.py only
# needs `lamda.client.Device` at its own import time (it caches what it needs
# into its own module namespace), and leaving a fake `lamda` package sitting
# in sys.modules for the rest of the pytest process could shadow a real
# import elsewhere.
_injected_lamda = "lamda" not in sys.modules
if _injected_lamda:
    _lamda_pkg = types.ModuleType("lamda")
    _lamda_client = types.ModuleType("lamda.client")
    # setattr: ModuleType has no declared Device/client attributes for mypy.
    setattr(_lamda_client, "Device", object)
    setattr(_lamda_pkg, "client", _lamda_client)
    sys.modules["lamda"] = _lamda_pkg
    sys.modules["lamda.client"] = _lamda_client

try:
    from control.bin import firerpa_heal  # noqa: E402
finally:
    if _injected_lamda:
        sys.modules.pop("lamda", None)
        sys.modules.pop("lamda.client", None)

from control.lib.firerpa_fleet import FirerpaTarget  # noqa: E402


def test_main_logs_expected_when_recovery_mode_explains_unreachable(monkeypatch):
    """A device whose inventory declares firerpa_recovery_mode:
    control-node-adb is expected to show FIRERPA as unreachable (Fire OS
    blocks Termux's own shell_data_file execution there; Mac ADB supplies
    UID 2000 instead) -- confirmed real for hd8 2026-08-02. This must be
    driven by the inventory-derived field, not a hardcoded alias, so any
    other host declared the same way gets the same "expected" annotation."""
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(firerpa_heal, "_log", lambda level, msg: calls.append((level, msg)))
    monkeypatch.setattr(firerpa_heal, "trim_log", lambda *a, **k: None)
    monkeypatch.setattr(firerpa_heal, "heal_device", lambda ip, port: {"firerpa": "unreachable"})
    target = FirerpaTarget(alias="hd8", ip="1.2.3.4", enabled=True, recovery_mode="control-node-adb")
    monkeypatch.setattr("control.lib.firerpa_fleet.get_fleet", lambda: [target])

    rc = firerpa_heal.main(["--all"])

    assert rc == 1
    assert any("expected" in msg and "hd8" in msg for _level, msg in calls)


def test_main_does_not_suppress_for_a_different_alias_with_expected_recovery_mode(monkeypatch):
    """The suppression must follow recovery_mode, not a hardcoded alias --
    an alias other than "hd8" with the same declared recovery_mode still
    gets the "expected" annotation."""
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(firerpa_heal, "_log", lambda level, msg: calls.append((level, msg)))
    monkeypatch.setattr(firerpa_heal, "trim_log", lambda *a, **k: None)
    monkeypatch.setattr(firerpa_heal, "heal_device", lambda ip, port: {"firerpa": "unreachable"})
    target = FirerpaTarget(alias="some-other-device", ip="9.9.9.9", enabled=True, recovery_mode="control-node-adb")
    monkeypatch.setattr("control.lib.firerpa_fleet.get_fleet", lambda: [target])

    rc = firerpa_heal.main(["--all"])

    assert rc == 1
    assert any("expected" in msg and "some-other-device" in msg for _level, msg in calls)


def test_main_does_not_suppress_for_normal_unreachable(monkeypatch):
    """A device with no special recovery_mode gets no "expected" annotation
    when FIRERPA is unreachable -- this is a real outage, not documented
    inventory-declared behavior."""
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(firerpa_heal, "_log", lambda level, msg: calls.append((level, msg)))
    monkeypatch.setattr(firerpa_heal, "trim_log", lambda *a, **k: None)
    monkeypatch.setattr(firerpa_heal, "heal_device", lambda ip, port: {"firerpa": "unreachable"})
    target = FirerpaTarget(alias="s24", ip="5.6.7.8", enabled=True, recovery_mode="none")
    monkeypatch.setattr("control.lib.firerpa_fleet.get_fleet", lambda: [target])

    rc = firerpa_heal.main(["--all"])

    assert rc == 1
    assert calls == []


def test_restart_shizuku_withheld_reply_is_not_a_failure(monkeypatch):
    sent = []
    logs = []
    monkeypatch.setattr(firerpa_heal, "is_shizuku_alive", lambda _d: False)
    monkeypatch.setattr(firerpa_heal, "_log", lambda level, msg: logs.append((level, msg)))
    monkeypatch.setattr(firerpa_heal.time, "sleep", lambda _s: None)

    def exec_stdout(_d, cmd, timeout=5):
        sent.append(cmd)
        return 'Broadcast completed: result=4, data="AUTH_UNANSWERED"'

    monkeypatch.setattr(firerpa_heal, "_exec_stdout", exec_stdout)
    assert firerpa_heal.restart_shizuku(object()) == "withheld"
    assert len(sent) == 1 and "force" not in sent[0]
    assert logs == []


def test_shizuku_start_withheld_detection():
    assert firerpa_heal.shizuku_start_withheld("Broadcast completed: result=4")
    assert firerpa_heal.shizuku_start_withheld('Broadcast completed: result=0, data="AUTH_UNANSWERED"')
    assert not firerpa_heal.shizuku_start_withheld("Broadcast completed: result=0")
    assert not firerpa_heal.shizuku_start_withheld("Broadcast completed: result=40")


def test_note_shizuku_auth_logs_once_per_change(monkeypatch, tmp_path):
    logs = []
    monkeypatch.setattr(firerpa_heal, "LOG_ROOT", str(tmp_path))
    monkeypatch.setattr(firerpa_heal, "_log", lambda level, msg: logs.append((level, msg)))
    firerpa_heal.note_shizuku_auth("fireos-device", False)
    firerpa_heal.note_shizuku_auth("fireos-device", True)
    firerpa_heal.note_shizuku_auth("fireos-device", True)
    assert logs == [(firerpa_heal.WARNING, "fireos-device: " + firerpa_heal.SHIZUKU_START_WITHHELD_MSG)]
    firerpa_heal.note_shizuku_auth("fireos-device", False)
    assert len(logs) == 2 and logs[1][0] == firerpa_heal.NOTICE
