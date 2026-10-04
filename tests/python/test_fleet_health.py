"""Unit tests for control/lib/fleet_health.py and control/bin/fleet_health_monitor.py."""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
sys.path.insert(0, str(REPO / "control" / "bin"))

import fleet_health as fh
import fleet_health_monitor as fhm


def test_parse_kv():
    text = "sshd=ok\nwatchdog_age=120\na11y=ok\njunk\n"
    assert fh.parse_kv(text)["sshd"] == "ok"
    assert fh.parse_kv(text)["watchdog_age"] == "120"


def test_health_gather_tracks_python_boot_supervisor():
    assert "start_adb\\.py" in fh.HEALTH_GATHER
    assert "start-adb\\.sh" not in fh.HEALTH_GATHER


def test_health_gather_reads_native_agent_log():
    """Dual-run: STATUS and agent_age come from agent.log as well as watchdog."""
    assert "agent.log" in fh.HEALTH_GATHER
    assert "agent_age=" in fh.HEALTH_GATHER
    assert r"\[agent\] STATUS" in fh.HEALTH_GATHER


def test_health_gather_tails_devlog_failures():
    """Central-logging gap (2026-07-31): the same probe now also tails
    watchdog.log ERR/WARNING lines and agent.log failure lines."""
    assert "DEVLOG_WATCHDOG|" in fh.HEALTH_GATHER
    assert "DEVLOG_AGENT|" in fh.HEALTH_GATHER
    assert r"\[repair\] (ERR|WARNING):" in fh.HEALTH_GATHER


_FAKE_ADB = """#!/bin/bash
echo "$*" >> "$ADB_LOG"
case "$1" in
  devices)
    echo "List of devices attached"
    st=$(cat "$ADB_STATE" 2>/dev/null)
    [ -n "$st" ] && printf 'localhost:5555\\t%s\\n' "$st"
    exit 0 ;;
  connect)
    [ -n "${ADB_AFTER_CONNECT:-}" ] && echo "$ADB_AFTER_CONNECT" > "$ADB_STATE"
    if [ "$(cat "$ADB_STATE" 2>/dev/null)" = unauthorized ]; then
      echo "failed to authenticate to localhost:5555"; exit 1
    fi
    echo "connected to localhost:5555"; exit 0 ;;
  disconnect) : > "$ADB_STATE"; exit 0 ;;
esac
exit 1
"""


def _gate_sandbox(tmp_path, state, *, helper=True, after_connect=""):
    """HOME + PATH where `adb` is a fake and python3 is this interpreter."""
    import shutil

    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "adb").write_text(_FAKE_ADB)
    (bin_dir / "adb").chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    if helper:
        stg_bin = home / ".stayturgid" / "bin"
        stg_bin.mkdir(parents=True)
        shutil.copy(REPO / "device" / "termux" / "py" / "stayturgid_shell.py", stg_bin / "stayturgid_shell.py")
    else:
        home.mkdir()
    (tmp_path / "state").write_text(state + "\n" if state else "")
    env = {
        "HOME": str(home),
        "PATH": "%s:/usr/bin:/bin" % bin_dir,
        "ADB_LOG": str(tmp_path / "adb.log"),
        "ADB_STATE": str(tmp_path / "state"),
        "ADB_AFTER_CONNECT": after_connect,
    }
    return env


def _run_gate(env):
    import subprocess

    r = subprocess.run(["bash", "-c", fh._ADB_GATE_BODY], env=env, capture_output=True, text=True, timeout=60)
    log = Path(env["ADB_LOG"])
    calls = log.read_text().splitlines() if log.exists() else []
    return fh.parse_kv(r.stdout).get("adb_auth"), calls


def test_health_gather_connects_only_through_the_gate():
    assert fh._ADB_GATE_BODY in fh.HEALTH_GATHER
    # The one remaining bare connect is the pre-gate fallback, behind its
    # own "not listed" check.
    assert fh.HEALTH_GATHER.count("adb connect localhost:5555") == 1


def test_health_gather_gate_unauthorised_never_reconnects(tmp_path):
    env = _gate_sandbox(tmp_path, "unauthorized")
    for _ in range(3):
        state, calls = _run_gate(env)
        assert state == "waiting"
    assert not [c for c in calls if c.split()[0] in ("connect", "reconnect", "disconnect", "kill-server")]


def test_health_gather_gate_after_revoke_offers_key_once(tmp_path):
    """Three 5-minute gathers after a revoke: the first offers Termux's key,
    the next two find the dialog outstanding and leave it alone."""
    env = _gate_sandbox(tmp_path, "", after_connect="unauthorized")
    states = [_run_gate(env)[0] for _ in range(3)]
    _state, calls = _run_gate(env)
    assert states == ["waiting"] * 3
    assert [c for c in calls if c.startswith("connect")] == ["connect localhost:5555"]
    assert (tmp_path / "home" / ".stayturgid" / "state" / "adb-auth-wait").is_file()


def test_health_gather_gate_authorised_is_unchanged(tmp_path):
    env = _gate_sandbox(tmp_path, "device")
    state, calls = _run_gate(env)
    assert state == "device"
    assert calls == ["devices"]


@pytest.mark.parametrize("helper", [True, False])
def test_health_gather_gate_offline_still_connects(tmp_path, helper):
    """offline is a closed 5555 or an adbd restart, not a dialog: the gather
    keeps master's connect, and no back-off marker is written."""
    env = _gate_sandbox(tmp_path, "offline", helper=helper, after_connect="device")
    state, calls = _run_gate(env)
    assert state == ("device" if helper else "unknown")
    assert "connect localhost:5555" in calls
    assert not (tmp_path / "home" / ".stayturgid" / "state" / "adb-auth-wait").exists()


def test_health_gather_gate_fallback_for_pre_gate_deploy(tmp_path):
    env = _gate_sandbox(tmp_path, "unauthorized", helper=False)
    state, calls = _run_gate(env)
    assert state == "waiting"
    assert calls == ["devices"]

    env = _gate_sandbox(tmp_path / "absent", "", helper=False, after_connect="device")
    state, calls = _run_gate(env)
    assert state == "unknown"
    assert calls == ["devices", "connect localhost:5555"]


