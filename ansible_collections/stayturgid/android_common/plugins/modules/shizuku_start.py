#!/usr/bin/python
# -*- coding: utf-8 -*-
# @heals: SHIZUKU-SERVER-CURRENT

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: shizuku_start
short_description: Start Shizuku on a device via ADB and apply fleet profile
description:
  - Starts the Shizuku daemon on an Android device over ADB.
  - First tries HEADLESS_START broadcast.
  - Falls back to direct libshizuku.so native launch.
  - Applies the fleet profile after start and reconciles it on every run.
  - Verifies the daemon is running and port 5555 is reachable.
  - Restarts a running server that started before the installed package was
    last updated (C(adb install -r) leaves the uid-shell server running the
    old code).
  - Idempotent with respect to the Shizuku daemon itself.
options:
  device:
    description: ADB device serial.
    type: str
    required: true
  shizuku_pkg:
    description: Shizuku package name.
    type: str
    default: moe.shizuku.privileged.api
  connect:
    description: Run C(adb connect) before other operations.
    type: bool
    default: true
  fleet_profile:
    description: Fleet profile JSON to apply after start.
    type: dict
  start_timeout:
    description: Maximum seconds to wait for Shizuku to come up.
    type: int
    default: 15
"""

EXAMPLES = r"""
- name: Start Shizuku and apply fleet profile
  stayturgid.android_common.shizuku_start:
    device: "{{ adb_target }}"
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when Shizuku was started or a stale server was restarted.
  type: bool
shizuku:
  description: Final Shizuku state (up / down / already_up / up_no_port).
  type: str
start_method:
  description: >-
    How Shizuku was started (headless / native / already_up /
    restarted_stale; in check mode would_start / would_restart_stale).
  type: str
server_stale:
  description: >-
    Whether the server found running started before the package's
    lastUpdateTime (yes / no / unknown). Unknown never restarts anything.
  type: str
server_started:
  description: Epoch seconds the running server started, by the phone's clock, or null.
  type: int
package_updated:
  description: Epoch seconds of the package's lastUpdateTime, by the phone's clock, or null.
  type: int
port5555:
  description: Whether port 5555 is open after start.
  type: str
fleet_profile_reconciled:
  description: >-
    True when the fleet profile (watchdog, tcp_mode, etc.) was successfully
    (re-)pushed and applied this run. The app defaults C(watchdog) to false,
    and it is only ever set by this profile — reconciling it on every run
    (not just on a cold start) keeps a device from silently drifting out of
    its self-healing configuration.
  type: bool
fleet_profile_result:
  description: >-
    The app's own record of this run's apply, read back from
    C(files/fleet/last-apply.json) (schema, ts, success, applied, skipped,
    errors, message, profile_sha256, source, app_version). The string
    C(unreported) when no result newer than the apply appeared (an app build
    that predates the file, or the apply never ran). The task fails when the
    record says C(success=false).
  type: raw
