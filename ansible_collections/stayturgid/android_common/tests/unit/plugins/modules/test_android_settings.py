"""Unit tests for android_settings module."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))

import android_settings as mod


def run_module(mocker, args, cmd_results=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}

    def fake_run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                if isinstance(result, list):
                    # successive answers for repeated calls; the last one sticks
                    return result.pop(0) if len(result) > 1 else result[0]
                return result
        if "pm path" in joined or "pm list packages" in joined:
            return (0, "package:com.tailscale.ipn\n", "")
        if "settings get" in joined:
            return (0, "null", "")
        if "settings put" in joined:
            return (0, "", "")
        return (0, "", "")

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(1))
    )

    with pytest.raises(SystemExit):
        mod.main()
    return captured


def test_android_settings_sets_vpn(mocker):
    out = run_module(
        mocker,
        dict(
            device="100.1.2.3:5555",
            connect=False,
            require_package="com.tailscale.ipn",
            settings=[
                dict(namespace="secure", key="always_on_vpn_app", value="com.tailscale.ipn"),
                dict(namespace="secure", key="always_on_vpn_lockdown", value="1"),
            ],
        ),
    )
    assert out["changed"] is True
    assert len(out["results"]) == 2


def test_android_settings_skips_missing_package(mocker):
    out = run_module(
        mocker,
        dict(
            device="dev",
            connect=False,
            require_package="com.missing",
            settings=[
                dict(namespace="secure", key="always_on_vpn_app", value="com.tailscale.ipn"),
            ],
        ),
        cmd_results=[
            ("pm list packages", (0, "", "")),
        ],
    )
    assert out["skipped"] is True
    assert out["changed"] is False


# --- #289 lockdown interlock -------------------------------------------------

LOCKDOWN_ARGS = dict(
    device="100.101.1.2:5555",
    connect=False,
    require_package="com.tailscale.ipn",
    lockdown_management_host="100.101.1.2",
    settings=[
        dict(namespace="secure", key="always_on_vpn_app", value="com.tailscale.ipn"),
        dict(namespace="secure", key="always_on_vpn_lockdown", value="1"),
    ],
)
TUN_UP = (0, "1: lo    inet 127.0.0.1/8 scope host lo\n27: tun0    inet 100.101.1.2/32 scope global tun0\n", "")
TUN_DOWN = (0, "1: lo    inet 127.0.0.1/8 scope host lo\n3: wlan0    inet 192.168.1.20/24 scope global wlan0\n", "")


def _puts(mocker, args, ip_result, reachable=True):
    mocker.patch.object(mod, "tcp_reachable", lambda host, port, timeout=5: reachable)
    mocker.patch.object(mod.time, "sleep", lambda _s: None)
    puts = []
    warnings = []
    mocker.patch("ansible.module_utils.basic.AnsibleModule.warn", lambda self, msg: warnings.append(msg))

    out = run_module(mocker, args, cmd_results=[("ip -4 -o addr show", ip_result)])
    for r in out["results"]:
        puts.append((r["key"], r["value"]))
    return out, dict(puts), warnings


def test_lockdown_refused_when_tailscale_not_logged_in(mocker):
    """Reproduces #289: lockdown=1 on an unauthenticated device used to be written as 1."""
    out, values, warnings = _puts(mocker, LOCKDOWN_ARGS, TUN_DOWN)
    assert values["always_on_vpn_lockdown"] == "0"
    assert values["always_on_vpn_app"] == "com.tailscale.ipn"
    assert out["lockdown_interlock"]["blocked"] is True
    assert "not logged in" in out["lockdown_interlock"]["reason"]
    assert warnings and "#289" in warnings[0]


def test_lockdown_refused_when_managed_over_lan(mocker):
    args = dict(LOCKDOWN_ARGS, lockdown_management_host="192.168.1.20")
    out, values, _ = _puts(mocker, args, TUN_UP)
    assert values["always_on_vpn_lockdown"] == "0"
    assert "not a tailnet address" in out["lockdown_interlock"]["reason"]