def test_extract_devlog_lines_splits_markers_and_keeps_rest():
    text = (
        "sshd=ok\n"
        "DEVLOG_WATCHDOG|2026-07-31 17:42:21 [repair] ERR: Tailscale repair FAILED "
        "(runtime=down policy=down); unlocked operator action may be required\n"
        "watchdog_age=10\n"
        "DEVLOG_AGENT|2026-07-31 17:43:00 [agent] catastrophic FAILED steps=shell_wireless\n"
    )
    remaining, devlog = fh.extract_devlog_lines(text)
    kv = fh.parse_kv(remaining)
    assert kv == {"sshd": "ok", "watchdog_age": "10"}
    assert devlog == [
        {
            "source": "watchdog.log",
            "line": (
                "2026-07-31 17:42:21 [repair] ERR: Tailscale repair FAILED "
                "(runtime=down policy=down); unlocked operator action may be required"
            ),
        },
        {
            "source": "agent.log",
            "line": "2026-07-31 17:43:00 [agent] catastrophic FAILED steps=shell_wireless",
        },
    ]


def test_extract_devlog_lines_no_markers_is_passthrough():
    text = "sshd=ok\nwatchdog_age=10\n"
    remaining, devlog = fh.extract_devlog_lines(text)
    assert remaining == "sshd=ok\nwatchdog_age=10"
    assert devlog == []


def test_ssh_health_surfaces_devlog_without_corrupting_report(monkeypatch):
    class MockResult:
        returncode = 0
        stdout = (
            "sshd=ok\n"
            "DEVLOG_WATCHDOG|2026-07-31 17:42:21 [repair] ERR: Tailscale repair FAILED "
            "(runtime=down policy=down)\n"
        )
        stderr = ""

    monkeypatch.setattr(fh.subprocess, "run", lambda *a, **k: MockResult())
    report = fh.ssh_health("oneui-device")
    assert report["sshd"] == "ok"
    assert "runtime" not in report  # the raw '=' inside the log line must not leak in
    assert report["_devlog"] == [
        {
            "source": "watchdog.log",
            "line": "2026-07-31 17:42:21 [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)",
        }
    ]


def test_device_log_epoch():
    parsed = fhm._device_log_epoch("2026-07-13 12:38:56 [watchdog] example failure")
    expected = datetime.datetime(2026, 7, 13, 12, 38, 56).timestamp()
    assert parsed == expected
    assert fhm._device_log_epoch("no timestamp") is None


def test_evaluate_healthy():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "ok",
        "shell5555": "ok",
        "watchdog_age": "100",
        "repair_age": "200",
        "agent_heartbeat_age": "60",
        "a11y": "ok",
        "autojs6_a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    assert fh.evaluate_health(report) == []


def test_evaluate_retired_watchdog_stale_is_telemetry_only():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "watchdog_age": str(fh.WATCHDOG_FRESH_SEC + 1),
        "repair_age": "100",
        "a11y": "ok",
        "autojs6_a11y": "ok",
    }
    issues = fh.evaluate_health(report)
    assert "watchdog_stale" not in issues
    assert "autojs6_a11y_stale" not in issues


def test_evaluate_retired_watchdog_missing_is_telemetry_only():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "watchdog_age": "missing",
        "repair_age": "100",
        "a11y": "ok",
        "autojs6_a11y": "ok",
    }
    issues = fh.evaluate_health(report)
    assert "watchdog_missing" not in issues
    assert "autojs6_a11y_stale" not in issues


def test_evaluate_retired_autojs_a11y_is_telemetry_only():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "watchdog_age": str(fh.WATCHDOG_FRESH_SEC + 1),
        "repair_age": "100",
        "a11y": "down",
        "autojs6_a11y": "missing",
    }
    issues = fh.evaluate_health(report)
    assert "autojs6_a11y_missing" not in issues
    assert "autojs6_a11y_stale" not in issues


def test_evaluate_shell_bootloop_port():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "down",
        "shell5555": "down",
        "watchdog_age": "10",
        "repair_age": "10",
        "port": "CLOSED_NO_SHELL",
        "shizuku": "down",
        "a11y": "ok",
        "autojs6_a11y": "ok",
    }
    issues = fh.evaluate_health(report)
    assert "bootloop_down" in issues
    assert "shell5555_down" in issues
    assert "port_closed" in issues
    assert "shizuku_down" in issues


def test_evaluate_a11y_and_ssh_echo():
    report = {
        "ssh_echo": "fail",
        "sshd": "ok",
        "watchdog_age": "10",
        "repair_age": "10",
        "a11y": "FAILED",
        "autojs6_a11y": "missing",
    }
    issues = fh.evaluate_health(report)
    assert "ssh_echo" in issues
    assert "a11y_failed" in issues
    assert "autojs6_a11y_missing" not in issues


def test_summarize_includes_issues():
    s = fh.summarize({"sshd": "ok", "watchdog_age": "9"}, ["watchdog_stale"])
    assert "issues=watchdog_stale" in s
    assert "sshd=ok" in s


def test_summarize_includes_agent_age():
    s = fh.summarize({"sshd": "ok", "agent_age": "42", "watchdog_age": "9"}, [])
    assert "agent_age=42" in s


def test_evaluate_agent_missing_is_hard_fail_after_cutover():
    # agent_missing/agent_stale gate on agent_heartbeat_age (#86, Shizuku/loopback-independent),
    # not the older agent_age — see AGENT_HEARTBEAT_FRESH_SEC's comment.
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "ok",
        "shell5555": "ok",
        "watchdog_age": "100",
        "repair_age": "200",
        "agent_heartbeat_age": "missing",
        "a11y": "ok",
        "autojs6_a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    assert fh.evaluate_health(report) == ["agent_missing"]


def test_evaluate_agent_stale():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "ok",
        "shell5555": "ok",
        "watchdog_age": "100",
        "repair_age": "200",
        "agent_heartbeat_age": str(fh.AGENT_HEARTBEAT_FRESH_SEC + 50),
        "a11y": "ok",
        "autojs6_a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    issues = fh.evaluate_health(report)
    assert "agent_stale" in issues
    assert "watchdog_stale" not in issues


