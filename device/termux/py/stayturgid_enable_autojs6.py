#!/usr/bin/env python3
"""On-device AutoJs6 fleet profile + Shizuku enable (Termux → localhost:5555).

Uses the FleetProfileActivity intent from djbclark/AutoJs6 fleet-profile-553
build to apply drawer preferences without UI automation.

Usage: stayturgid_enable_autojs6.py [alias]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import stayturgid_shell as sh

sh.ensure_lib_path()
import a11y_services as a11y  # noqa: E402

AUTOJS_PKG = "org.autojs.autojs6"
AUTOJS_FLEET_ACTIVITY = "org.autojs.autojs.core.pref.fleet.FleetProfileActivity"
FLEET_PROFILE_ACTION = "org.autojs.autojs6.action.APPLY_FLEET_PROFILE"
A11Y_SVC = a11y.AUTOJS6_A11Y
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
PROBE_REMOTE = "/sdcard/stayturgid/autojs6/scripts/shizuku-probe.js"
WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"

# Fleet profile shipped with the device tree
LOCAL_PROFILE = os.path.join(sh.STG, "autojs6", "fleet_profile.json")
if not os.path.isfile(LOCAL_PROFILE):
    _here = os.path.abspath(__file__)
    _repo = os.path.dirname(_here)
    while _repo != os.path.dirname(_repo):
        candidate = os.path.join(_repo, "device", "autojs6", "fleet_profile.json")
        if os.path.isfile(candidate):
            LOCAL_PROFILE = candidate
            break
        _repo = os.path.dirname(_repo)

DEVICE_PROFILE = "/sdcard/Download/autojs6-fleet.json"


def adb_shell(shell, *args, timeout=30):
    return shell(*args, timeout=timeout)


def shizuku_server_running(shell):
    rc, out = shell("pgrep", "-f", "shizuku_server")
    return rc == 0 and bool((out or "").strip())


def pm_shizuku_granted(shell):
    rc, text = shell("dumpsys", "package", AUTOJS_PKG)
    text = text or ""
    if SHIZUKU_PERM not in text:
        return False
    block = text.split(SHIZUKU_PERM, 1)[-1][:400]
    return "granted=true" in block


def a11y_services_list(shell):
    rc, out = shell("settings", "get", "secure", "enabled_accessibility_services")
    return (out or "").strip()


def a11y_enabled(shell):
    return A11Y_SVC in a11y_services_list(shell)


def put_a11y_services(shell, value):
    shell("settings", "put", "secure", "enabled_accessibility_services", value)
    shell("settings", "put", "secure", "accessibility_enabled", "1")


def enable_a11y_shell_append(shell, alias):
    """Append AutoJs6 to the system accessibility list (merge-safe)."""
    before = a11y_services_list(shell)
    if A11Y_SVC in before:
        return True
    target = a11y.desired_services(alias, before, ensure_autojs6=True)
    put_a11y_services(shell, target)
    time.sleep(1)
    after = a11y_services_list(shell)
    repair = a11y.repair_after_shrink(before, after, alias)
    if repair and repair != after:
        put_a11y_services(shell, repair)
        time.sleep(1)
        after = a11y_services_list(shell)
    return A11Y_SVC in after


def backup_a11y_services(shell, alias):
    live = a11y_services_list(shell)
    state = os.path.join(os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid"), "state")
    os.makedirs(state, exist_ok=True)
    path = os.path.join(state, "a11y_services_backup.txt")
    with open(path, "w") as f:
        f.write(a11y.normalize_value(live) + "\n")
    return live


def enable_accessibility(shell, alias):
    """Enable AutoJs6 accessibility via settings put (no UI needed)."""
    before = backup_a11y_services(shell, alias)
    if a11y_enabled(shell):
        print("AutoJs6 accessibility already enabled (settings).")
        return True
    if enable_a11y_shell_append(shell, alias):
        print("AutoJs6 accessibility enabled via settings merge (append-safe).")
        return True
    lost = a11y.services_lost(before, a11y_services_list(shell))
    if lost:
        sys.stderr.write(
            "ERROR: accessibility list shrank (%s)\n" % ", ".join(lost)
        )
    sys.stderr.write("ERROR: AutoJs6 accessibility still disabled after settings merge\n")
    return False


def push_fleet_profile(shell):
    """Push the fleet profile JSON to the device."""
    if not os.path.isfile(LOCAL_PROFILE):
        sys.stderr.write("ERROR: fleet profile not found: %s\n" % LOCAL_PROFILE)
        return False
    with open(LOCAL_PROFILE) as f:
        profile = json.load(f)
    # Write to a temp location then push
    tmp = "/tmp/autojs6-fleet.json"
    with open(tmp, "w") as f:
        json.dump(profile, f, indent=2)
    shell("mkdir", "-p", os.path.dirname(DEVICE_PROFILE))
    # Read and push via stdin to avoid push_file needing ADB
    with open(tmp) as f:
        content = f.read()
    shell("sh", "-c", "cat > %s" % DEVICE_PROFILE, input=content)
    print("Pushed fleet profile to %s" % DEVICE_PROFILE)
    return True


def apply_fleet_profile(shell, *, silent=False):
    """Apply the fleet profile via FleetProfileActivity intent."""
    cmd = [
        "am", "start",
        "-a", FLEET_PROFILE_ACTION,
        "-e", "profile_path", DEVICE_PROFILE,
    ]
    if silent:
        cmd.extend(["-e", "silent", "true"])
    cmd.extend([
        "-n", "%s/%s" % (AUTOJS_PKG, AUTOJS_FLEET_ACTIVITY),
    ])
    rc, out = adb_shell(shell, *cmd)
    time.sleep(3)
    # Check if the activity launched
    if rc != 0:
        sys.stderr.write(
            "ERROR: FleetProfileActivity failed (rc=%d): %s\n" % (rc, out or "")
        )
        return False
    print("Fleet profile applied via intent.")
    return True


def run_shizuku_probe(shell):
    """Run the in-app shizuku probe script to verify end-to-end."""
    shell(
        "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", "file://" + PROBE_REMOTE,
        "-t", "text/javascript",
        "-n", "%s/org.autojs.autojs.external.open.RunIntentActivity"
        % AUTOJS_PKG,
    )
    time.sleep(4)
    rc, out = shell("tail", "-12", WATCHDOG_LOG)
    lines = [ln for ln in (out or "").splitlines() if "[setup] shizuku" in ln]
    text = lines[-1] if lines else ""
    print("Probe: %s" % (text or "(no log line)"))
    return "operational=true" in text.lower()


def sync_shizuku_grants():
    """Run the Shizuku grant script."""
    grant = os.path.join(sh.STG, "bin", "stayturgid_grant_shizuku.py")
    if not os.path.isfile(grant):
        grant = os.path.join(os.path.dirname(__file__), "stayturgid_grant_shizuku.py")
    print("Syncing Shizuku manager grants for AutoJs6...")
    return subprocess.run([sys.executable, grant], cwd=os.path.dirname(grant) or ".").returncode


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    alias = argv[0] if argv else (sh.read_device_profile().get("alias") or "device")

    # 1. Sync Shizuku grants
    if sync_shizuku_grants() != 0:
        sys.stderr.write("ERROR: grant_shizuku failed\n")
        return 1

    try:
        import stayturgid_screen_control as sc

        with sc.ScreenControlSession(label=alias) as session:
            shell = session.shell

            # 2. Check Shizuku server
            if not shizuku_server_running(shell):
                sys.stderr.write(
                    "ERROR: shizuku_server not running — start Shizuku first\n"
                )
                return 1

            # 3. Push and apply fleet profile (no UI automation)
            if not push_fleet_profile(shell):
                return 1
            if not apply_fleet_profile(shell):
                return 1

            # 4. Enable accessibility (system-level, still needs settings put)
            if not enable_accessibility(shell, alias):
                sys.stderr.write("ERROR: accessibility enable failed\n")
                return 1

            # 5. Verify Shizuku permission granted
            if not pm_shizuku_granted(shell):
                print("WARN: pm grant not visible in dumpsys yet, waiting...")
                time.sleep(3)

            # 6. Run shizuku probe
            if a11y_enabled(shell):
                run_shizuku_probe(shell)

            print("AutoJs6 fleet profile + Shizuku enabled on %s." % alias)
            return 0

    except Exception as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
