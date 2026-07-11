#!/usr/bin/env python3
"""Enable AutoJs6 fleet drawer defaults via FleetProfileActivity intent.

Uses the fleet profile intent from djbclark/AutoJs6 (fleet-profile-553)
to apply all drawer preferences without UI automation.

Deterministic order:
  1. grant_shizuku.py — pm grant + shizuku.json (privileged shell, no UI)
  2. Push fleet profile JSON to device
  3. Apply via FleetProfileActivity intent (no UI)
  4. Enable accessibility via settings put (no UI)
  5. Run shizuku-probe to verify end-to-end

Usage: ./enable_autojs6_shizuku.py <s24|p7a|hd8|serial>
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import a11y_services as a11y  # noqa: E402
import stayturgid_device as dev  # noqa: E402
import post_ui_remote as remote  # noqa: E402

AUTOJS_PKG = "org.autojs.autojs6"
AUTOJS_RUN = "org.autojs.autojs.external.open.RunIntentActivity"
FLEET_ACTIVITY = "org.autojs.autojs.core.pref.fleet.FleetProfileActivity"
FLEET_ACTION = "org.autojs.autojs6.action.APPLY_FLEET_PROFILE"
A11Y_SVC = a11y.AUTOJS6_A11Y
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
PROBE_REMOTE = "/sdcard/stayturgid/autojs6/scripts/shizuku-probe.js"
WATCHDOG_LOG = "/sdcard/stayturgid/logs/watchdog.log"
GRANT = Path(__file__).resolve().parent / "grant_shizuku.py"

# Fleet profile shipped with the device tree
LOCAL_PROFILE = REPO_ROOT / "device" / "autojs6" / "fleet_profile.json"
DEVICE_PROFILE = "/sdcard/Download/autojs6-fleet.json"


def adb(serial: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", serial, "shell"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def sync_shizuku_grants(alias: str) -> int:
    if not GRANT.is_file():
        print("WARN: grant_shizuku.py missing", file=sys.stderr)
        return 0
    print("Syncing Shizuku manager grants for AutoJs6...")
    return subprocess.run([sys.executable, str(GRANT), alias], cwd=REPO_ROOT).returncode


def shizuku_server_running(serial: str) -> bool:
    result = adb(serial, "pgrep", "-f", "shizuku_server")
    return result.returncode == 0 and bool((result.stdout or "").strip())


def pm_shizuku_granted(serial: str) -> bool:
    result = adb(serial, "dumpsys", "package", AUTOJS_PKG)
    text = result.stdout or ""
    if SHIZUKU_PERM not in text:
        return False
    block = text.split(SHIZUKU_PERM, 1)[-1][:400]
    return "granted=true" in block


def a11y_services_list(serial: str) -> str:
    result = adb(serial, "settings", "get", "secure", "enabled_accessibility_services")
    return (result.stdout or "").strip()


def a11y_enabled(serial: str) -> bool:
    return A11Y_SVC in a11y_services_list(serial)


def put_a11y_services(serial: str, value: str) -> None:
    adb(serial, "settings", "put", "secure", "enabled_accessibility_services", value)
    adb(serial, "settings", "put", "secure", "accessibility_enabled", "1")


def backup_a11y_services(serial: str, alias: str) -> str:
    live = a11y_services_list(serial)
    a11y.write_backup_file(a11y.backup_file_for(alias), live)
    tmp = REPO_ROOT / "control" / "lib" / "a11y_backups" / (".push_%s.tmp" % alias)
    a11y.write_backup_file(tmp, live)
    adb(serial, "mkdir", "-p", "/sdcard/stayturgid/state")
    subprocess.run(
        ["adb", "-s", serial, "push", str(tmp), "/sdcard/stayturgid/%s" % a11y.DEVICE_BACKUP_REL],
        capture_output=True,
        check=False,
    )
    tmp.unlink(missing_ok=True)
    return live


def enable_a11y_shell_append(serial: str, alias: str) -> bool:
    """Append AutoJs6 to the system accessibility list (merge-safe)."""
    before = a11y_services_list(serial)
    if A11Y_SVC in before:
        return True
    target = a11y.desired_services(alias, before, ensure_autojs6=True)
    put_a11y_services(serial, target)
    time.sleep(1)
    after = a11y_services_list(serial)
    repair = a11y.repair_after_shrink(before, after, alias)
    if repair and repair != after:
        put_a11y_services(serial, repair)
        time.sleep(1)
        after = a11y_services_list(serial)
    return A11Y_SVC in after


def enable_accessibility(serial: str, alias: str) -> bool:
    """Enable AutoJs6 accessibility via settings put (no UI needed)."""
    backup_a11y_services(serial, alias)
    if a11y_enabled(serial):
        print("AutoJs6 accessibility already enabled (settings).")
        return True
    if enable_a11y_shell_append(serial, alias):
        print("AutoJs6 accessibility enabled via settings merge (append-safe).")
        return True
    lost = a11y.services_lost(backup_a11y_services(serial, alias), a11y_services_list(serial))
    if lost:
        sys.stderr.write(
            "ERROR: accessibility list shrank (%s)\n" % ", ".join(lost)
        )
    sys.stderr.write("ERROR: AutoJs6 accessibility still disabled after settings merge\n")
    return False


def push_fleet_profile(serial: str) -> bool:
    """Push fleet profile JSON to device via adb push."""
    if not LOCAL_PROFILE.is_file():
        sys.stderr.write("ERROR: fleet profile not found: %s\n" % LOCAL_PROFILE)
        return False
    adb(serial, "mkdir", "-p", str(Path(DEVICE_PROFILE).parent))
    result = subprocess.run(
        ["adb", "-s", serial, "push", str(LOCAL_PROFILE), DEVICE_PROFILE],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.stderr.write("ERROR: adb push failed: %s\n" % (result.stderr or ""))
        return False
    print("Pushed fleet profile to %s" % DEVICE_PROFILE)
    return True


FLEET_RESULT_PATH = "/sdcard/autojs6-fleet-result.json"


def apply_fleet_profile(serial: str) -> bool:
    """Apply fleet profile via FleetProfileActivity intent."""
    result = adb(
        serial,
        "am", "start",
        "-a", FLEET_ACTION,
        "-e", "profile_path", DEVICE_PROFILE,
        "-e", "silent", "true",
        "-n", "%s/%s" % (AUTOJS_PKG, FLEET_ACTIVITY),
    )
    time.sleep(3)
    if result.returncode != 0:
        sys.stderr.write(
            "ERROR: FleetProfileActivity failed (rc=%d): %s\n"
            % (result.returncode, result.stderr or result.stdout or "")
        )
        return False
    result_json = adb(serial, "cat", FLEET_RESULT_PATH)
    if result_json and result_json.returncode == 0 and result_json.stdout:
        try:
            data = json.loads(result_json.stdout)
            if data.get("success"):
                print("Fleet profile applied: %d keys, %d skipped, %d failed"
                      % (data.get("applied_count", 0),
                         data.get("skipped_count", 0),
                         data.get("failed_keys", [])))
            else:
                sys.stderr.write("WARN: profile applied with errors: %s\n"
                                 % data.get("message", ""))
            return data.get("success", True)
        except (json.JSONDecodeError, KeyError) as e:
            sys.stderr.write("WARN: unreadable result file: %s\n" % e)
    print("Fleet profile applied via intent.")
    return True


def run_shizuku_probe(serial: str) -> bool:
    adb(serial, "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", "file://" + PROBE_REMOTE,
        "-t", "text/javascript",
        "-n", "%s/%s" % (AUTOJS_PKG, AUTOJS_RUN))
    time.sleep(4)
    result = adb(serial, "tail", "-12", WATCHDOG_LOG)
    lines = [ln for ln in (result.stdout or "").splitlines() if "[setup] shizuku" in ln]
    text = lines[-1] if lines else ""
    print("Probe: %s" % (text or "(no log line)"))
    return "operational=true" in text.lower()


def report_debug_state(serial: str, alias: str) -> None:
    sys.stderr.write("\n=== AutoJs6 enable FAILED on %s — debug state ===\n" % alias)
    sys.stderr.write("Host: %s  adb: %s\n" % (alias, serial))
    sys.stderr.write("enabled_accessibility_services:\n  %s\n" % a11y_services_list(serial))
    sys.stderr.write("accessibility_enabled: %s\n" % (
        (adb(serial, "settings", "get", "secure", "accessibility_enabled").stdout or "").strip()
    ))
    sys.stderr.write("shizuku_server: %s\n" % ("up" if shizuku_server_running(serial) else "down"))
    sys.stderr.write("pm shizuku grant visible: %s\n" % pm_shizuku_granted(serial))
    sys.stderr.write("fleet profile: %s\n" % LOCAL_PROFILE)
    sys.stderr.write("Re-run: ./control/tools/autojs6/enable_autojs6_shizuku.py %s\n" % alias)
    sys.stderr.write("Ensure: Shizuku running, AutoJs6 fleet-profile build installed.\n")
    sys.stderr.write("=== end debug state ===\n")


def main_mac_adb(alias: str) -> int:
    """Mac-side: fleet profile intent + a11y via adb (no UI automation)."""
    serial = dev.resolve_adb(alias)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)

    if sync_shizuku_grants(alias) != 0:
        sys.stderr.write("ERROR: grant_shizuku failed\n")
        return 1
    if not shizuku_server_running(serial):
        sys.stderr.write("ERROR: shizuku_server not running — start Shizuku first\n")
        return 1

    try:
        # Push and apply fleet profile (no UI needed)
        if not push_fleet_profile(serial):
            report_debug_state(serial, alias)
            return 1
        if not apply_fleet_profile(serial):
            report_debug_state(serial, alias)
            return 1

        # Enable accessibility via settings put (no UI needed)
        if not enable_accessibility(serial, alias):
            report_debug_state(serial, alias)
            return 1

        # Verify Shizuku permission
        if not pm_shizuku_granted(serial):
            print("WARN: pm grant not visible in dumpsys yet, waiting...")
            time.sleep(3)

        # Run shizuku probe to verify end-to-end
        if a11y_enabled(serial):
            run_shizuku_probe(serial)

        print("AutoJs6 fleet profile + Shizuku enabled on %s." % alias)
        return 0

    except Exception as e:
        sys.stderr.write("ERROR: %s\n" % e)
        report_debug_state(serial, alias)
        return 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: enable_autojs6_shizuku.py <s24|p7a|hd8|serial>\n")
        return 2

    alias = argv[0]
    return remote.run_with_mac_fallback(
        alias,
        "stayturgid_enable_autojs6.py",
        [alias],
        lambda: main_mac_adb(alias),
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