def test_evaluate_agent_reboot_candidate():
    report = {"agent_heartbeat_age": "10", "agent_reboot_candidate": "yes"}
    assert fh.evaluate_health(report) == ["agent_reboot_candidate"]


def test_evaluate_agent_age_alone_no_longer_drives_staleness():
    # The Shizuku-bound comonitor signal (agent_age) is retained as telemetry only — it must not,
    # by itself, produce agent_stale/agent_missing now that agent_heartbeat_age is authoritative.
    report = {"agent_age": "missing", "agent_heartbeat_age": "5"}
    assert fh.evaluate_health(report) == []


def test_evaluate_tailscale_down():
    report = {"tailscale": "down", "agent_heartbeat_age": "60"}
    assert fh.evaluate_health(report) == ["tailscale_down"]


def test_evaluate_tailscale_policy_down():
    report = {"tailscale_policy": "down", "agent_heartbeat_age": "60"}
    assert fh.evaluate_health(report) == ["tailscale_policy_down"]


def test_evaluate_tailscale_failed_states():
    report = {"tailscale": "FAILED", "tailscale_policy": "FAILED", "agent_heartbeat_age": "60"}
    assert fh.evaluate_health(report) == [
        "tailscale_down",
        "tailscale_policy_down",
    ]


def test_normalize_status_fields_includes_tailscale():
    report = {
        "status_line": (
            "[agent] STATUS port=open shizuku=up a11y=down tailscale=up tailscale_policy=down reason=agent-comonitor"
        )
    }
    fh._normalize_status_fields(report)
    assert report["tailscale"] == "up"
    assert report["tailscale_policy"] == "down"


def test_monitor_notifies_after_debounce(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", True)  # isolate notify test
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:1.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "watchdog_age": "99999",
                "agent_age": "99999",
                "agent_heartbeat_age": "99999",
                "repair_age": "10",
                "a11y": "ok",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
            },
        ),
    )

    class MockResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(fhm.subprocess, "run", lambda *a, **kw: MockResult())
    notifs, logs = [], []
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: notifs.append(a))
    monkeypatch.setattr(fhm, "_fleet_log", lambda _level, message: logs.append(message))

    fhm.check_device("oneui-device", "100.1", "192.1")
    assert not notifs
    assert any("agent_stale" in m for m in logs)
    fhm.check_device("oneui-device", "100.1", "192.1")
    assert len(notifs) == 1 and "agent_stale" in notifs[0][1]


def test_monitor_agent_heal_failure_skips_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    heal_dir = tmp_path / "agent-heal"
    monkeypatch.setattr(fhm, "AGENT_HEAL_STATE_DIR", str(heal_dir))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", False)
    monkeypatch.setattr(fhm, "AGENT_HEAL_AFTER", 1)
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:100.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "watchdog_age": "99999",
                "agent_age": "99999",
                "agent_heartbeat_age": "99999",
                "repair_age": "10",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "a11y": "ok",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
            },
        ),
    )

    def fail_run(args, **kw):
        class R:
            returncode = 1
            stdout = "fail"
            stderr = ""

        return R()

    monkeypatch.setattr(fhm.subprocess, "run", fail_run)
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "_fleet_log", lambda *_: None)
    monkeypatch.setattr(fhm, "REPO", str(tmp_path))
    (tmp_path / "control" / "tools" / "native-agent").mkdir(parents=True)
    (tmp_path / "control" / "tools" / "native-agent" / "start_agent.py").write_text("x")

    fhm.check_device("oneui-device", "100.1", "192.1")
    assert not (heal_dir / "oneui-device").exists()


def test_monitor_skips_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm.fh, "probe_device", lambda *a, **k: (None, {"reachable": "no"}))
    logs = []
    monkeypatch.setattr(fhm, "_fleet_log", lambda _level, message: logs.append(message))
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    fhm.check_device("oneui-device", "100.1", "192.1")
    assert any("unreachable" in m for m in logs)
    assert fhm.read_state(os.path.join(str(tmp_path), "oneui-device")) == 0


def test_soft_health_snapshot_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", True)
    events = []

    def capture(etype, device, **details):
        events.append((etype, device, details))

    monkeypatch.setattr(fhm, "_stats_event", capture)
    monkeypatch.setattr(fhm, "_fleet_log", lambda *_: None)
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "_scrape_device_errors", lambda *a, **k: None)
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:1.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "watchdog_age": "100",
                "repair_age": "50",
                "agent_age": "42",
                "agent_heartbeat_age": "42",
                "a11y": "up",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
            },
        ),
    )
    fhm.check_device("p7a", "100.1", "192.1")
    soft = [e for e in events if e[0] == "soft_health"]
    assert len(soft) == 1
    assert soft[0][1] == "p7a"
    assert soft[0][2]["agent_age"] == 42
    assert soft[0][2]["issues"] == "none"


def test_monitor_heals_stale_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm, "AGENT_HEAL_STATE_DIR", str(tmp_path / "agent-heal"))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", False)
    monkeypatch.setattr(fhm, "AGENT_HEAL_AFTER", 2)
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:1.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "watchdog_age": "10",
                "repair_age": "10",
                "agent_age": "99999",
                "agent_heartbeat_age": "99999",
                "a11y": "ok",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
            },
        ),
    )
    calls = []

    def fake_run(args, **kw):
        calls.append(args)

        class R:
            returncode = 0
            stdout = "Starting native-agent\n"
            stderr = ""

        return R()

    monkeypatch.setattr(fhm.subprocess, "run", fake_run)
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "_fleet_log", lambda *_: None)
    monkeypatch.setattr(fhm, "REPO", str(tmp_path))
    (tmp_path / "control" / "tools" / "native-agent").mkdir(parents=True)
    (tmp_path / "control" / "tools" / "native-agent" / "start_agent.py").write_text("x")

    fhm.check_device("oneui-device", "100.1", "192.1")
    assert not any(any("start_agent.py" in str(part) for part in call) for call in calls)
    fhm.check_device("oneui-device", "100.1", "192.1")
    agent_calls = [call for call in calls if any("start_agent.py" in str(part) for part in call)]
    assert len(agent_calls) == 1