"""

import json
import time

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.shizuku_staleness import (
    STALE_YES,
    parse_staleness,
    staleness_probe,
)

SHIZUKU_PKG = "moe.shizuku.privileged.api"
HEADLESS_START = "moe.shizuku.privileged.api.HEADLESS_START"
HEADLESS_STOP = "moe.shizuku.privileged.api.HEADLESS_STOP"
HEADLESS_STATUS = "moe.shizuku.privileged.api.HEADLESS_STATUS"
STOP_TIMEOUT = 10
APPLY_FLEET = "moe.shizuku.privileged.api.APPLY_FLEET_PROFILE"
FLEET_ACTIVITY = "moe.shizuku.privileged.api/af.shizuku.manager.fleet.FleetProfileActivity"
FLEET_PROFILE_PATH = "/data/local/tmp/shizuku-fleet.json"
# ShizukuTendCF only reads a profile from its own files dirs (it refuses any
# other path with "Profile must be under ..."), so the pushed file is copied
# here before the apply. adb shell can write this dir; other apps cannot.
FLEET_APPLY_DIR = "/sdcard/Android/data/%s/files" % SHIZUKU_PKG
FLEET_APPLY_PATH = FLEET_APPLY_DIR + "/shizuku-fleet.json"
# `am start` exits 0 whatever the apply did and the silent apply shows nothing,
# so the app's result file (FleetApplyReport.kt) is the only record of the
# outcome. Same file fleet_health.HEALTH_GATHER reads.
FLEET_RESULT_PATH = FLEET_APPLY_DIR + "/fleet/last-apply.json"
FLEET_RESULT_TIMEOUT = 10
FLEET_RESULT_UNREPORTED = "unreported"

DEFAULT_FLEET_PROFILE = {
    "mode": "adb",
    "start_on_boot": True,
    "tcp_mode": True,
    "tcp_port": 5555,
    "watchdog": True,
}


def shizuku_installed(run_command, device, pkg=SHIZUKU_PKG):
    rc, out, _err = adb_shell(run_command, device, "pm path %s" % pkg)
    if rc != 0:
        return False
    return "package:" in normalize_adb_output(out)


def shizuku_running(run_command, device):
    rc, out, _err = adb_shell(
        run_command, device, "am broadcast -a %s -p %s 2>/dev/null" % (HEADLESS_STATUS, SHIZUKU_PKG)
    )
    text = normalize_adb_output(out)
    if rc == 0 and "result=1" in text:
        return True
    rc, out, _err = adb_shell(run_command, device, "pgrep -f '[s]hizuku_(plus_)?server' >/dev/null && echo up")
    return rc == 0 and "up" in normalize_adb_output(out)


def port5555_open(run_command, device):
    rc, out, _err = adb_shell(run_command, device, "grep -q ':15B3' /proc/net/tcp && echo open || echo closed")
    return rc == 0 and "open" in normalize_adb_output(out)


def send_headless_start(run_command, device):
    # Since API 26 an implicit broadcast to a manifest receiver is dropped;
    # the TendCF receiver requires the package to be named (-p).
    rc, out, _err = adb_shell(run_command, device, "am broadcast -a %s -p %s" % (HEADLESS_START, SHIZUKU_PKG))
    normalize_adb_output(out)
    return rc == 0


def server_staleness(run_command, device, pkg=SHIZUKU_PKG):
    """parse_staleness() of the on-device probe; all unknown if adb fails."""
    rc, out, _err = adb_shell(run_command, device, staleness_probe(pkg))
    return parse_staleness(normalize_adb_output(out) if rc == 0 else "")


def staleness_fields(staleness):
    return dict(
        server_stale=staleness["stale"],
        server_started=staleness["server_start"],
        package_updated=staleness["package_updated"],
    )


def wait_stopped(run_command, device, timeout):
    deadline = time.time() + timeout
    while shizuku_running(run_command, device):
        if time.time() >= deadline:
            return False
        time.sleep(1)
    return True


def stop_server(run_command, device, timeout=None):
    """HEADLESS_STOP, then SIGTERM if the server outlives it. True once it is gone.

    The receiver only stops a server the manager believes is running and
    answers NOT_RUNNING otherwise; the server runs as uid shell, so the adb
    shell can end it directly in that case.
    """
    timeout = STOP_TIMEOUT if timeout is None else timeout
    adb_shell(run_command, device, "am broadcast -a %s -p %s" % (HEADLESS_STOP, SHIZUKU_PKG))
    if wait_stopped(run_command, device, timeout):
        return True
    adb_shell(run_command, device, "pkill -f '[s]hizuku_(plus_)?server'")
    return wait_stopped(run_command, device, timeout)


def resolve_libdir(run_command, device, pkg=SHIZUKU_PKG):
    rc, out, _err = adb_shell(run_command, device, "pm path %s" % pkg)
    if rc != 0:
        return None
    for line in normalize_adb_output(out).splitlines():
        line = line.strip()
        if line.startswith("package:"):
            apk = line.split(":", 1)[1]
            return apk.rsplit("/", 1)[0] + "/lib/arm64"
    return None


def start_native(run_command, device, libdir, pkg=SHIZUKU_PKG):
    cmd = (
        "test -x %s/libshizuku.so && "
        "LD_LIBRARY_PATH=%s %s/libshizuku.so || "
        "sh /storage/emulated/0/Android/data/%s/start.sh"
    ) % (libdir, libdir, libdir, pkg)
    return adb_shell(run_command, device, cmd)


try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_timeout import (
        DEFAULT_SLOW_TIMEOUT,
        run_command_with_timeout,
    )
except ImportError:
    import os
    import sys

    _mod_utils = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "module_utils")
    if _mod_utils not in sys.path:
        sys.path.insert(0, _mod_utils)
    # Same names as the collection import above (non-collection load path); mypy
    # would flag the rebinding as no-redef.
    from adb_timeout import (  # type: ignore[no-redef]
        DEFAULT_SLOW_TIMEOUT,
        run_command_with_timeout,
    )


def push_fleet_profile(module, device, profile):
    import os
    import tempfile

    content = json.dumps(profile, separators=(",", ":"))
    tmp = tempfile.NamedTemporaryFile("w", dir=module.tmpdir, suffix=".json", delete=False)
    try:
        tmp.write(content)
        tmp.close()
        rc, _out, err = run_command_with_timeout(
            module.run_command,
            ["adb", "-s", device, "push", tmp.name, FLEET_PROFILE_PATH],
            timeout=DEFAULT_SLOW_TIMEOUT,
            get_bin_path_fn=module.get_bin_path,
        )
        if rc != 0:
            return False, "push fleet profile failed: %s" % normalize_adb_output(err)
    finally:
        os.unlink(tmp.name)
    rc, _out, err = adb_shell(module.run_command, device, "chmod 644 %s" % FLEET_PROFILE_PATH)
    if rc != 0:
        return False, "chmod fleet profile failed"
    rc, _out, err = adb_shell(
        module.run_command,
        device,
        "mkdir -p %s && cp %s %s" % (FLEET_APPLY_DIR, FLEET_PROFILE_PATH, FLEET_APPLY_PATH),
    )
    if rc != 0:
        return False, "copy fleet profile into the app's files dir failed: %s" % normalize_adb_output(err)
    return True, "ok"


def apply_fleet_profile(run_command, device):
    rc, _out, _err = adb_shell(
        run_command,
        device,
        # --ez: the activity reads `silent` as a boolean; a string extra reads
        # as false and the result toast pops up on the phone.
        "am start --user 0 -a %s -e profile_path %s --ez silent true -n %s"
        % (APPLY_FLEET, FLEET_APPLY_PATH, FLEET_ACTIVITY),
    )
    return rc == 0


def device_epoch(run_command, device):
    rc, out, _err = adb_shell(run_command, device, "date +%s")
    text = normalize_adb_output(out)
    if rc != 0 or not text.isdigit():
        return None
    return int(text)


def read_fleet_result(run_command, device):
    """The app's last apply record as a dict, or None if absent/unparseable."""
    rc, out, _err = adb_shell(run_command, device, "cat %s 2>/dev/null" % FLEET_RESULT_PATH)
    if rc != 0:
        return None
    try:
        data = json.loads(normalize_adb_output(out))
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("ts"), int):
        return None
    return data


