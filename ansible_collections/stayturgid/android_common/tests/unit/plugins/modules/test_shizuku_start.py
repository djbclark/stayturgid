"""Unit tests for shizuku_start module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import shizuku_start as mod


@pytest.fixture(autouse=True)
def _no_result_wait(monkeypatch):
    # Most fakes return "" for the result file; without this every apply
    # would poll the full FLEET_RESULT_TIMEOUT before reporting "unreported".
    monkeypatch.setattr(mod, "FLEET_RESULT_TIMEOUT", 0)


def result_json(ts, success=True, message="Applied 5 preferences, skipped 0"):
    return json.dumps(
        {
            "schema": 1,
            "ts": ts,
            "success": success,
            "applied": 5 if success else 0,
            "skipped": 0,
            "errors": [] if success else ["Path not allowed"],
            "message": message,
            "profile_sha256": "ab" * 32,
            "source": "path",
            "app_version": "13.6.0",
        }
    )


# --- pure-function unit tests ---


def fake_run(cmd_results=None):
    def runner(cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        return (0, "", "")

    return runner


def test_shizuku_installed_found():
    run = fake_run([("pm path", (0, "package:/data/app/com.example/base.apk\n", ""))])
    assert mod.shizuku_installed(run, "dev", "com.example") is True


def test_shizuku_installed_not_found():
    run = fake_run([("pm path", (1, "", "not found"))])
    assert mod.shizuku_installed(run, "dev", "com.example") is False


def test_shizuku_running_headless_status_up():
    run = fake_run(
        [
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=1\n", "")),
        ]
    )
    assert mod.shizuku_running(run, "dev") is True


def test_shizuku_running_pgrep_fallback():
    run = fake_run(
        [
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=0\n", "")),
            ("pgrep -f '[s]hizuku_(plus_)?server'", (0, "up\n", "")),
        ]
    )
    assert mod.shizuku_running(run, "dev") is True


def test_shizuku_running_down():
    run = fake_run(
        [
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=0\n", "")),
            ("pgrep -f '[s]hizuku_(plus_)?server'", (1, "", "")),
        ]
    )
    assert mod.shizuku_running(run, "dev") is False


def test_port5555_open():
    run = fake_run(
        [
            ("/proc/net/tcp", (0, "open\n", "")),
        ]
    )
    assert mod.port5555_open(run, "dev") is True


def test_port5555_closed():
    run = fake_run(
        [
            ("/proc/net/tcp", (0, "closed\n", "")),
        ]
    )
    assert mod.port5555_open(run, "dev") is False


def test_resolve_libdir():
    run = fake_run(
        [
            ("pm path", (0, "package:/data/app/~~aaa==/moe.shizuku.privileged.api-bbb==/base.apk\n", "")),
        ]
    )
    path = mod.resolve_libdir(run, "dev", "moe.shizuku.privileged.api")
    assert path == "/data/app/~~aaa==/moe.shizuku.privileged.api-bbb==/lib/arm64"


def test_resolve_libdir_not_installed():
    run = fake_run([("pm path", (1, "", "not found"))])
    assert mod.resolve_libdir(run, "dev") is None


def test_send_headless_start():
    run = fake_run([("HEADLESS_START", (0, "Broadcast completed: result=0\n", ""))])
    assert mod.send_headless_start(run, "dev") is True


def test_device_epoch():
    assert mod.device_epoch(fake_run([("date +%s", (0, "1759500000\r\n", ""))]), "dev") == 1759500000
    assert mod.device_epoch(fake_run([("date +%s", (0, "", ""))]), "dev") is None
    assert mod.device_epoch(fake_run([("date +%s", (1, "1759500000", ""))]), "dev") is None


def test_read_fleet_result_parses_the_app_record():
    run = fake_run([("last-apply.json", (0, result_json(100) + "\r\n", ""))])
    result = mod.read_fleet_result(run, "dev")
    assert result["ts"] == 100
    assert result["success"] is True


@pytest.mark.parametrize("out", ["", "not json", "[1, 2]", '{"success": true}', '{"ts": "100"}'])
def test_read_fleet_result_rejects_absent_or_malformed(out):
    assert mod.read_fleet_result(fake_run([("last-apply.json", (0, out, ""))]), "dev") is None


def test_fleet_result_baseline_prefers_the_device_clock():
    run = fake_run([("date +%s", (0, "500\n", "")), ("last-apply.json", (0, result_json(100), ""))])
    assert mod.fleet_result_baseline(run, "dev") == 500


def test_fleet_result_baseline_without_clock_needs_a_newer_record():
    run = fake_run([("date +%s", (0, "", "")), ("last-apply.json", (0, result_json(100), ""))])
    assert mod.fleet_result_baseline(run, "dev") == 101
    assert mod.fleet_result_baseline(fake_run([("date +%s", (0, "", ""))]), "dev") == 0


def test_wait_fleet_result_accepts_same_second():
    run = fake_run([("last-apply.json", (0, result_json(500), ""))])
    assert mod.wait_fleet_result(run, "dev", since=500)["ts"] == 500


def test_wait_fleet_result_stale_or_missing_is_unreported():
    stale = fake_run([("last-apply.json", (0, result_json(499), ""))])
    assert mod.wait_fleet_result(stale, "dev", since=500, timeout=0) == "unreported"
    assert mod.wait_fleet_result(fake_run(), "dev", since=500, timeout=0) == "unreported"


def test_fleet_result_failed_only_on_explicit_false():
    assert mod.fleet_result_failed(json.loads(result_json(1, success=False))) is True
    assert mod.fleet_result_failed(json.loads(result_json(1))) is False
    assert mod.fleet_result_failed("unreported") is False
    assert mod.fleet_result_failed({"ts": 1}) is False


# --- module integration tests ---


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}
    call_counts = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                idx = call_counts.get(needle, 0)
                call_counts[needle] = idx + 1
                if isinstance(result, list):
                    if idx < len(result):
                        return result[idx]
                    return result[-1]
                return result
        if "pm path" in joined:
            return (0, "package:/data/app/~~a==/moe.shizuku.privileged.api-b==/base.apk\n", "")
        if "HEADLESS_STATUS" in joined:
            return (0, "Broadcast completed: result=1\n", "")
        if "pgrep" in joined:
            return (0, "up\n", "")
        if "/proc/net/tcp" in joined:
            return (0, "open\n", "")
        if "HEADLESS_START" in joined:
            return (0, "", "")
        if "APPLY_FLEET_PROFILE" in joined:
            return (0, "", "")
        return (0, "", "")

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    def fake_fail(self, **kw):
        captured.update(kw, failed=True)
        raise SystemExit(1)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fake_fail)

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_module_skips_when_already_up(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
        ),
        cmd_results=[
            ("pm path", (0, "package:/data/app/.../base.apk\n", "")),
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=1\n", "")),
            ("/proc/net/tcp", (0, "open\n", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is False
    assert out["shizuku"] == "already_up"
    # Even when the daemon itself isn't (re)started, the fleet profile
    # (watchdog, tcp_mode, ...) must still be reconciled every run — see
    # stayturgid#34: watchdog defaults to off in the app and is only ever
    # set by this profile.
    assert out["fleet_profile_reconciled"] is True
    # The fake has no result file: an app build that predates it never fails the task.
    assert out["fleet_profile_result"] == "unreported"


ALREADY_UP = [
    ("pm path", (0, "package:/data/app/.../base.apk\n", "")),
    ("HEADLESS_STATUS", (0, "Broadcast completed: result=1\n", "")),
    ("/proc/net/tcp", (0, "open\n", "")),
    ("date +%s", (0, "1000\n", "")),
]


def test_module_reports_successful_apply_result(mocker):
    out = run_module(
        mocker,
        dict(device="dev", connect=False),
        cmd_results=ALREADY_UP + [("last-apply.json", (0, result_json(1001), ""))],
    )
    assert out.get("failed") is not True, out
    assert out["fleet_profile_reconciled"] is True
    assert out["fleet_profile_result"]["success"] is True
    assert out["fleet_profile_result"]["applied"] == 5


def test_module_fails_when_app_reports_failed_apply(mocker):
    # 2026-10-03: every apply failed for hours with "Profile must be under ..."
    # while am start exited 0 and the silent apply showed nothing.
    out = run_module(
        mocker,
        dict(device="dev", connect=False),
        cmd_results=ALREADY_UP
        + [("last-apply.json", (0, result_json(1000, success=False, message="Profile must be under /x"), ""))],
    )
    assert out.get("failed") is True
    assert "Profile must be under /x" in out["msg"]
    assert out["fleet_profile_reconciled"] is False
    assert out["fleet_profile_result"]["success"] is False
    assert out["shizuku"] == "already_up"


def test_module_ignores_stale_failed_result(mocker):
    # A failure recorded before this run's apply is not this run's outcome.
    out = run_module(
        mocker,
        dict(device="dev", connect=False),
        cmd_results=ALREADY_UP + [("last-apply.json", (0, result_json(999, success=False), ""))],
    )
    assert out.get("failed") is not True, out
    assert out["fleet_profile_result"] == "unreported"
    assert out["fleet_profile_reconciled"] is True


def test_module_reconciles_profile_when_already_up_no_port(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
        ),
        cmd_results=[
            ("pm path", (0, "package:/data/app/.../base.apk\n", "")),
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=1\n", "")),
            ("/proc/net/tcp", (0, "closed\n", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is False
    assert out["shizuku"] == "up_no_port"
    assert out["fleet_profile_reconciled"] is True


def test_module_reports_reconcile_failure_when_already_up(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
        ),
        cmd_results=[
            ("pm path", (0, "package:/data/app/.../base.apk\n", "")),
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=1\n", "")),
            ("/proc/net/tcp", (0, "open\n", "")),
            ("push", (1, "", "device offline")),
        ],
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is False
    assert out["shizuku"] == "already_up"
    assert out["fleet_profile_reconciled"] is False
    assert out["fleet_profile_result"] == "unreported"


def test_module_fails_when_not_installed(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
        ),
        cmd_results=[
            ("pm path", (1, "", "not found")),
        ],
    )
    assert out.get("failed") is True


def test_module_check_mode_reports(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            _ansible_check_mode=True,
        ),
        cmd_results=[
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=1\n", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is False
    assert out["shizuku"] == "already_up"


def test_module_check_mode_would_start(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            _ansible_check_mode=True,
        ),
        cmd_results=[
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=0\n", "")),
            ("pgrep -f '[s]hizuku_(plus_)?server'", (1, "", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert out["shizuku"] == "down"


def test_module_starts_with_headless(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            start_timeout=1,
        ),
        cmd_results=[
            # installed check
            ("pm path", (0, "package:/data/app/.../base.apk\n", "")),
            # not running initially: HEADLESS_STATUS→result=0, pgrep→down
            (
                "HEADLESS_STATUS",
                [
                    (0, "Broadcast completed: result=0\n", ""),
                    # second call after headless start: running
                    (0, "Broadcast completed: result=1\n", ""),
                    # third call during verification poll: running
                    (0, "Broadcast completed: result=1\n", ""),
                ],
            ),
            ("pgrep -f '[s]hizuku_(plus_)?server'", (1, "", "")),
            # headless start and fleet profile
            ("HEADLESS_START", (0, "", "")),
            ("adb push", (0, "", "")),
            ("chmod 644", (0, "", "")),
            ("APPLY_FLEET_PROFILE", (0, "", "")),
            # port check in verification poll
            ("/proc/net/tcp", (0, "open\n", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert out["shizuku"] == "up"
    assert out["port5555"] == "open"


def test_module_cold_start_still_fails_on_failed_apply(mocker):
    out = run_module(
        mocker,
        dict(device="dev", connect=False, start_timeout=1),
        cmd_results=[
            ("pm path", (0, "package:/data/app/.../base.apk\n", "")),
            (
                "HEADLESS_STATUS",
                [
                    (0, "Broadcast completed: result=0\n", ""),
                    (0, "Broadcast completed: result=1\n", ""),
                ],
            ),
            ("pgrep -f '[s]hizuku_(plus_)?server'", (1, "", "")),
            ("/proc/net/tcp", (0, "open\n", "")),
            ("date +%s", (0, "1000\n", "")),
            ("last-apply.json", (0, result_json(1000, success=False, message="Invalid JSON"), "")),
        ],
    )
    assert out.get("failed") is True
    # Shizuku itself did start; only the profile failed.
    assert out["changed"] is True
    assert out["shizuku"] == "up"
    assert "Invalid JSON" in out["msg"]


def test_module_native_fallback(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            start_timeout=1,
        ),
        cmd_results=[
            (
                "pm path",
                [
                    (0, "package:/data/app/.../base.apk\n", ""),
                    # resolve_libdir call
                    (0, "package:/data/app/~~aaa==/moe.shizuku.privileged.api-bbb==/base.apk\n", ""),
                ],
            ),
            # headless fails: first check down, second check still down
            (
                "HEADLESS_STATUS",
                [
                    (0, "Broadcast completed: result=0\n", ""),
                    (0, "Broadcast completed: result=0\n", ""),
                    # verification poll: running after native launch
                    (0, "Broadcast completed: result=1\n", ""),
                ],
            ),
            ("pgrep -f '[s]hizuku_(plus_)?server'", (1, "", "")),
            # headless start sent
            ("HEADLESS_START", (0, "", "")),
            # native launch: libshizuku.so
            ("libshizuku.so", (0, "", "")),
            # fleet profile
            ("adb push", (0, "", "")),
            ("chmod 644", (0, "", "")),
            ("APPLY_FLEET_PROFILE", (0, "", "")),
            # port check
            ("/proc/net/tcp", (0, "open\n", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert out["shizuku"] == "up"
    assert out["start_method"] == "native"
    assert out["port5555"] == "open"