# ── device_log_failure (central-logging gap, 2026-07-31) ───────────────────


def test_devlog_severity_watchdog_reads_explicit_token():
    assert (
        fhm._devlog_severity(
            "watchdog.log",
            "2026-07-31 17:42:21 [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)",
        )
        == "ERR"
    )
    assert (
        fhm._devlog_severity(
            "watchdog.log",
            "2026-07-31 17:42:21 [repair] WARNING: wireless debugging re-enable FAILED",
        )
        == "WARNING"
    )
    assert fhm._devlog_severity("watchdog.log", "2026-07-31 17:42:21 [repair] NOTICE: Tailscale restored") is None


def test_devlog_severity_agent_log_is_always_err():
    # agent.log lines only reach us after HEALTH_GATHER's FAILED/error=/still-down
    # grep already filtered out anything that isn't a failure.
    assert fhm._devlog_severity("agent.log", "2026-07-31 [agent] catastrophic FAILED steps=x") == "ERR"


def test_report_device_log_failures_dedups_by_epoch(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "DEVLOG_STATE_DIR", str(tmp_path / "device-log-failure"))
    events = []
    monkeypatch.setattr(fhm, "_stats_event", lambda etype, device, **d: events.append((etype, device, d)))

    report = {
        "_devlog": [
            {
                "source": "watchdog.log",
                "line": "2026-07-31 17:42:21 [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)",
            },
        ]
    }
    fhm._report_device_log_failures("hd8", report)
    assert len(events) == 1
    assert events[0][0] == "device_log_failure"
    assert events[0][1] == "hd8"
    assert events[0][2]["source"] == "watchdog.log"
    assert events[0][2]["severity"] == "ERR"
    assert "Tailscale repair FAILED" in events[0][2]["message"]

    # Same line again (e.g. still within HEALTH_GATHER's tail -20 window on the
    # next cycle) must NOT be re-reported — epoch dedup.
    fhm._report_device_log_failures("hd8", report)
    assert len(events) == 1

    # A genuinely NEW, later timestamped line for the same persistent failure
    # (stayturgid_repair.py re-logs a fresh ERR every cycle it's still down)
    # must be reported — this is the "re-notify while unresolved" path.
    report2 = {
        "_devlog": [
            {
                "source": "watchdog.log",
                "line": "2026-07-31 17:47:21 [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)",
            },
        ]
    }
    fhm._report_device_log_failures("hd8", report2)
    assert len(events) == 2


def test_report_device_log_failures_ignores_non_failure_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "DEVLOG_STATE_DIR", str(tmp_path / "device-log-failure"))
    events = []
    monkeypatch.setattr(fhm, "_stats_event", lambda etype, device, **d: events.append((etype, device, d)))
    report = {
        "_devlog": [
            {"source": "watchdog.log", "line": "2026-07-31 17:42:21 [repair] NOTICE: Tailscale restored"},
        ]
    }
    fhm._report_device_log_failures("hd8", report)
    assert events == []


def test_report_device_log_failures_noop_without_devlog():
    # No "_devlog" key at all (e.g. a healthy probe with nothing to report) —
    # must not raise or touch state.
    fhm._report_device_log_failures("hd8", {})


def test_check_device_forwards_devlog_to_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fhm, "DEVLOG_STATE_DIR", str(tmp_path / "device-log-failure"))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", True)
    monkeypatch.setattr(fhm, "_scrape_device_errors", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "_fleet_log", lambda *_: None)
    events = []
    monkeypatch.setattr(fhm, "_stats_event", lambda etype, device, **d: events.append((etype, device, d)))
    monkeypatch.setattr(
        fhm.fh,
        "probe_device",
        lambda name, ts, lan: (
            "adb:1.1.1.1:5555",
            {
                "ssh_echo": "ok",
                "sshd": "ok",
                "bootloop": "ok",
                "shell5555": "ok",
                "watchdog_age": "10",
                "repair_age": "10",
                "agent_heartbeat_age": "10",
                "a11y": "ok",
                "autojs6_a11y": "ok",
                "port": "open",
                "shizuku": "up",
                "_devlog": [
                    {
                        "source": "watchdog.log",
                        "line": "2026-07-31 17:42:21 [repair] ERR: Tailscale repair FAILED (runtime=down)",
                    }
                ],
            },
        ),
    )
    fhm.check_device("p7a", "100.1", "192.1")
    devlog_events = [e for e in events if e[0] == "device_log_failure"]
    assert len(devlog_events) == 1
    assert devlog_events[0][1] == "p7a"
    assert devlog_events[0][2]["severity"] == "ERR"


def test_repair_heal_pkill_cannot_match_its_own_remote_shell():
    # `pkill -f stayturgid_repair` inside `ssh host "<cmd>"` matched the remote
    # shell's own command line and killed the session (rc=255) before nohup
    # ran — t2e's boot loop stayed dead 2026-09-27..29.
    import re

    cmd = fhm.REPAIR_HEAL_REMOTE_CMD
    for pattern in re.findall(r"pkill -f '([^']+)'", cmd):
        assert re.search(pattern, cmd) is None, pattern
    assert "pkill -f stayturgid_repair " not in cmd
    assert "setsid nohup" in cmd and "~/.termux/boot/" in cmd


def test_repair_heal_rc255_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", False)
    monkeypatch.setattr(fhm, "REPAIR_HEAL_STATE_DIR", str(tmp_path / "repair-heal"))
    monkeypatch.setattr(fhm, "notify", lambda *a, **k: None)
    monkeypatch.setattr(fhm, "_fleet_log", lambda *a, **k: None)
    calls = []

    class Result:
        returncode = 255
        stdout = ""
        stderr = "Connection closed"

    def fake_run(argv, **kw):
        calls.append(argv)
        return Result()

    monkeypatch.setattr(fhm.subprocess, "run", fake_run)
    fhm.maybe_heal_repair_stale("t2e", ["repair_stale"], fhm.REPAIR_HEAL_AFTER, adb_serial="100.73.253.10:5555")
    assert any("cmd package unstop com.termux.boot" in " ".join(c) for c in calls)
    # Failure must not start the cooldown, so the next run retries.
    assert fhm._heal_repair_cooldown_ok("t2e")