def fleet_result_baseline(run_command, device):
    """The earliest ``ts`` that can belong to an apply started now.

    Taken from the phone's own clock, so Mac/phone skew cannot make a fresh
    result look stale. Inclusive because ``ts`` is whole seconds. Without a
    readable clock, anything newer than the record already there will do.
    """
    now = device_epoch(run_command, device)
    if now is not None:
        return now
    prior = read_fleet_result(run_command, device)
    return prior["ts"] + 1 if prior else 0


def wait_fleet_result(run_command, device, since, timeout=None):
    """Poll for a result with ``ts >= since``; FLEET_RESULT_UNREPORTED if none."""
    deadline = time.time() + (FLEET_RESULT_TIMEOUT if timeout is None else timeout)
    while True:
        result = read_fleet_result(run_command, device)
        if result is not None and result["ts"] >= since:
            return result
        if time.time() >= deadline:
            return FLEET_RESULT_UNREPORTED
        time.sleep(1)


def fleet_result_failed(result):
    # Only an explicit false fails: "unreported" is an older app build.
    return isinstance(result, dict) and result.get("success") is False


def reconcile_fleet_profile(module, device, profile):
    """Push + apply the fleet profile regardless of whether Shizuku was just
    started or was already running.

    ``watchdog`` (and the rest of the fleet profile) is only ever set by this
    profile, and the app itself defaults ``watchdog`` to off. Only applying
    the profile on a cold start means a device that has drifted out of the
    desired configuration (fresh install predating the profile, an app
    update that reset SharedPreferences, a partial first provisioning run)
    never gets reconciled as long as Shizuku happens to stay up — silently
    disarming the binder-death auto-restart chain the profile is meant to
    arm. See stayturgid#34.

    Returns ``(reconciled, result)``: ``result`` is the app's apply record
    (see read_fleet_result) or FLEET_RESULT_UNREPORTED.
    """
    ok, msg = push_fleet_profile(module, device, profile)
    if not ok:
        module.warn("fleet profile reconciliation: %s" % msg)
        return False, FLEET_RESULT_UNREPORTED
    since = fleet_result_baseline(module.run_command, device)
    if not apply_fleet_profile(module.run_command, device):
        module.warn("fleet profile reconciliation: apply_fleet_profile failed")
        return False, FLEET_RESULT_UNREPORTED
    result = wait_fleet_result(module.run_command, device, since)
    if result == FLEET_RESULT_UNREPORTED:
        module.warn(
            "fleet profile apply sent but the app reported no result in %ds "
            "(app build predates %s?)" % (FLEET_RESULT_TIMEOUT, FLEET_RESULT_PATH)
        )
    return not fleet_result_failed(result), result