def test_lockdown_refused_without_management_host(mocker):
    args = {k: v for k, v in LOCKDOWN_ARGS.items() if k != "lockdown_management_host"}
    out, values, _ = _puts(mocker, args, TUN_UP)
    assert values["always_on_vpn_lockdown"] == "0"
    assert out["lockdown_interlock"]["blocked"] is True


def test_lockdown_refused_when_management_host_is_another_tailnet_ip(mocker):
    args = dict(LOCKDOWN_ARGS, lockdown_management_host="100.101.9.9")
    out, values, _ = _puts(mocker, args, TUN_UP)
    assert values["always_on_vpn_lockdown"] == "0"
    assert "is not the device's tailnet address" in out["lockdown_interlock"]["reason"]


def test_lockdown_refused_when_management_path_unreachable(mocker):
    out, values, _ = _puts(mocker, LOCKDOWN_ARGS, TUN_UP, reachable=False)
    assert values["always_on_vpn_lockdown"] == "0"
    assert "not reachable" in out["lockdown_interlock"]["reason"]


def test_lockdown_allowed_when_authenticated_and_path_verified(mocker):
    out, values, warnings = _puts(mocker, LOCKDOWN_ARGS, TUN_UP)
    assert values["always_on_vpn_lockdown"] == "1"
    assert out["lockdown_interlock"] == dict(
        blocked=False, reason="verified", device_tailnet_ip="100.101.1.2", stage="verified"
    )
    assert warnings == []


def test_lockdown_zero_request_skips_interlock(mocker):
    args = dict(LOCKDOWN_ARGS)
    args["settings"] = [dict(namespace="secure", key="always_on_vpn_lockdown", value="0")]
    out, values, _ = _puts(mocker, args, TUN_DOWN)
    assert values["always_on_vpn_lockdown"] == "0"
    assert "lockdown_interlock" not in out


def test_parse_tailnet_ipv4_accepts_any_tun_index_and_rejects_non_cgnat():
    from ansible_collections.stayturgid.android_common.plugins.module_utils import adb_shell

    assert adb_shell.parse_tailnet_ipv4("9: tun3    inet 100.64.0.7/32 scope global tun3") == "100.64.0.7"
    assert adb_shell.parse_tailnet_ipv4("9: tun0    inet 100.128.0.7/32 scope global tun0") is None
    assert adb_shell.parse_tailnet_ipv4("9: wlan0    inet 100.100.0.7/24 scope global wlan0") is None
    assert adb_shell.parse_tailnet_ipv4("") is None


# --- #289 back-off: adb path and post-write verification --------------------


def _puts_seq(mocker, args, ip_results, reachable_answers, put_results=None):
    """Like _puts but with successive answers for the tailnet probe and the TCP probe."""
    answers = list(reachable_answers)
    mocker.patch.object(
        mod, "tcp_reachable", lambda host, port, timeout=5: answers.pop(0) if len(answers) > 1 else answers[0]
    )
    mocker.patch.object(mod.time, "sleep", lambda _s: None)
    warnings = []
    mocker.patch("ansible.module_utils.basic.AnsibleModule.warn", lambda self, msg: warnings.append(msg))
    cmd_results = [("ip -4 -o addr show", ip_results)]
    if put_results is not None:
        cmd_results.append(("settings put secure always_on_vpn_lockdown 0", put_results))
    out = run_module(mocker, args, cmd_results=cmd_results)
    values = {r["key"]: (r["value"], r["status"]) for r in out["results"]}
    return out, values, warnings


def test_lockdown_refused_when_adb_target_is_lan(mocker):
    """Lockdown could cut the very adb path that would be needed to revert it."""
    args = dict(LOCKDOWN_ARGS, device="192.168.1.20:5555")
    out, values, _ = _puts(mocker, args, TUN_UP)
    assert values["always_on_vpn_lockdown"] == "0"
    assert "LAN or mDNS path" in out["lockdown_interlock"]["reason"]
    assert out["lockdown_interlock"]["stage"] == "precheck"


def test_lockdown_refused_when_adb_target_is_another_tailnet_ip(mocker):
    args = dict(LOCKDOWN_ARGS, device="100.101.9.9:5555")
    out, values, _ = _puts(mocker, args, TUN_UP)
    assert values["always_on_vpn_lockdown"] == "0"
    assert "adb target 100.101.9.9:5555 is not the device's tailnet address" in out["lockdown_interlock"]["reason"]


