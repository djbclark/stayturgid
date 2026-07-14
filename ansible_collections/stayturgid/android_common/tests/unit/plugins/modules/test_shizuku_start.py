"""Unit tests for shizuku_start module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import shizuku_start as mod  # noqa: E402

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
            ("pgrep -f '[s]hizuku_server'", (0, "up\n", "")),
        ]
    )
    assert mod.shizuku_running(run, "dev") is True


def test_shizuku_running_down():
    run = fake_run(
        [
            ("HEADLESS_STATUS", (0, "Broadcast completed: result=0\n", "")),
            ("pgrep -f '[s]hizuku_server'", (1, "", "")),
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
            ("pgrep -f '[s]hizuku_server'", (1, "", "")),
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
            ("pgrep -f '[s]hizuku_server'", (1, "", "")),
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
            ("pgrep -f '[s]hizuku_server'", (1, "", "")),
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
