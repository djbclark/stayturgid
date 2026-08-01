"""Tests for Termux repair's control-ET SSH config self-heal."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "device" / "termux" / "py" / "stayturgid_repair.py"
SPEC = importlib.util.spec_from_file_location("stayturgid_repair", MODULE_PATH)
assert SPEC and SPEC.loader
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


def _setup_repair_tree(tmp_path, monkeypatch, config_text):
    home = tmp_path / "home"
    stg = home / ".stayturgid"
    share = stg / "share"
    share.mkdir(parents=True)
    (share / "ssh-config-control-et").write_text(
        "Host mac\n    HostName 100.0.0.1\n    IdentityFile ~/.ssh/id_ed25519_fleet\n    IdentitiesOnly yes\n",
        encoding="utf-8",
    )
    conf = home / ".ssh" / "config"
    conf.parent.mkdir(parents=True)
    conf.write_text(config_text, encoding="utf-8")
    monkeypatch.setattr(repair, "HOME", str(home))
    monkeypatch.setattr(repair, "STG", str(stg))
    monkeypatch.setattr(repair, "log", lambda *_args, **_kwargs: None)
    return conf


def test_repair_removes_legacy_block_but_preserves_managed_config(tmp_path, monkeypatch):
    conf = _setup_repair_tree(
        tmp_path,
        monkeypatch,
        "# MacBook Air via Tailscale\n"
        "Host mac\n"
        "    HostName old.example\n"
        "    IdentityFile ~/.ssh/id_old\n"
        "    IdentitiesOnly yes\n"
        "# BEGIN STAYTURGID-CONTROL-ET\n"
        "Host mac\n    IdentityFile ~/.ssh/id_ed25519_fleet\n"
        "# END STAYTURGID-CONTROL-ET\n"
        "Host unrelated\n    User preserve\n",
    )

    assert repair.ensure_control_et_ssh_config() == "repaired"
    text = conf.read_text(encoding="utf-8")
    assert "MacBook Air via Tailscale" not in text
    assert "id_old" not in text
    assert "STAYTURGID-CONTROL-ET" in text
    assert "User preserve" in text


def test_repair_cleans_legacy_block_before_restoring_marked_block(tmp_path, monkeypatch):
    conf = _setup_repair_tree(
        tmp_path,
        monkeypatch,
        "# MacBook Air via Tailscale\n"
        "Host mac\n"
        "    HostName old.example\n"
        "    IdentityFile ~/.ssh/id_old\n"
        "    IdentitiesOnly yes\n",
    )

    assert repair.ensure_control_et_ssh_config() == "repaired"
    text = conf.read_text(encoding="utf-8")
    assert "MacBook Air via Tailscale" not in text
    assert "id_old" not in text
    assert "STAYTURGID-CONTROL-ET" in text
    assert "id_ed25519_fleet" in text


def _setup_tailscale(monkeypatch):
    commands = []
    monkeypatch.setattr(repair, "read_device_profile", lambda: {})
    monkeypatch.setattr(repair, "_tailscale_installed", lambda _have_sh=False: True)
    monkeypatch.setattr(
        repair,
        "_device_command",
        lambda args, have_sh=False, timeout=15: commands.append((args, have_sh)) or (0, ""),
    )
    monkeypatch.setattr(repair, "log", lambda *_args, **_kwargs: None)
    return commands


def test_tailscale_healthy_still_enforces_policy(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: True)

    assert repair.ensure_tailscale(have_sh=True) == "up"
    assert [command[:5] for command, _have_sh in commands] == [
        ["settings", "put", "secure", "always_on_vpn_app", repair.TAILSCALE_PACKAGE],
        ["settings", "put", "secure", "always_on_vpn_lockdown", "0"],
    ]
    assert all(have_sh for _command, have_sh in commands)


def test_tailscale_reconnect_receiver_is_verified(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3: True)

    assert repair.ensure_tailscale() == "repaired"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert not any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_first_failure_defers_activity_fallback(monkeypatch):
    """A single down reading shouldn't yank the app into the foreground —
    only a second consecutive cycle (tracked via state.json) escalates."""
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3: False)
    monkeypatch.setattr(repair, "_previous_repair_field", lambda _key: "up")

    assert repair.ensure_tailscale() == "FAILED"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert not any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_failed_receiver_and_activity_report_failure(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3: False)
    monkeypatch.setattr(repair, "_previous_repair_field", lambda _key: "down")

    assert repair.ensure_tailscale() == "FAILED"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_status_normalizes_runtime_and_policy(monkeypatch):
    _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda: False)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: False)

    assert repair._tailscale_status(have_sh=True) == ("down", "down")


def test_tailscale_status_skips_disabled_profile(monkeypatch):
    monkeypatch.setattr(repair, "read_device_profile", lambda: {"tailscaleEnabled": False})

    assert repair._tailscale_status() == ("skip", "skip")


def test_tailscale_runtime_probes_remote_control_plane(monkeypatch):
    commands = []
    monkeypatch.setattr(repair, "sh_adb", lambda _command: (0, "tun0\n"))
    monkeypatch.setattr(
        repair,
        "run",
        lambda args, timeout=15: commands.append((args, timeout)) or (0, ""),
    )

    assert repair._tailscale_runtime_up() is True
    assert commands == [
        (
            ["ping", "-c", "2", "-W", "3", "controlplane.tailscale.com"],
            8,
        )
    ]


# ── On-device fallback anomaly detection (issue: central-logging gap, 2026-07-31) ──


def _write_watchdog_log(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ts(seconds_ago, now=None):
    """Format a 'YYYY-MM-DD HH:MM:SS' watchdog-log timestamp N seconds before now."""
    import datetime as _dt

    now = now if now is not None else time.time()
    return _dt.datetime.fromtimestamp(now - seconds_ago).strftime("%Y-%m-%d %H:%M:%S")


def test_count_recent_watchdog_errors_only_counts_err_within_window(tmp_path):
    log = tmp_path / "watchdog.log"
    _write_watchdog_log(
        log,
        [
            # 3 ERR lines inside the 1h window (10, 30, 50 min ago).
            "%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(10 * 60),
            "%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(30 * 60),
            "%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(50 * 60),
            # Outside the window (2h ago) — must not count.
            "%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(2 * 3600),
            # WARNING/NOTICE lines must not count as ERR.
            "%s [repair] WARNING: wireless debugging re-enable FAILED" % _ts(5 * 60),
            "%s [repair] NOTICE: Tailscale restored" % _ts(4 * 60),
        ],
    )
    assert repair.count_recent_watchdog_errors(path=str(log)) == 3


def test_count_recent_watchdog_errors_missing_file_is_zero(tmp_path):
    assert repair.count_recent_watchdog_errors(path=str(tmp_path / "missing.log"), now=time.time()) == 0


class _FakeTapi:
    def __init__(self):
        self.calls = []

    def notify(self, args, **kwargs):
        self.calls.append(args)


def test_maybe_notify_error_rate_below_threshold_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, "SDLOG", str(tmp_path / "watchdog.log"))
    monkeypatch.setattr(repair, "ERROR_RATE_NOTIFY_STAMP", str(tmp_path / "state" / "notify-stamp"))
    monkeypatch.setattr(repair, "log", lambda *_a, **_k: None)
    _write_watchdog_log(
        tmp_path / "watchdog.log",
        ["%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(60)],
    )
    tapi = _FakeTapi()
    assert repair.maybe_notify_error_rate(tapi_module=tapi) == "ok"
    assert tapi.calls == []


def test_maybe_notify_error_rate_notifies_via_termux_api_wrapper_only(tmp_path, monkeypatch):
    """Must go through the safe termux_api wrapper (notify()), never a bare
    subprocess call to termux-notification — a bare timeout+kill on a
    termux-api client causes a loud ResultReturner-error toast (the exact bug
    already fixed once this session, in start_adb.py)."""
    monkeypatch.setattr(repair, "SDLOG", str(tmp_path / "watchdog.log"))
    monkeypatch.setattr(repair, "ERROR_RATE_NOTIFY_STAMP", str(tmp_path / "state" / "notify-stamp"))
    monkeypatch.setattr(repair, "log", lambda *_a, **_k: None)
    _write_watchdog_log(
        tmp_path / "watchdog.log",
        [
            "%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(20 * 60),
            "%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(10 * 60),
            "%s [repair] ERR: Tailscale repair FAILED (runtime=down policy=down)" % _ts(60),
        ],
    )

    def _no_subprocess_run(*_a, **_k):
        raise AssertionError("must not call subprocess.run directly for termux-notification")

    monkeypatch.setattr(repair.subprocess, "run", _no_subprocess_run)

    tapi = _FakeTapi()
    assert repair.maybe_notify_error_rate(tapi_module=tapi) == "notified"
    assert len(tapi.calls) == 1
    assert tapi.calls[0][0] == "termux-notification"
    assert (tmp_path / "state" / "notify-stamp").is_file()

    # A second call right away must respect the re-notify cooldown.
    assert repair.maybe_notify_error_rate(tapi_module=tapi) == "cooldown"
    assert len(tapi.calls) == 1
