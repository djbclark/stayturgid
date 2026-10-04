"""Tests for Termux repair's control-ET SSH config self-heal."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

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
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda _have_sh=False: True)

    assert repair.ensure_tailscale(have_sh=True) == "up"
    assert [command[:5] for command, _have_sh in commands] == [
        ["settings", "put", "secure", "always_on_vpn_app", repair.TAILSCALE_PACKAGE],
        ["settings", "put", "secure", "always_on_vpn_lockdown", "0"],
    ]
    assert all(have_sh for _command, have_sh in commands)


def test_tailscale_reconnect_receiver_is_verified(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda _have_sh=False: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3, have_sh=False: True)

    assert repair.ensure_tailscale(have_sh=True) == "repaired"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert not any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_failure_never_foregrounds_the_app(monkeypatch):
    commands = _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: True)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda _have_sh=False: False)
    monkeypatch.setattr(repair, "_wait_for_tailscale", lambda attempts=3, have_sh=False: False)
    assert repair.ensure_tailscale(have_sh=True) == "FAILED"
    assert any(command[:2] == ["am", "broadcast"] for command, _have_sh in commands)
    assert not any(command[:2] == ["am", "start"] for command, _have_sh in commands)


def test_tailscale_no_shell_reports_unknown_without_side_effects(monkeypatch):
    """Fire OS / split-storage hosts (STAYTURGID_NO_LOCAL_ADB=1) never have a
    privileged shell from Termux — have_sh is always False there. Every
    settings/proc check ensure_tailscale would otherwise attempt is
    guaranteed to fail (SecurityException / EACCES / no adb transport), so
    it must report "unknown" and take no repair action at all rather than
    logging a false "FAILED" and forcing Tailscale's UI into the foreground.
    Regression test for the hd8 false-negative confirmed live 2026-07-31."""
    commands = _setup_tailscale(monkeypatch)
    logs = []
    monkeypatch.setattr(repair, "log", lambda msg, level=repair.INFO: logs.append((msg, level)))

    assert repair.ensure_tailscale(have_sh=False) == "unknown"
    assert commands == []
    assert not any("FAILED" in msg for msg, _level in logs)


def test_tailscale_status_normalizes_runtime_and_policy(monkeypatch):
    _setup_tailscale(monkeypatch)
    monkeypatch.setattr(repair, "_tailscale_runtime_up", lambda _have_sh=False: False)
    monkeypatch.setattr(repair, "_tailscale_policy_up", lambda _have_sh=False: False)

    assert repair._tailscale_status(have_sh=True) == ("down", "down")


def test_tailscale_status_skips_disabled_profile(monkeypatch):
    monkeypatch.setattr(repair, "read_device_profile", lambda: {"tailscaleEnabled": False})

    assert repair._tailscale_status() == ("skip", "skip")


def test_tailscale_status_reports_unknown_without_shell(monkeypatch):
    """Without a privileged shell neither check can be verified — reporting
    "down" would be a false negative (see hd8, 2026-07-31)."""
    monkeypatch.setattr(repair, "read_device_profile", lambda: {})
    monkeypatch.setattr(repair, "_tailscale_installed", lambda _have_sh=False: True)

    assert repair._tailscale_status(have_sh=False) == ("unknown", "unknown")


def test_tailscale_runtime_up_without_shell_is_unknown(monkeypatch):
    """_tailscale_runtime_up must not touch sh_adb at all when have_sh is
    False — on hosts like hd8 there is no localhost:5555 daemon to reach, so
    even attempting it is a wasted, always-failing call."""

    def _boom(_command, timeout=15):
        raise AssertionError("sh_adb should not be called when have_sh is False")

    monkeypatch.setattr(repair, "sh_adb", _boom)

    assert repair._tailscale_runtime_up(have_sh=False) is None


def test_tailscale_policy_up_without_shell_is_unknown(monkeypatch):
    def _boom(_args, have_sh=False, timeout=15):
        raise AssertionError("_device_command should not be called when have_sh is False")

    monkeypatch.setattr(repair, "_device_command", _boom)

    assert repair._tailscale_policy_up(have_sh=False) is None


def test_tailscale_runtime_probes_remote_control_plane(monkeypatch):
    commands = []
    monkeypatch.setattr(repair, "sh_adb", lambda _command: (0, "tun0\n"))
    monkeypatch.setattr(
        repair,
        "run",
        lambda args, timeout=15: commands.append((args, timeout)) or (0, ""),
    )

    assert repair._tailscale_runtime_up(have_sh=True) is True
    assert commands == [
        (
            ["ping", "-c", "2", "-W", "3", "controlplane.tailscale.com"],
            8,
        )
    ]


def test_tailscale_runtime_up_recognizes_tun1(monkeypatch):
    """Regression: s24 and t2e both allocate tun1 (not tun0) for Tailscale's
    VpnService — Android assigns whatever TUN index is free, not always 0.
    A hardcoded 'tun0' match previously false-negatived here, which fired
    the disruptive foreground-activity repair fallback against a tunnel
    that was actually healthy (observed: s24, 100+ consecutive cycles)."""
    monkeypatch.setattr(repair, "sh_adb", lambda _command: (0, "tun1\n"))
    monkeypatch.setattr(repair, "run", lambda args, timeout=15: (0, ""))

    assert repair._tailscale_runtime_up(have_sh=True) is True


def test_tailscale_runtime_up_ignores_tunl0(monkeypatch):
    """tunl0 (IP-IP tunnel kernel module) is always present and never a VPN
    tunnel — must not be mistaken for a live Tailscale interface."""
    monkeypatch.setattr(repair, "sh_adb", lambda _command: (0, ""))
    monkeypatch.setattr(
        repair, "run", lambda args, timeout=15: (_ for _ in ()).throw(AssertionError("ping should not run"))
    )

    assert repair._tailscale_runtime_up(have_sh=True) is False


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


def test_sv_up_sshd_false_without_sv(monkeypatch, tmp_path):
    monkeypatch.setattr(repair, "PREFIX", str(tmp_path))
    assert repair.sv_up_sshd() is False


def test_sv_up_sshd_uses_runit_and_restores_svdir(monkeypatch, tmp_path):
    prefix = tmp_path
    (prefix / "bin").mkdir()
    sv = prefix / "bin" / "sv"
    sv.write_text("#!/bin/sh\n")
    sv.chmod(0o755)
    (prefix / "var" / "service" / "sshd").mkdir(parents=True)
    monkeypatch.setattr(repair, "PREFIX", str(prefix))
    monkeypatch.delenv("SVDIR", raising=False)

    calls = []

    def fake_run(args, timeout=15):
        calls.append(list(args))
        if args[:2] == ["pgrep", "-f"] and "unsvdir" in args[2]:
            return (1, "")  # runsvdir not running
        return (0, "")

    monkeypatch.setattr(repair, "run", fake_run)
    monkeypatch.setattr(repair.time, "sleep", lambda s: None)

    assert repair.sv_up_sshd() is True
    assert any(c[0] == "sh" and "runsvdir" in c[2] for c in calls)
    assert [str(sv), "up", "sshd"] in calls
    assert "SVDIR" not in repair.os.environ


def _watchdog_shell(script_on_device, running=True, spawn_stays_up=True):
    calls = []
    state = {"running": running}

    def sh_adb(cmd):
        calls.append(cmd)
        if cmd.startswith("pgrep -f "):
            return (0, "17845\n") if state["running"] else (1, "")
        if cmd.startswith("cat "):
            return (0, script_on_device)
        if cmd.startswith("kill -9 "):
            state["running"] = False
        if "nohup setsid sh" in cmd:
            state["running"] = spawn_stays_up
        return (0, "")

    return calls, sh_adb


def test_watchdog_current_loop_is_left_alone(monkeypatch):
    calls, sh_adb = _watchdog_shell(repair._WATCHDOG_SCRIPT_BODY)
    monkeypatch.setattr(repair, "sh_adb", sh_adb)
    assert repair.ensure_shizuku_watchdog() == "already running"
    assert not any(c.startswith("kill") or "setsid" in c for c in calls)


def test_watchdog_stale_loop_is_killed_and_replaced(monkeypatch):
    stale = repair._WATCHDOG_SCRIPT_BODY.replace("[s]hizuku_(plus_)?server", "[s]hizuku_server")
    assert stale != repair._WATCHDOG_SCRIPT_BODY
    calls, sh_adb = _watchdog_shell(stale)
    monkeypatch.setattr(repair, "sh_adb", sh_adb)
    assert repair.ensure_shizuku_watchdog() == "replaced stale loop"
    assert "kill -9 17845" in calls
    kill_at = calls.index("kill -9 17845")
    assert any("base64 -d" in c for c in calls[kill_at:])
    assert any("nohup setsid sh" in c and "</dev/null" in c for c in calls[kill_at:])


def test_watchdog_uses_explicit_headless_start_without_native_starter():
    body = repair._WATCHDOG_SCRIPT_BODY
    assert "/data/local/tmp/shizuku_starter" not in body
    assert ".HEADLESS_STATUS -n " in body
    assert ".HEADLESS_START -n " in body
    assert "result=0" in body
    assert "sleep 60" in body


class _FakeShellLib:
    ADB_AUTH_WAITING_MSG = "adb unauthorised, waiting for the user"

    def __init__(self, state):
        self.state = state
        self.calls = 0

    def adb_connect(self):
        self.calls += 1
        return self.state


def _gated(monkeypatch, state):
    lib = _FakeShellLib(state)
    monkeypatch.setattr(repair, "_shell_lib", lambda: lib)
    monkeypatch.setitem(repair._adb_auth_state, "last", None)
    return lib


def _no_bare_adb_connect(monkeypatch, extra=None):
    ran = []

    def fake_run(args, timeout=15):
        if args[:2] == ["adb", "connect"]:
            raise AssertionError("bare adb connect bypassed the gate")
        ran.append(list(args))
        return (0, "")

    monkeypatch.setattr(repair, "run", fake_run)
    return ran


def test_privileged_shell_stands_down_while_unauthorised(monkeypatch):
    _gated(monkeypatch, "waiting")
    _no_bare_adb_connect(monkeypatch)
    monkeypatch.setattr(repair, "sh_adb", lambda *_a, **_k: pytest.fail("no shell while waiting for the user"))

    assert repair.privileged_shell() is False
    assert repair.adb_auth_waiting() is True


def test_privileged_shell_authorised_path_unchanged(monkeypatch):
    lib = _gated(monkeypatch, "device")
    monkeypatch.setattr(repair, "sh_adb", lambda cmd, timeout=15: (0, "2000\n") if cmd == "id -u" else (1, ""))

    assert repair.privileged_shell() is True
    assert repair.adb_auth_waiting() is False
    assert lib.calls == 1


def test_wireless_debugging_unreachable_shell_reconnects_through_gate(monkeypatch):
    lib = _gated(monkeypatch, "device")
    _no_bare_adb_connect(monkeypatch)
    monkeypatch.setattr(repair.time, "sleep", lambda *_: None)
    answers = iter([(1, ""), (0, "1\n")])
    monkeypatch.setattr(repair, "sh_adb", lambda *_a, **_k: next(answers))

    assert repair.ensure_wireless_debugging() == "up"
    assert lib.calls == 1


def test_wireless_debugging_while_unauthorised_is_no_shell_without_error(monkeypatch):
    _gated(monkeypatch, "waiting")
    _no_bare_adb_connect(monkeypatch)
    logs = []
    monkeypatch.setattr(repair, "log", lambda msg, level=repair.INFO: logs.append((msg, level)))
    shells = []
    monkeypatch.setattr(repair, "sh_adb", lambda cmd, timeout=15: shells.append(cmd) or (1, ""))

    assert repair.ensure_wireless_debugging() == "NO_SHELL"
    # One probe before the gate, none after it: nothing retried, nothing put.
    assert shells == ["settings get global adb_wifi_enabled"]
    assert not any(level <= repair.ERR for _msg, level in logs)


def _main_with_closed_shell(monkeypatch, tmp_path, gate_state, phone=None):
    """Run main() down the no-privileged-shell branch with Shizuku up and rish present.

    With *phone*, the real stayturgid_shell gate runs against it instead of a
    stub returning *gate_state*.
    """
    if phone is None:
        _gated(monkeypatch, gate_state)
        ran = _no_bare_adb_connect(monkeypatch)
        sh_adb = lambda *_a, **_k: (1, "")  # noqa: E731
        sleep = lambda *_: None  # noqa: E731
    else:
        ran = phone.install(monkeypatch, tmp_path)
        sh_adb = phone.sh_adb
        sleep = phone.sleep
    logs = []
    statuses = []
    rish = tmp_path / ".stayturgid" / "bin" / "rish"
    rish.parent.mkdir(parents=True)
    rish.write_text("#!/bin/sh\n")
    rish.chmod(0o755)
    monkeypatch.setattr(repair, "STG", str(tmp_path / ".stayturgid"))
    monkeypatch.setattr(repair, "TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.setattr(repair, "acquire_lock", lambda: object())
    monkeypatch.setattr(repair, "trim_log", lambda *_a, **_k: None)
    monkeypatch.setattr(repair, "log", lambda msg, level=repair.INFO: logs.append((msg, level)))
    monkeypatch.setattr(repair, "_write_status", statuses.append)
    monkeypatch.setattr(repair, "ensure_sshd_down_file", lambda: None)
    monkeypatch.setattr(repair, "sshd_up", lambda: True)
    monkeypatch.setattr(repair, "privileged_shell_expected", lambda: True)
    monkeypatch.setattr(repair, "sh_adb", sh_adb)
    for name in ("ensure_shell_profile_path", "ensure_termux_mirror", "maybe_notify_error_rate"):
        monkeypatch.setattr(repair, name, lambda: None)
    for name in ("ensure_control_et_ssh_config", "ensure_os_release", "ensure_pkg_upgrade_daily"):
        monkeypatch.setattr(repair, name, lambda: "skip")
    monkeypatch.setattr(repair, "ensure_tailscale", lambda have_sh=False: "skip")
    monkeypatch.setattr(repair, "_tailscale_status", lambda have_sh=False: ("skip", "skip"))
    monkeypatch.setattr(repair.time, "sleep", sleep)
    rc = repair.main()
    return rc, ran, logs, statuses


class _FakePhone:
    """adbd behind Termux's adb server on a virtual clock: an authorised key,
    5555 closed (row "offline"), and a rish restart that leaves the row
    offline for one second before it comes back as "device"."""

    def __init__(self):
        self.clock = 0.0
        self.restarted_at = None
        self.restarts = 0
        self.connects = 0

    def state(self):
        if self.restarted_at is not None and self.clock >= self.restarted_at + 1:
            return "device"
        return "offline"

    def sleep(self, seconds):
        self.clock += seconds

    def adb(self, args, timeout=60, input_text=None):
        import subprocess

        sub = args[1] if len(args) > 1 else ""
        if sub == "devices":
            return subprocess.CompletedProcess(
                args, 0, "List of devices attached\nlocalhost:5555\t%s\n" % self.state(), ""
            )
        if sub == "connect":
            self.connects += 1
            return subprocess.CompletedProcess(args, 0, "already connected to localhost:5555\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    def sh_adb(self, cmd, timeout=15):
        if self.state() != "device":
            return 1, ""
        if cmd == "id -u":
            return 0, "2000\n"
        if cmd == "settings get global adb_wifi_enabled":
            return 0, "1\n"
        return 0, ""

    def install(self, monkeypatch, tmp_path):
        import sys

        sys.path.insert(0, str(MODULE_PATH.parent))
        import stayturgid_shell

        self.lib = stayturgid_shell
        monkeypatch.setattr(stayturgid_shell, "STG", str(tmp_path / "gate"))
        monkeypatch.setattr(stayturgid_shell, "_boot_epoch", lambda: None, raising=False)
        monkeypatch.setattr(stayturgid_shell, "run", self.adb)
        monkeypatch.setitem(repair._adb_auth_state, "last", None)
        ran = []

        def fake_run(args, timeout=15):
            if args[:2] == ["adb", "connect"]:
                raise AssertionError("bare adb connect bypassed the gate")
            ran.append(list(args))
            if args[-1:] and "ctl.restart adbd" in args[-1]:
                self.restarts += 1
                self.restarted_at = self.clock
            return (0, "")

        monkeypatch.setattr(repair, "run", fake_run)
        return ran


def test_main_offline_transport_still_restores_via_rish(monkeypatch, tmp_path):
    """Review findings 1 and 5: "offline" is what an authorised transport shows
    with 5555 closed and while adbd restarts. Through the real gate, repair
    must restart adbd once via rish and end with a uid-2000 shell, with no
    back-off marker left to block the next cycle."""
    phone = _FakePhone()
    rc, ran, logs, statuses = _main_with_closed_shell(monkeypatch, tmp_path, None, phone=phone)

    assert phone.restarts == 1
    assert phone.connects >= 1
    assert "port=open" in statuses[-1]
    assert "shell=yes" in statuses[-1]
    assert any("port 5555 restored" in msg for msg, _level in logs)
    assert not any("waiting for the user" in msg for msg, _level in logs)
    assert not Path(phone.lib.adb_auth_marker()).exists()


def test_main_unauthorised_never_restarts_adbd(monkeypatch, tmp_path):
    rc, ran, logs, statuses = _main_with_closed_shell(monkeypatch, tmp_path, "waiting")

    assert rc == 1
    assert not any("ctl.restart" in " ".join(args) for args in ran)
    assert any("adb unauthorised, waiting for the user" in msg for msg, _level in logs)
    assert not any("escalate to native-agent" in msg for msg, _level in logs)
    assert "port=CLOSED_NO_SHELL" in statuses[-1]


def test_main_closed_port_still_restores_via_rish(monkeypatch, tmp_path):
    _rc, ran, logs, _statuses = _main_with_closed_shell(monkeypatch, tmp_path, "down")

    assert any("ctl.restart adbd" in " ".join(args) for args in ran)
    assert any("escalate to native-agent" in msg for msg, _level in logs)


def test_watchdog_not_running_is_spawned(monkeypatch):
    calls, sh_adb = _watchdog_shell("", running=False)
    monkeypatch.setattr(repair, "sh_adb", sh_adb)
    assert repair.ensure_shizuku_watchdog() == "spawned"
    assert not any(c.startswith("kill") for c in calls)


def test_watchdog_spawn_that_is_reaped_fails_loudly(monkeypatch):
    calls, sh_adb = _watchdog_shell("", running=False, spawn_stays_up=False)
    monkeypatch.setattr(repair, "sh_adb", sh_adb)
    monkeypatch.setattr(repair.time, "sleep", lambda _s: None)
    assert repair.ensure_shizuku_watchdog().startswith("spawn FAILED (did not stay up)")
    assert any("nohup setsid sh" in c for c in calls)


# ── Stale Shizuku server (2026-10-04: r2785 server kept running under an r2787 APK) ──

STALENESS_MODULE = (
    ROOT / "ansible_collections" / "stayturgid" / "android_common" / "plugins" / "module_utils" / "shizuku_staleness.py"
)
STALE_OUT = "shizuku_server_start=996000\nshizuku_pkg_update=998000\nshizuku_server_stale=yes\n"


def test_staleness_probe_matches_the_collection_copy():
    spec = importlib.util.spec_from_file_location("shizuku_staleness", STALENESS_MODULE)
    assert spec and spec.loader
    staleness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(staleness)
    assert repair.SHIZUKU_STALENESS_PROBE == staleness.staleness_probe(repair.SHIZUKU_PKG)


class _FakeShizukuShell:
    """sh_adb fake with a live/dead server that HEADLESS_STOP/pkill/HEADLESS_START act on."""

    def __init__(self, probe_out, stop_works=True, kill_works=True, start_works=True):
        self.probe_out = probe_out
        self.alive = True
        self.stop_works = stop_works
        self.kill_works = kill_works
        self.start_works = start_works
        self.calls = []

    def __call__(self, cmd, timeout=15):
        self.calls.append(cmd)
        if cmd == repair.SHIZUKU_STALENESS_PROBE:
            return 0, self.probe_out
        if "HEADLESS_STATUS" in cmd:
            return 0, "Broadcast completed: result=%d\n" % (1 if self.alive else 3)
        if cmd.startswith("pgrep -f '[s]hizuku_(plus_)?server'"):
            return (0, "4242\n") if self.alive else (1, "")
        if "HEADLESS_STOP" in cmd:
            self.alive = self.alive and not self.stop_works
        elif cmd.startswith("pkill -f '[s]hizuku_(plus_)?server'"):
            self.alive = self.alive and not self.kill_works
        elif "HEADLESS_START" in cmd:
            self.alive = self.alive or self.start_works
        return 0, ""

    def index(self, needle):
        return next(i for i, c in enumerate(self.calls) if needle in c)


def _setup_stale(monkeypatch, tmp_path, shell, capture_log=True):
    logs = []
    monkeypatch.setattr(repair, "sh_adb", shell)
    if capture_log:
        monkeypatch.setattr(repair, "log", lambda msg, level=repair.INFO: logs.append((msg, level)))
    monkeypatch.setattr(repair, "SHIZUKU_STALE_RESTART_STAMP", str(tmp_path / "state" / "shizuku-stale-restart"))
    monkeypatch.setattr(repair, "SHIZUKU_STOP_TIMEOUT", 0)
    monkeypatch.setattr(repair, "SHIZUKU_START_TIMEOUT", 0)
    monkeypatch.setattr(repair.time, "sleep", lambda _s: None)
    return logs


def test_shizuku_staleness_parses_the_probe(monkeypatch):
    monkeypatch.setattr(repair, "sh_adb", lambda cmd, timeout=15: (0, STALE_OUT))
    assert repair.shizuku_staleness() == ("yes", 996000, 998000)
    monkeypatch.setattr(repair, "sh_adb", lambda cmd, timeout=15: (255, STALE_OUT))
    assert repair.shizuku_staleness() == ("unknown", None, None)
    monkeypatch.setattr(repair, "sh_adb", lambda cmd, timeout=15: (0, "shizuku_server_stale=perhaps\n"))
    assert repair.shizuku_staleness() == ("unknown", None, None)


def test_stale_shizuku_is_stopped_then_started_with_notice(monkeypatch, tmp_path):
    shell = _FakeShizukuShell(STALE_OUT)
    logs = _setup_stale(monkeypatch, tmp_path, shell)
    assert repair.restart_stale_shizuku() == "restarted"
    assert shell.index("HEADLESS_STOP") < shell.index("HEADLESS_START")
    assert not any(c.startswith("pkill") for c in shell.calls)
    assert shell.alive
    assert logs == [
        (
            "restarted stale Shizuku server (server started %s, package updated %s)"
            % (repair._fmt_epoch(996000), repair._fmt_epoch(998000)),
            repair.NOTICE,
        )
    ]
    assert (tmp_path / "state" / "shizuku-stale-restart").is_file()


def test_stale_shizuku_notice_line_format(monkeypatch, tmp_path):
    _setup_stale(monkeypatch, tmp_path, _FakeShizukuShell(STALE_OUT), capture_log=False)
    log_path = tmp_path / "repair.log"
    for name in ("LOG", "SDLOG", "SDCARD_WATCHDOG_LOG"):
        monkeypatch.setattr(repair, name, str(log_path))
    for name in ("LOG_JSONL", "SDLOG_JSONL", "SDCARD_WATCHDOG_JSONL"):
        monkeypatch.setattr(repair, name, str(tmp_path / "repair.jsonl"))
    assert repair.restart_stale_shizuku() == "restarted"
    expected = "[repair] NOTICE: restarted stale Shizuku server (server started %s, package updated %s)" % (
        repair._fmt_epoch(996000),
        repair._fmt_epoch(998000),
    )
    assert expected in log_path.read_text()


def test_stale_shizuku_restart_respects_cooldown(monkeypatch, tmp_path):
    shell = _FakeShizukuShell(STALE_OUT)
    logs = _setup_stale(monkeypatch, tmp_path, shell)
    stamp = tmp_path / "state" / "shizuku-stale-restart"
    stamp.parent.mkdir(parents=True)
    stamp.write_text(str(int(time.time()) - 60))
    assert repair.restart_stale_shizuku() == "cooldown"
    assert not any("HEADLESS_STOP" in c or "HEADLESS_START" in c for c in shell.calls)
    assert logs and logs[0][1] == repair.WARNING
    # Past the 30-minute cooldown it acts again.
    stamp.write_text(str(int(time.time()) - repair.SHIZUKU_STALE_RESTART_COOLDOWN_SEC - 1))
    assert repair.restart_stale_shizuku() == "restarted"


@pytest.mark.parametrize(
    "probe_out,expected",
    [
        ("shizuku_server_start=999000\nshizuku_pkg_update=998000\nshizuku_server_stale=no\n", "current"),
        ("shizuku_server_start=unknown\nshizuku_pkg_update=998000\nshizuku_server_stale=unknown\n", "unknown"),
        ("", "unknown"),
    ],
)
def test_current_or_unreadable_shizuku_is_left_alone(monkeypatch, tmp_path, probe_out, expected):
    shell = _FakeShizukuShell(probe_out)
    logs = _setup_stale(monkeypatch, tmp_path, shell)
    assert repair.restart_stale_shizuku() == expected
    assert shell.calls == [repair.SHIZUKU_STALENESS_PROBE]
    assert logs == []
    assert not (tmp_path / "state" / "shizuku-stale-restart").exists()


def test_stale_shizuku_that_ignores_headless_stop_is_killed(monkeypatch, tmp_path):
    shell = _FakeShizukuShell(STALE_OUT, stop_works=False)
    _setup_stale(monkeypatch, tmp_path, shell)
    assert repair.restart_stale_shizuku() == "restarted"
    assert shell.index("HEADLESS_STOP") < shell.index("pkill") < shell.index("HEADLESS_START")


def test_stale_shizuku_that_will_not_stop_fails_loudly(monkeypatch, tmp_path):
    shell = _FakeShizukuShell(STALE_OUT, stop_works=False, kill_works=False)
    logs = _setup_stale(monkeypatch, tmp_path, shell)
    assert repair.restart_stale_shizuku() == "FAILED"
    assert not any("HEADLESS_START" in c for c in shell.calls)
    assert logs[-1][1] == repair.ERR
    # Stamped anyway, so the next cycle waits out the cooldown instead of retrying.
    assert (tmp_path / "state" / "shizuku-stale-restart").is_file()


def test_stale_shizuku_that_does_not_come_back_fails_loudly(monkeypatch, tmp_path):
    shell = _FakeShizukuShell(STALE_OUT, start_works=False)
    logs = _setup_stale(monkeypatch, tmp_path, shell)
    assert repair.restart_stale_shizuku() == "FAILED"
    assert logs[-1][1] == repair.ERR
    assert "did not come back" in logs[-1][0]


def test_failed_stale_restart_is_retried_cold_on_next_pass(monkeypatch, tmp_path):
    shell = _FakeShizukuShell(STALE_OUT, start_works=False)
    _setup_stale(monkeypatch, tmp_path, shell)

    assert repair.repair_shizuku("Broadcast completed: result=1\n") == ("down", False)
    assert sum("HEADLESS_START" in call for call in shell.calls) == 1
    assert not shell.alive

    shell.start_works = True
    assert repair.repair_shizuku("Broadcast completed: result=4\n") == ("down", True)
    assert sum("HEADLESS_START" in call for call in shell.calls) == 2
    assert shell.alive


def test_stale_restart_cooldown_does_not_block_cold_retry(monkeypatch, tmp_path):
    shell = _FakeShizukuShell(STALE_OUT)
    shell.alive = False
    _setup_stale(monkeypatch, tmp_path, shell)
    stamp = tmp_path / "state" / "shizuku-stale-restart"
    stamp.parent.mkdir(parents=True)
    stamp.write_text(str(int(time.time())))

    assert repair.repair_shizuku("Broadcast completed: result=4\n") == ("down", True)
    assert shell.alive
    assert not any(call == repair.SHIZUKU_STALENESS_PROBE for call in shell.calls)


def test_starting_state_does_not_send_another_headless_start(monkeypatch):
    shell = _FakeShizukuShell("", start_works=True)
    shell.alive = False
    monkeypatch.setattr(repair, "sh_adb", shell)
    assert repair.repair_shizuku("Broadcast completed: result=0\n") == ("starting", False)
    assert not any("HEADLESS_START" in call for call in shell.calls)