def test_lockdown_allowed_over_usb_serial(mocker):
    args = dict(LOCKDOWN_ARGS, device="R5CX1234ABC")
    out, values, warnings = _puts(mocker, args, TUN_UP)
    assert values["always_on_vpn_lockdown"] == "1"
    assert out["lockdown_interlock"]["stage"] == "verified"
    assert warnings == []


def test_lockdown_reverted_when_management_path_dies_after_write(mocker):
    out, values, warnings = _puts_seq(mocker, LOCKDOWN_ARGS, TUN_UP, reachable_answers=[True, False])
    assert values["always_on_vpn_lockdown"] == ("0", "reverted")
    assert out["lockdown_interlock"]["blocked"] is True
    assert out["lockdown_interlock"]["stage"] == "post_write"
    assert "stopped answering" in out["lockdown_interlock"]["reason"]
    assert warnings and "reverted to 0" in warnings[-1]


def test_lockdown_reverted_when_tailnet_address_vanishes_after_write(mocker):
    out, values, _ = _puts_seq(mocker, LOCKDOWN_ARGS, [TUN_UP, TUN_DOWN], reachable_answers=[True])
    assert values["always_on_vpn_lockdown"] == ("0", "reverted")
    assert out["lockdown_interlock"]["stage"] == "post_write"
    assert "tailnet address was gone" in out["lockdown_interlock"]["reason"]


def test_lockdown_post_write_revert_failure_fails_the_task_with_recovery_steps(mocker):
    failed = {}
    mocker.patch.object(mod, "tcp_reachable", lambda host, port, timeout=5: False)
    mocker.patch.object(mod, "lockdown_interlock", lambda *a, **k: (True, "verified", "100.101.1.2"))
    mocker.patch.object(mod.time, "sleep", lambda _s: None)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.warn", lambda self, msg: None)

    def fail(self, **kw):
        failed.update(kw)
        raise SystemExit(1)

    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fail)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.exit_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(0))
    )
    mocker.patch(
        "ansible.module_utils.basic._ANSIBLE_ARGS", json.dumps({"ANSIBLE_MODULE_ARGS": dict(LOCKDOWN_ARGS)}).encode()
    )
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    def run_command(self, cmd, *a, **kw):
        joined = " ".join(cmd)
        if "settings put secure always_on_vpn_lockdown 0" in joined:
            return (1, "", "error: device offline")
        if "ip -4 -o addr show" in joined:
            return TUN_UP
        if "pm list packages" in joined:
            return (0, "package:com.tailscale.ipn\n", "")
        if "settings get" in joined:
            return (0, "0", "")
        return (0, "", "")

    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", run_command)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1
    assert "USB" in failed["msg"] and "always_on_vpn_lockdown 0" in failed["msg"]
    assert failed["lockdown_interlock"]["stage"] == "post_write"


def test_lockdown_check_mode_runs_precheck_but_never_probes_after(mocker):
    probes = []
    mocker.patch.object(mod, "tcp_reachable", lambda host, port, timeout=5: probes.append((host, port)) or True)
    mocker.patch.object(
        mod.time, "sleep", lambda _s: (_ for _ in ()).throw(AssertionError("must not settle in check mode"))
    )
    mocker.patch("ansible.module_utils.basic.AnsibleModule.warn", lambda self, msg: None)
    args = dict(LOCKDOWN_ARGS, _ansible_check_mode=True)
    out = run_module(mocker, args, cmd_results=[("ip -4 -o addr show", TUN_UP)])
    assert out["lockdown_interlock"]["stage"] == "verified"
    assert [r["status"] for r in out["results"]] == ["would_set", "would_set"]
    assert len(probes) == 1


def test_adb_target_kind():
    assert mod.adb_target_kind("R5CX1234ABC") == "usb"
    assert mod.adb_target_kind("100.101.1.2:5555") == "tailnet"
    assert mod.adb_target_kind("192.168.1.20:5555") == "other"
    assert mod.adb_target_kind("192.0.2.68:39081") == "other"
