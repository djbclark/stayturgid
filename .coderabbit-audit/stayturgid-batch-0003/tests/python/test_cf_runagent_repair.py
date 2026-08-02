"""Regression tests for the Tier 3a CFEngine cf-runagent fallback.

Guards the two bugs that made the original fallback a no-op against a real
cf-runagent (CFEngine Core 3.28.0):

  1. `--protocol-version` is not a cf-runagent flag (it exits rc=1). The wire
     protocol is pinned in the config body instead, so it must never appear on
     the command line.
  2. A bare trailing host arg is parsed as an input FILE (overriding -f), not a
     host — the target must be passed via -H/--hail.

Also checks the cooldown stamp is written on the missing-config early-return so
an unprovisioned Mac does not re-probe port 5308 every health cycle.
"""

from __future__ import annotations

import os
import socket

import fleet_health_monitor as monitor


def test_cf_runagent_cmd_targets_host_with_hail() -> None:
    cmd = monitor._cf_runagent_cmd("/opt/homebrew/bin/cf-runagent", "/cfg/cf-runagent.cf", "100.64.0.9")

    # No invalid protocol flag (protocol_version is pinned in the config body).
    assert "--protocol-version" not in cmd
    # Host is hailed via -H, immediately followed by the IP.
    assert "-H" in cmd
    assert cmd[cmd.index("-H") + 1] == "100.64.0.9"
    # The IP must not appear as a bare trailing positional (that would be parsed
    # as an input FILE and override -f).
    assert cmd[-1] != "100.64.0.9"
    assert cmd[-2:] == ["--remote-bundles", "stayturgid_heal"]
    # Config is passed with -f.
    assert cmd[cmd.index("-f") + 1] == "/cfg/cf-runagent.cf"


def _stub_reachable(monkeypatch) -> None:
    """Make the port-5308 TCP probe always succeed."""

    class _Sock:
        def close(self) -> None:  # noqa: D401
            pass

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _Sock())


def test_missing_config_still_writes_cooldown_stamp(monkeypatch, tmp_path) -> None:
    """A Mac without a rendered cf-runagent.cf must not re-probe every cycle."""
    root = tmp_path
    (root / "state").mkdir()
    monkeypatch.setattr(monitor, "ROOT", str(root))
    _stub_reachable(monkeypatch)
    # cf_config path will not exist under tmp_path -> missing-config branch.

    def _boom(*_a, **_k):  # subprocess must NOT run when config is missing
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(monitor.subprocess, "run", _boom)

    monitor._try_cf_runagent_repair("hd8", "100.64.0.9")

    stamp = root / "state" / "cfengine-heal-fallback-hd8"
    assert stamp.exists(), "cooldown stamp must be written even on missing-config early return"


def test_cooldown_suppresses_second_attempt(monkeypatch, tmp_path) -> None:
    root = tmp_path
    (root / "state").mkdir()
    monkeypatch.setattr(monitor, "ROOT", str(root))
    _stub_reachable(monkeypatch)

    # Pre-write a fresh stamp -> within cooldown window.
    stamp = root / "state" / "cfengine-heal-fallback-hd8"
    stamp.write_text("0")
    os.utime(stamp, None)

    calls = []
    monkeypatch.setattr(monitor.subprocess, "run", lambda *a, **k: calls.append(a))

    monitor._try_cf_runagent_repair("hd8", "100.64.0.9")
    assert calls == [], "attempt within cooldown window must be suppressed"


def test_no_ts_ip_is_noop(monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise AssertionError("should not probe without a ts_ip")

    monkeypatch.setattr(socket, "create_connection", _boom)
    monitor._try_cf_runagent_repair("hd8", "")