def test_health_gather_emits_tasker_recover_age():
    import inspect

    assert "tasker_recover_age=" in fh.HEALTH_GATHER
    assert "net.dinglisch.android.taskerm" in fh.HEALTH_GATHER
    assert "tasker-sshd-recover.ts" in fh.HEALTH_GATHER
    # adb shell cannot read Termux's home: an absent field must mean unknown.
    assert "tasker_recover_age" not in inspect.getsource(fh.adb_health)


def test_tasker_recover_stale_missing():
    assert fh.tasker_recover_stale({"tasker_recover_age": "missing"}) is True


def test_tasker_recover_stale_fresh():
    assert fh.tasker_recover_stale({"tasker_recover_age": "60"}) is False
    assert fh.tasker_recover_stale({"tasker_recover_age": str(fh.TASKER_RECOVER_FRESH_SEC)}) is False


def test_tasker_recover_stale_stale():
    assert fh.tasker_recover_stale({"tasker_recover_age": str(fh.TASKER_RECOVER_FRESH_SEC + 1)}) is True


def test_tasker_recover_stale_unknown_never_nags():
    assert fh.tasker_recover_stale({"tasker_recover_age": "notasker"}) is False
    assert fh.tasker_recover_stale({}) is False
    assert fh.tasker_recover_stale({"tasker_recover_age": ""}) is False
    assert fh.tasker_recover_stale({"tasker_recover_age": "unknown"}) is False
    assert fh.tasker_recover_stale({"tasker_recover_age": "garbage"}) is False


def test_evaluate_tasker_recover_is_advisory_only():
    base = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "ok",
        "shell5555": "ok",
        "repair_age": "200",
        "agent_heartbeat_age": "60",
        "a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    for value in ("missing", str(fh.TASKER_RECOVER_FRESH_SEC + 1)):
        report = dict(base, tasker_recover_age=value)
        assert fh.tasker_recover_stale(report)
        assert fh.evaluate_health(report) == []


def test_summarize_includes_tasker_recover_age():
    s = fh.summarize({"tasker_recover_age": "missing"}, [])
    assert "tasker_recover_age=missing" in s


def test_summarize_includes_tasker_result_and_monitor():
    s = fh.summarize({"tasker_recover_result": "failed", "tasker_monitor": "stopped"}, [])
    assert "tasker_recover_result=failed" in s
    assert "tasker_monitor=stopped" in s


def test_health_gather_includes_tasker_body():
    import inspect

    assert fh._TASKER_BODY in fh.HEALTH_GATHER
    assert "tasker-sshd-recover.result" in fh._TASKER_BODY
    assert "dumpsys activity services net.dinglisch.android.taskerm" in fh._TASKER_BODY
    assert "tasker_recover_result" not in inspect.getsource(fh.adb_health)


_TASKER_PKG = "package:/data/app/~~x/net.dinglisch.android.taskerm-1/base.apk\r\n"
_DUMP_RUNNING = (
    "ACTIVITY MANAGER SERVICES (dumpsys activity services)\r\n"
    "  User 0 active services:\r\n"
    "  * ServiceRecord{2f3a1b u0 net.dinglisch.android.taskerm/.MonitorService}\r\n"
)
_DUMP_ONLY_A11Y = (
    "ACTIVITY MANAGER SERVICES (dumpsys activity services)\r\n"
    "  * ServiceRecord{9c u0 net.dinglisch.android.taskerm/.MyAccessibilityService}\r\n"
)
_DUMP_NOTHING = "ACTIVITY MANAGER SERVICES (dumpsys activity services)\r\n  (nothing)\r\n"


def _run_tasker_body(tmp_path, *, pkg: str = "", dump: str = "", marker=None, result=None) -> dict[str, str]:
    """Run _TASKER_BODY under bash against a temp HOME with stubbed adb/pm."""
    import subprocess

    home = tmp_path / "home"
    state = home / ".stayturgid" / "state"
    state.mkdir(parents=True)
    if marker is not None:
        (state / "tasker-sshd-recover.ts").write_text(marker)
    if result is not None:
        (state / "tasker-sshd-recover.result").write_text(result)
    (tmp_path / "pkg.txt").write_text(pkg)
    (tmp_path / "dump.txt").write_text(dump)
    # Shell functions, not PATH shims: see _run_fleet_profile_body.
    stubs = 'adb() { case "$*" in *"pm path"*) cat "%s" ;; *dumpsys*) cat "%s" ;; esac; }\npm() { :; }\n' % (
        tmp_path / "pkg.txt",
        tmp_path / "dump.txt",
    )
    env = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
    env["HOME"] = str(home)
    r = subprocess.run(["bash", "-c", stubs + fh._TASKER_BODY], capture_output=True, text=True, env=env, timeout=10)
    assert r.returncode == 0, r.stderr
    return fh.parse_kv(r.stdout)


def test_tasker_body_without_tasker(tmp_path):
    out = _run_tasker_body(tmp_path)
    assert out == {
        "tasker_recover_age": "notasker",
        "tasker_recover_result": "missing",
        "tasker_monitor": "notasker",
    }


def test_tasker_body_reads_marker_line1_and_ok_result(tmp_path):
    now = int(datetime.datetime.now().timestamp())
    out = _run_tasker_body(
        tmp_path,
        pkg=_TASKER_PKG,
        dump=_DUMP_RUNNING,
        marker="%d\n" % (now - 100),
        result="end=%d\nexit=0\nstep.10-sshd=0\nsv_sshd=run: sshd: (pid 1) 5s\ntty=not a tty\n" % now,
    )
    assert 95 <= int(out["tasker_recover_age"]) <= 160
    assert out["tasker_recover_result"] == "ok"
    assert out["tasker_monitor"] == "running"


def test_tasker_body_failed_result(tmp_path):
    out = _run_tasker_body(tmp_path, pkg=_TASKER_PKG, result="end=1\nexit=1\nstep.10-sshd=1\n")
    assert out["tasker_recover_result"] == "failed"


