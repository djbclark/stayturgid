"""Unit tests for device/termux/py/stayturgid_autojs6_guard.py."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "device" / "termux" / "py"))

import stayturgid_autojs6_guard as guard  # noqa: E402


def _write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_guard_arms_restart_when_stale_and_repair_fresh(tmp_path, monkeypatch):
    sd = tmp_path / "sd"
    home = tmp_path / "home"
    log = sd / "logs" / "watchdog.log"
    monkeypatch.setattr(guard, "SD", str(sd))
    monkeypatch.setattr(guard, "LOG", str(log))
    monkeypatch.setattr(guard, "HOME", str(home))
    monkeypatch.setattr(guard, "STATE", str(home / ".stayturgid" / "state"))
    monkeypatch.setattr(guard, "TRIGGER", str(sd / "run" / "start_autojs6_now"))
    monkeypatch.setattr(guard, "TRIGGER_SDCARD", str(sd / "run" / "start_autojs6_now"))
    monkeypatch.setattr(
        guard, "RESTART_STAMP", str(home / ".stayturgid" / "state" / "last_autojs6_restart_trigger")
    )
    monkeypatch.setattr(
        guard, "NOTIFY_STAMP", str(home / ".stayturgid" / "state" / "last_autojs6_stale_notify")
    )
    monkeypatch.setattr(guard, "maybe_notify", lambda: None)

    stale = datetime.now() - timedelta(hours=2)
    fresh = datetime.now() - timedelta(minutes=2)

    def fmt(ts: datetime) -> str:
        return ts.strftime("%Y-%m-%d %H:%M:%S")

    _write_log(
        log,
        [
            fmt(stale) + " [watchdog] cycle start trigger=interval (autojs6)",
            fmt(fresh) + " [repair] INFO: STATUS port=open shizuku=up sshd=up a11y=up shell=yes wifi=up rc=0",
        ],
    )

    assert guard.action_check() == 0
    assert (sd / "run" / "start_autojs6_now").is_file()
    text = log.read_text(encoding="utf-8")
    assert "armed start_autojs6_now" in text


def test_guard_skips_restart_when_watchdog_fresh(tmp_path, monkeypatch):
    sd = tmp_path / "sd"
    home = tmp_path / "home"
    log = sd / "logs" / "watchdog.log"
    monkeypatch.setattr(guard, "SD", str(sd))
    monkeypatch.setattr(guard, "LOG", str(log))
    monkeypatch.setattr(guard, "HOME", str(home))
    monkeypatch.setattr(guard, "STATE", str(home / ".stayturgid" / "state"))
    monkeypatch.setattr(guard, "TRIGGER", str(sd / "run" / "start_autojs6_now"))
    monkeypatch.setattr(guard, "TRIGGER_SDCARD", str(sd / "run" / "start_autojs6_now"))
    monkeypatch.setattr(
        guard, "RESTART_STAMP", str(home / ".stayturgid" / "state" / "last_autojs6_restart_trigger")
    )

    now = datetime.now()

    def fmt(ts: datetime) -> str:
        return ts.strftime("%Y-%m-%d %H:%M:%S")

    _write_log(
        log,
        [
            fmt(now - timedelta(minutes=5)) + " [watchdog] cycle start trigger=interval (autojs6)",
            fmt(now - timedelta(minutes=2))
            + " [repair] INFO: STATUS port=open shizuku=up sshd=up a11y=up shell=yes wifi=up rc=0",
        ],
    )

    assert guard.action_check() == 0
    assert not (sd / "run" / "start_autojs6_now").exists()


def test_restart_logs_request_not_unverified_success(tmp_path, monkeypatch):
    sd = tmp_path / "sd"
    home = tmp_path / "home"
    log = sd / "logs" / "watchdog.log"
    boot = sd / "autojs6" / "scripts" / "boot-launcher.js"
    boot.parent.mkdir(parents=True)
    boot.write_text("// boot", encoding="utf-8")

    monkeypatch.setattr(guard, "SD", str(sd))
    monkeypatch.setattr(guard, "LOG", str(log))
    monkeypatch.setattr(guard, "STATE", str(home / ".stayturgid" / "state"))
    monkeypatch.setattr(guard, "TRIGGER", str(sd / "run" / "start_autojs6_now"))
    monkeypatch.setattr(guard, "TRIGGER_SDCARD", str(sd / "run" / "start_autojs6_now"))
    monkeypatch.setattr(
        guard, "RESTART_STAMP", str(home / ".stayturgid" / "state" / "restart")
    )
    monkeypatch.setattr(guard, "run", lambda _args: SimpleNamespace(returncode=0))

    guard.maybe_restart_trigger()

    text = log.read_text(encoding="utf-8")
    assert "restart requested via am start" in text
    assert "restarted AutoJs6" not in text