def finish(module, fleet_result, **result):
    """exit_json, or fail_json when the app recorded a failed apply."""
    result["fleet_profile_result"] = fleet_result
    if fleet_result_failed(fleet_result):
        module.fail_json(msg="fleet profile apply failed on the device: %s" % fleet_result.get("message"), **result)
    module.exit_json(**result)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            shizuku_pkg=dict(type="str", default=SHIZUKU_PKG),
            connect=dict(type="bool", default=True),
            fleet_profile=dict(type="dict"),
            start_timeout=dict(type="int", default=15),
        ),
        supports_check_mode=True,
    )

    device = module.params["device"]
    pkg = module.params["shizuku_pkg"]

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    if module.check_mode:
        running = shizuku_running(module.run_command, device)
        if running:
            staleness = server_staleness(module.run_command, device, pkg)
            if staleness["stale"] == STALE_YES:
                module.exit_json(
                    changed=True,
                    shizuku="already_up",
                    start_method="would_restart_stale",
                    port5555="unknown",
                    **staleness_fields(staleness),
                )
            module.exit_json(
                changed=False,
                shizuku="already_up",
                start_method="already_up",
                port5555="unknown",
                **staleness_fields(staleness),
            )
        module.exit_json(changed=True, shizuku="down", start_method="would_start", port5555="unknown")

    if not shizuku_installed(module.run_command, device, pkg):
        module.fail_json(msg="Shizuku (%s) is not installed on %s" % (pkg, device))

    profile = module.params["fleet_profile"] or DEFAULT_FLEET_PROFILE

    running = shizuku_running(module.run_command, device)
    staleness = server_staleness(module.run_command, device, pkg) if running else parse_staleness("")
    stale = staleness_fields(staleness)
    restarted_stale = False
    if running and staleness["stale"] == STALE_YES:
        # Stopped here, started again by the cold-start path below, which
        # already knows how to fall back to a native launch.
        if not stop_server(module.run_command, device):
            module.fail_json(
                msg="Shizuku server (started %s) is older than its package (updated %s, epoch seconds) "
                "and did not stop (HEADLESS_STOP, then SIGTERM)"
                % (staleness["server_start"], staleness["package_updated"]),
                **stale,
            )
        running = False
        restarted_stale = True
    port_open = port5555_open(module.run_command, device) if running else False

    if running and port_open:
        reconciled, fleet_result = reconcile_fleet_profile(module, device, profile)
        finish(
            module,
            fleet_result,
            changed=False,
            shizuku="already_up",
            start_method="already_up",
            port5555="open",
            fleet_profile_reconciled=reconciled,
            **stale,
        )

    if running and not port_open:
        reconciled, fleet_result = reconcile_fleet_profile(module, device, profile)
        finish(
            module,
            fleet_result,
            changed=False,
            shizuku="up_no_port",
            start_method="already_up",
            port5555="closed",
            fleet_profile_reconciled=reconciled,
            **stale,
        )

    start_method = "none"

    send_headless_start(module.run_command, device)
    time.sleep(3)
    if shizuku_running(module.run_command, device):
        start_method = "headless"
    else:
        libdir = resolve_libdir(module.run_command, device, pkg)
        if libdir:
            rc, _out, _err = start_native(module.run_command, device, libdir, pkg)
            time.sleep(2)
            if shizuku_running(module.run_command, device):
                start_method = "native"
            else:
                module.fail_json(msg="Shizuku failed to start via both HEADLESS_START and native launch", **stale)
    if restarted_stale:
        start_method = "restarted_stale"

    reconciled, fleet_result = reconcile_fleet_profile(module, device, profile)
    time.sleep(1)
    send_headless_start(module.run_command, device)

    deadline = time.time() + module.params["start_timeout"]
    while time.time() < deadline:
        if shizuku_running(module.run_command, device) and port5555_open(module.run_command, device):
            break
        time.sleep(1)

    final_running = shizuku_running(module.run_command, device)
    final_port = "open" if port5555_open(module.run_command, device) else "closed"

    if final_running and final_port == "open":
        finish(
            module,
            fleet_result,
            changed=True,
            shizuku="up",
            start_method=start_method,
            port5555=final_port,
            fleet_profile_reconciled=reconciled,
            **stale,
        )
    elif final_running:
        module.warn("Shizuku is running but port 5555 is closed — fleet profile may need a second apply")
        finish(
            module,
            fleet_result,
            changed=True,
            shizuku="up_no_port",
            start_method=start_method,
            port5555="closed",
            fleet_profile_reconciled=reconciled,
            **stale,
        )
    else:
        module.fail_json(
            msg="Shizuku failed to come up within %ds timeout" % module.params["start_timeout"],
            fleet_profile_result=fleet_result,
            start_method=start_method,
            **stale,
        )


if __name__ == "__main__":
    main()