def test_tasker_body_unparseable_result_is_missing(tmp_path):
    out = _run_tasker_body(tmp_path, pkg=_TASKER_PKG, result="garbage\nexit=\n")
    assert out["tasker_recover_result"] == "missing"


def test_tasker_body_monitor_stopped(tmp_path):
    for dump in (_DUMP_NOTHING, _DUMP_ONLY_A11Y):
        assert _run_tasker_body(tmp_path / str(len(dump)), pkg=_TASKER_PKG, dump=dump)["tasker_monitor"] == "stopped"


def test_tasker_body_monitor_unknown_without_a_dump(tmp_path):
    assert _run_tasker_body(tmp_path, pkg=_TASKER_PKG, dump="")["tasker_monitor"] == "unknown"


def test_tasker_result_and_monitor_are_advisory_only():
    base = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "bootloop": "ok",
        "shell5555": "ok",
        "repair_age": "200",
        "agent_heartbeat_age": "60",
        "a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    report = dict(base, tasker_recover_result="failed", tasker_monitor="stopped")
    assert fh.tasker_recover_failed(report)
    assert fh.tasker_monitor_stopped(report)
    assert fh.evaluate_health(report) == []


def test_tasker_failed_and_stopped_unknown_never_nag():
    for value in ("ok", "missing", "", None):
        assert not fh.tasker_recover_failed({"tasker_recover_result": value})
    for value in ("running", "unknown", "notasker", "", None):
        assert not fh.tasker_monitor_stopped({"tasker_monitor": value})


# ── Tasker SSHD_RECOVER broadcast during a real outage (SSHD-RUNNING) ──────

_ADB_FALLBACK_REPORT = {
    "ssh_echo": "skip",
    "sshd": "unknown",
    "bootloop": "unknown",
    "shell5555": "skip",
    "repair_age": "10",
    "agent_heartbeat_age": "60",
}


def _sshd_heal_env(tmp_path, monkeypatch, path: str, report: dict):
    import adb_cli

    monkeypatch.setattr(fhm, "STATE_DIR", str(tmp_path / "fleet-health"))
    monkeypatch.setattr(fhm, "SSHD_RECOVER_HEAL_STATE_DIR", str(tmp_path / "sshd-recover-heal"))
    monkeypatch.setattr(fhm, "TASKER_RECOVER_PROBE_STATE_DIR", str(tmp_path / "probe"))
    monkeypatch.setattr(fhm, "TASKER_RECOVER_NAG_STATE_DIR", str(tmp_path / "nag"))
    monkeypatch.setattr(fhm, "TASKER_RESULT_NAG_STATE_DIR", str(tmp_path / "result-nag"))
    monkeypatch.setattr(fhm, "TASKER_MONITOR_NAG_STATE_DIR", str(tmp_path / "monitor-nag"))
    monkeypatch.setattr(fhm, "SKIP_HEALTH", False)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", False)
    monkeypatch.setattr(fhm.fh, "probe_device", lambda name, ts, lan: (path, dict(report)))
    monkeypatch.setattr(fhm.dev, "resolve_adb", lambda name: None)
    for fn in ("_scrape_device_errors", "maybe_heal_repair_stale", "maybe_heal_agent", "notify"):
        monkeypatch.setattr(fhm, fn, lambda *a, **k: None)
    logs: list[str] = []
    monkeypatch.setattr(fhm, "_fleet_log", lambda _level, message: logs.append(message))
    monkeypatch.setattr(fhm, "_stats_event", lambda *a, **k: None)
    calls: list[tuple] = []

    class R:
        returncode = 0
        stdout = "Broadcast completed: result=0"
        stderr = ""

    def fake_adb(serial, *args, **kwargs):
        calls.append((serial, args))
        return R()

    monkeypatch.setattr(adb_cli, "adb", fake_adb)
    return calls, logs


_BROADCAST = ("shell", "am", "broadcast", "-a", "com.stayturgid.SSHD_RECOVER")


def test_ssh_down_adb_up_fires_sshd_recover_broadcast(tmp_path, monkeypatch):
    calls, logs = _sshd_heal_env(tmp_path, monkeypatch, "adb:1.1.1.1:5555", _ADB_FALLBACK_REPORT)
    fhm.check_device("p7a", "100.1", "192.1")
    assert calls == [("1.1.1.1:5555", _BROADCAST)]
    assert any("sshd-recover broadcast" in m and "rc=0" in m for m in logs)


def test_sshd_recover_broadcast_cooldown(tmp_path, monkeypatch):
    calls, logs = _sshd_heal_env(tmp_path, monkeypatch, "adb:1.1.1.1:5555", _ADB_FALLBACK_REPORT)
    fhm.check_device("p7a", "100.1", "192.1")
    fhm.check_device("p7a", "100.1", "192.1")
    assert len(calls) == 1
    assert any("cooldown" in m for m in logs)
    stamp = tmp_path / "sshd-recover-heal" / "p7a"
    old = datetime.datetime.now().timestamp() - fhm.SSHD_RECOVER_HEAL_COOLDOWN_SEC - 1
    os.utime(stamp, (old, old))
    fhm.check_device("p7a", "100.1", "192.1")
    assert len(calls) == 2


def test_sshd_down_over_ssh_fires_broadcast(tmp_path, monkeypatch):
    report = dict(_ADB_FALLBACK_REPORT, ssh_echo="ok", sshd="down")
    calls, _ = _sshd_heal_env(tmp_path, monkeypatch, "adb:1.1.1.1:5555", report)
    fhm.check_device("p7a", "100.1", "192.1")
    assert calls == [("1.1.1.1:5555", _BROADCAST)]


def test_healthy_ssh_over_adb_path_does_not_broadcast(tmp_path, monkeypatch):
    # resolve_path prefers adb, so an adb: path alone does not mean SSH failed.
    report = dict(_ADB_FALLBACK_REPORT, ssh_echo="ok", sshd="ok")
    calls, _ = _sshd_heal_env(tmp_path, monkeypatch, "adb:1.1.1.1:5555", report)
    fhm.check_device("p7a", "100.1", "192.1")
    assert calls == []


