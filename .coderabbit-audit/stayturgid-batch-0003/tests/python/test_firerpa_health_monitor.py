"""Policy and recovery tests for the Mac-side FIRERPA monitor."""

from __future__ import annotations

from types import SimpleNamespace

import firerpa_health_monitor as monitor


def test_recover_device_uses_canonical_lifecycle(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    target = monitor.FirerpaTarget(
        alias="fire-tablet",
        ip="100.64.0.8",
        recovery_mode=monitor.RECOVERY_MODE_CONTROL_NODE_ADB,
    )
    monkeypatch.setattr(monitor, "_recovery_adb_target", lambda _target: "100.64.0.8:5555")
    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    assert monitor.recover_device(target) == (True, "recovered")
    assert calls == [
        [
            monitor.sys.executable,
            str(monitor.LIFECYCLE),
            "start",
            "--adb-target",
            "100.64.0.8:5555",
            "--port=65000",
            "--certificate=/data/local/tmp/firerpa/server/lamda.pem",
        ]
    ]


def test_main_reports_known_incompatibility_and_recovers_opted_in_host(monkeypatch) -> None:
    logs: list[tuple[int, str]] = []
    checks = {"fire-tablet": 0}
    targets = [
        monitor.FirerpaTarget(alias="phone", ip="100.64.0.1"),
        monitor.FirerpaTarget(
            alias="preview-phone",
            ip="100.64.0.2",
            enabled=False,
            runtime_status="pending-incompatible-runtime",
        ),
        monitor.FirerpaTarget(
            alias="fire-tablet",
            ip="100.64.0.8",
            recovery_mode=monitor.RECOVERY_MODE_CONTROL_NODE_ADB,
        ),
    ]

    def fake_check(alias: str, _ip: str, _port: int):
        if alias == "fire-tablet":
            checks[alias] += 1
            if checks[alias] == 1:
                return {"firerpa": "unreachable"}
        return {"firerpa": "10.0", "sshd": "up", "shizuku": "up"}

    monkeypatch.setattr(monitor, "get_fleet", lambda: targets)
    monkeypatch.setattr(monitor, "Device", object())
    monkeypatch.setattr(monitor, "check_device", fake_check)
    monkeypatch.setattr(monitor, "recover_device", lambda _target: (True, "recovered"))
    monkeypatch.setattr(monitor.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(monitor, "trim_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        monitor,
        "log",
        lambda _name, level, message, **_kwargs: logs.append((level, message)),
    )

    assert monitor.main() == 0
    assert checks["fire-tablet"] == 2
    assert any("firerpa=pending-incompatible-runtime" in message for _, message in logs)
    assert any("fire-tablet" in message and "recovery=recovered" in message for _, message in logs)


def test_main_fails_when_control_node_recovery_fails(monkeypatch) -> None:
    target = monitor.FirerpaTarget(
        alias="fire-tablet",
        ip="100.64.0.8",
        recovery_mode=monitor.RECOVERY_MODE_CONTROL_NODE_ADB,
    )
    logs: list[str] = []
    monkeypatch.setattr(monitor, "get_fleet", lambda: [target])
    monkeypatch.setattr(monitor, "Device", object())
    monkeypatch.setattr(monitor, "check_device", lambda *_args: {"firerpa": "unreachable"})
    monkeypatch.setattr(monitor, "recover_device", lambda _target: (False, "adb-unreachable"))
    monkeypatch.setattr(monitor, "trim_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        monitor,
        "log",
        lambda _name, _level, message, **_kwargs: logs.append(message),
    )

    assert monitor.main() == 1
    assert "recovery=adb-unreachable" in logs[-1]
    assert "issues=firerpa_down,recovery_failed" in logs[-1]
