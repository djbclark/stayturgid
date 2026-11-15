"""A missing [watchdog] marker is telemetry, not a dead check."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import fleet_health as fh


def test_gather_does_not_probe_a_retired_accessibility_package():
    assert "a11y=unknown" not in fh.HEALTH_GATHER
    assert "a11y=retired" not in fh.HEALTH_GATHER


def test_gather_reports_retired_watchdog_when_the_legacy_marker_is_absent():
    assert "_wd_age=$(_age '\\[watchdog\\]')" in fh.HEALTH_GATHER
    assert '[ "$_wd_age" = missing ]' in fh.HEALTH_GATHER
    assert 'echo "watchdog_age=$_wd_age"' in fh.HEALTH_GATHER


def test_adb_fallback_uses_the_same_retired_watchdog_reading():
    src = inspect.getsource(fh.adb_health)
    assert "a11y=unknown" not in src
    assert "a11y=retired" not in src
    assert '[ "$_wd_age" = missing ]' in src


def _tasker_monitor(tmp_path: Path, dump: str) -> str:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    pkg = tmp_path / "pkg.txt"
    body = tmp_path / "dump.txt"
    pkg.write_text("package:/data/app/net.dinglisch.android.taskerm/base.apk\n")
    body.write_text(dump)
    stubs = 'adb() { case "$*" in *"pm path"*) cat "%s" ;; *dumpsys*) cat "%s" ;; esac; }\npm() { :; }\n' % (pkg, body)
    env = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
    env["HOME"] = str(home)
    result = subprocess.run(
        ["bash", "-c", stubs + fh._TASKER_BODY],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return fh.parse_kv(result.stdout)["tasker_monitor"]


def test_tasker_monitor_ghost_record_is_stopped_and_a_live_process_is_running(tmp_path):
    header = "ACTIVITY MANAGER SERVICES (dumpsys activity services)\n  * ServiceRecord{1 u0 "
    ghost = header + "net.dinglisch.android.taskerm/.MonitorService}\n    app=null\n"
    live = (
        header
        + "net.dinglisch.android.taskerm/.MonitorService}\n    app=ProcessRecord{abc 1:net.dinglisch.android.taskerm/u0a1}\n"
    )
    assert _tasker_monitor(tmp_path / "ghost", ghost) == "stopped"
    assert _tasker_monitor(tmp_path / "live", live) == "running"


def test_retired_watchdog_is_not_a_health_issue():
    text = "watchdog_age=retired\n"
    report = fh.parse_kv(text)
    assert report["watchdog_age"] == "retired"
    assert (
        fh.evaluate_health(
            {
                "ssh_echo": "ok",
                "sshd": "ok",
                "repair_age": "100",
                "agent_heartbeat_age": "30",
                "watchdog_age": "retired",
                "port": "open",
                "shizuku": "up",
            }
        )
        == []
    )