def test_sshd_recover_broadcast_honours_skip_watchdog_heal(tmp_path, monkeypatch):
    calls, _ = _sshd_heal_env(tmp_path, monkeypatch, "adb:1.1.1.1:5555", _ADB_FALLBACK_REPORT)
    monkeypatch.setattr(fhm, "SKIP_WATCHDOG_HEAL", True)
    fhm.check_device("p7a", "100.1", "192.1")
    assert calls == []


def test_sshd_recover_broadcast_error_never_raises(tmp_path, monkeypatch):
    import adb_cli

    _, logs = _sshd_heal_env(tmp_path, monkeypatch, "adb:1.1.1.1:5555", _ADB_FALLBACK_REPORT)

    def boom(*a, **k):
        raise OSError("adb missing")

    monkeypatch.setattr(adb_cli, "adb", boom)
    fhm.check_device("p7a", "100.1", "192.1")
    assert any("sshd-recover broadcast error" in m for m in logs)


def test_monitor_declares_it_heals_sshd_running():
    head = (REPO / "control" / "bin" / "fleet_health_monitor.py").read_text().splitlines()[:5]
    assert any(line.startswith("# @heals:") and "SSHD-RUNNING" in line for line in head)


def _run_fleet_profile_body(tmp_path, adb_stdout: str) -> dict[str, str]:
    """Run _FLEET_PROFILE_BODY under bash with a fake adb that prints *adb_stdout*."""
    import subprocess

    (tmp_path / "out.txt").write_text(adb_stdout)
    # A shell function, not a PATH shim: a BASH_ENV that rebuilds PATH would
    # otherwise put the real adb first and reach for a device.
    script = "adb() { cat '%s'; }\n%s" % (tmp_path / "out.txt", fh._FLEET_PROFILE_BODY)
    env = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10)
    assert r.returncode == 0, r.stderr
    return fh.parse_kv(r.stdout)


def _apply_record(ts: int, success: bool, errors: str = "[]") -> str:
    return (
        '{"schema":1,"ts":%d,"success":%s,"applied":5,"skipped":0,"errors":%s,'
        '"message":"Applied 5 preferences, skipped 0","profile_sha256":null,'
        '"source":"path","app_version":"13.6.0"}\r\n' % (ts, "true" if success else "false", errors)
    )


def test_health_gather_includes_fleet_profile_probe():
    assert fh._FLEET_PROFILE_BODY in fh.HEALTH_GATHER
    assert "files/fleet/last-apply.json" in fh.HEALTH_GATHER
    assert "adb -s localhost:5555 shell" in fh._FLEET_PROFILE_BODY


def test_fleet_profile_body_ok(tmp_path):
    ts = int(datetime.datetime.now().timestamp()) - 120
    out = _run_fleet_profile_body(tmp_path, _apply_record(ts, True))
    assert out["fleet_profile"] == "ok"
    assert 115 <= int(out["fleet_profile_age"]) <= 180


def test_fleet_profile_body_failed(tmp_path):
    out = _run_fleet_profile_body(tmp_path, _apply_record(1, False, '["Path not allowed"]'))
    assert out["fleet_profile"] == "failed"
    assert int(out["fleet_profile_age"]) > 0


def test_fleet_profile_body_missing(tmp_path):
    out = _run_fleet_profile_body(tmp_path, "")
    assert out == {"fleet_profile": "missing", "fleet_profile_age": "missing"}


def test_fleet_profile_body_escaped_error_text_cannot_flip_the_verdict(tmp_path):
    # An unknown profile key is echoed into errors; org.json escapes its quotes.
    errors = r'["Unknown key: \"success\":true,\"ts\":9"]'
    out = _run_fleet_profile_body(tmp_path, _apply_record(5, False, errors))
    assert out["fleet_profile"] == "failed"
    assert int(out["fleet_profile_age"]) > 1_000_000


def test_evaluate_fleet_profile_failed_is_an_issue():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "repair_age": "200",
        "agent_heartbeat_age": "60",
        "a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    assert fh.evaluate_health(dict(report, fleet_profile="failed")) == ["fleet_profile_failed"]
    # Older app builds write no record: missing must never be an issue.
    for value in ("ok", "missing", None):
        r = dict(report) if value is None else dict(report, fleet_profile=value, fleet_profile_age="missing")
        assert fh.evaluate_health(r) == []


def test_summarize_includes_fleet_profile():
    s = fh.summarize({"fleet_profile": "failed", "fleet_profile_age": "42"}, ["fleet_profile_failed"])
    assert "fleet_profile=failed" in s
    assert "fleet_profile_age=42" in s
    assert "issues=fleet_profile_failed" in s


def _run_shizuku_stale_body(tmp_path, adb_stdout: str, fire: str = "") -> tuple[dict[str, str], str]:
    """Run _SHIZUKU_STALE_BODY under bash; the fake adb records the command it was handed."""
    import subprocess

    (tmp_path / "out.txt").write_text(adb_stdout)
    argv = tmp_path / "argv.txt"
    script = "FIRE=%s\nadb() { printf '%%s' \"$4\" > '%s'; cat '%s'; }\n%s" % (
        fire,
        argv,
        tmp_path / "out.txt",
        fh._SHIZUKU_STALE_BODY,
    )
    env = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10)
    assert r.returncode == 0, r.stderr
    return fh.parse_kv(r.stdout), (argv.read_text() if argv.exists() else "")


def _staleness_module():
    import importlib.util

    path = REPO / "ansible_collections/stayturgid/android_common/plugins/module_utils/shizuku_staleness.py"
    spec = importlib.util.spec_from_file_location("shizuku_staleness_t", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_health_gather_includes_shizuku_stale_probe():
    import subprocess

    assert fh._SHIZUKU_STALE_BODY in fh.HEALTH_GATHER
    assert _staleness_module().staleness_probe() in fh._SHIZUKU_STALE_BODY
    # The probe is spliced into single quotes; a stray quote would break the whole gather.
    r = subprocess.run(["bash", "-n"], input=fh.HEALTH_GATHER, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr


def test_shizuku_stale_body_passes_the_probe_through_intact(tmp_path):
    out, argv = _run_shizuku_stale_body(
        tmp_path, "shizuku_server_start=996000\r\nshizuku_pkg_update=998000\r\nshizuku_server_stale=yes\r\n"
    )
    assert argv == _staleness_module().staleness_probe()
    assert out == {
        "shizuku_server_start": "996000",
        "shizuku_pkg_update": "998000",
        "shizuku_server_stale": "yes",
    }


@pytest.mark.parametrize(
    "adb_stdout,verdict",
    [
        ("shizuku_server_stale=no\n", "no"),
        ("shizuku_server_stale=unknown\n", "unknown"),
        ("", "unknown"),
        ("error: device offline\n", "unknown"),
    ],
)
def test_shizuku_stale_body_verdicts(tmp_path, adb_stdout, verdict):
    assert _run_shizuku_stale_body(tmp_path, adb_stdout)[0]["shizuku_server_stale"] == verdict


def test_shizuku_stale_body_skips_hosts_without_a_local_shell(tmp_path):
    out, argv = _run_shizuku_stale_body(tmp_path, "shizuku_server_stale=yes\n", fire="1")
    assert out == {"shizuku_server_stale": "unknown"}
    assert argv == ""


def test_evaluate_shizuku_server_stale_only_on_explicit_yes():
    report = {
        "ssh_echo": "ok",
        "sshd": "ok",
        "repair_age": "200",
        "agent_heartbeat_age": "60",
        "a11y": "ok",
        "port": "open",
        "shizuku": "up",
    }
    assert fh.evaluate_health(dict(report, shizuku_server_stale="yes")) == ["shizuku_server_stale"]
    for value in ("no", "unknown", None):
        r = dict(report) if value is None else dict(report, shizuku_server_stale=value)
        assert fh.evaluate_health(r) == []


def test_summarize_includes_shizuku_server_stale():
    assert "shizuku_server_stale=yes" in fh.summarize({"shizuku_server_stale": "yes"}, ["shizuku_server_stale"])
    assert "shizuku_server_stale=?" in fh.summarize({}, [])


def test_soft_health_snapshot_carries_shizuku_server_stale(monkeypatch):
    events = []
    monkeypatch.setattr(fhm, "_stats_event", lambda etype, device, **d: events.append((etype, device, d)))
    fhm._record_soft_health_snapshot("p7a", "ssh", {"shizuku_server_stale": "yes"}, ["shizuku_server_stale"])
    fhm._record_soft_health_snapshot("p7a", "adb:x", {}, [])
    assert events[0][2]["shizuku_server_stale"] == "yes"
    assert events[1][2]["shizuku_server_stale"] == "unknown"


def test_soft_health_snapshot_carries_fleet_profile(monkeypatch):
    events = []
    monkeypatch.setattr(fhm, "_stats_event", lambda etype, device, **d: events.append((etype, device, d)))
    fhm._record_soft_health_snapshot("p7a", "ssh", {"fleet_profile": "ok", "fleet_profile_age": "300"}, [])
    fhm._record_soft_health_snapshot("p7a", "adb:x", {}, [])
    assert events[0][2]["fleet_profile"] == "ok"
    assert events[0][2]["fleet_profile_age"] == 300
    # The adb fallback probe never gathers it: unknown, not missing.
    assert events[1][2]["fleet_profile"] == "unknown"
    assert events[1][2]["fleet_profile_age"] == "unknown"


# --- unanswered Shizuku ADB authorisation dialog ---

_HEALTHY = {
    "ssh_echo": "ok",
    "sshd": "ok",
    "bootloop": "ok",
    "shell5555": "ok",
    "repair_age": "200",
    "agent_heartbeat_age": "60",
    "a11y": "ok",
    "port": "open",
    "shizuku": "up",
}


def test_shizuku_auth_unanswered_is_a_finding_with_a_hint():
    issues = fh.evaluate_health(dict(_HEALTHY, shizuku_auth="unanswered"))
    assert issues == ["shizuku_auth_unanswered"]
    hint = fh.ISSUE_HINTS["shizuku_auth_unanswered"]
    assert "\n" not in hint and "Attempt now" in hint


@pytest.mark.parametrize("value", ["ok", "unknown", "skip"])
def test_shizuku_auth_other_values_are_not_findings(value):
    assert fh.evaluate_health(dict(_HEALTHY, shizuku_auth=value)) == []


def test_shizuku_auth_absent_is_backward_compatible():
    assert fh.evaluate_health(dict(_HEALTHY)) == []
    assert "shizuku_auth=?" in fh.summarize(dict(_HEALTHY), [])


def test_status_line_shizuku_auth_is_normalized():
    report = {"status_line": "[repair] STATUS port=open shizuku=down env=ok shizuku_auth=unanswered"}
    fh._normalize_status_fields(report)
    assert report["shizuku_auth"] == "unanswered"
    old = {"status_line": "[repair] STATUS port=open shizuku=up env=ok"}
    fh._normalize_status_fields(old)
    assert "shizuku_auth" not in old


def test_health_gather_reads_shizuku_auth_from_repair_status():
    assert "shizuku_auth=" in fh.HEALTH_GATHER
    assert "shizuku_auth=unknown" in fh.HEALTH_GATHER


def test_monitor_logs_issue_hint_once_per_change(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(fhm, "_fleet_log", lambda level, message: logs.append((level, message)))
    state = str(tmp_path / "host.hints")
    fhm.log_issue_hints("p7a", ["shizuku_auth_unanswered", "shizuku_down"], state)
    fhm.log_issue_hints("p7a", ["shizuku_auth_unanswered"], state)
    assert logs == [(fhm.WARNING, "p7a shizuku_auth_unanswered: " + fh.ISSUE_HINTS["shizuku_auth_unanswered"])]
    fhm.log_issue_hints("p7a", [], state)
    assert logs[-1] == (fhm.NOTICE, "p7a shizuku_auth_unanswered cleared")
    fhm.log_issue_hints("p7a", [], state)
    assert len(logs) == 2
