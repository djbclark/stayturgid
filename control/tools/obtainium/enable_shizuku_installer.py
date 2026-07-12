#!/usr/bin/env python3
"""Enable Obtainium's Shizuku installer via headless fleet profile intent.

Uses djbclark/Obtainium fork's FleetProfileActivity to set
installMethod=shizuku directly via SharedPreferences — no UI needed.

Steps:
  1. pm grant API_V23 to Obtainium
  2. Add Obtainium's uid to shizuku.json
  3. Push fleet profile JSON with installMethod: shizuku
  4. Apply via FleetProfileActivity intent

Usage: ./enable_shizuku_installer.py <p7a|s24|hd8|serial>
"""
import json
import os
import subprocess
import sys
import time
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "control", "lib"))
import stayturgid_device as dev  # noqa: E402

OBTAINIUM_PKG = "dev.imranr.obtainium"
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
STAGING = "/sdcard/Download/shizuku-obtainium.json"
FLEET_PROFILE = {"installMethod": "shizuku"}
FLEET_JSON_PATH = "/data/local/tmp/obtainium-fleet.json"
FLEET_ACTIVITY = "dev.imranr.obtainium/.FleetProfileActivity"
FLEET_ACTION = "dev.imranr.obtainium.action.APPLY_FLEET_PROFILE"


def adb(serial, *args, timeout=30):
    try:
        return subprocess.run(
            ["adb", "-s", serial, "shell"] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def grant_json(serial):
    print("Granting Shizuku API to Obtainium...")
    adb(serial, "pm", "grant", OBTAINIUM_PKG, SHIZUKU_PERM)
    # Read current shizuku.json, patch in Obtainium
    result = adb(serial, "cat", SHIZUKU_JSON)
    if not result or not result.stdout:
        sys.stderr.write("ERROR: shizuku.json not readable\n")
        return False
    current = result.stdout.strip()
    # Get Obtainium's uid
    pkginfo = adb(serial, "dumpsys", "package", OBTAINIUM_PKG).stdout or ""
    uid = None
    for line in (pkginfo or "").splitlines():
        if "userId=" in line:
            uid = line.split("userId=")[-1].strip()
            break
        if line.strip().startswith("uid="):
            uid = line.strip().split()[0].split("=")[-1].rstrip(",")
            break
    if not uid:
        sys.stderr.write("ERROR: could not determine Obtainium uid\n")
        return False
    patched = dev.patch_shizuku_json(current, uid, OBTAINIUM_PKG)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(patched)
        tmp = f.name
    subprocess.run(["adb", "-s", serial, "push", tmp, STAGING], capture_output=True, check=False)
    adb(serial, "cp", STAGING, SHIZUKU_JSON)
    adb(serial, "chmod", "644", SHIZUKU_JSON)
    os.unlink(tmp)
    return True


def apply_fleet_profile(serial):
    """Push fleet profile and apply via FleetProfileActivity intent."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(FLEET_PROFILE, f)
        tmp = f.name
    subprocess.run(["adb", "-s", serial, "push", tmp, FLEET_JSON_PATH], capture_output=True, check=False)
    os.unlink(tmp)

    result = adb(serial, "am", "start",
                 "-a", FLEET_ACTION,
                 "-e", "profile_path", FLEET_JSON_PATH,
                 "-e", "silent", "true",
                 "-n", FLEET_ACTIVITY)
    time.sleep(2)
    if result and result.returncode == 0:
        print("Shizuku installer enabled via fleet profile (installMethod=shizuku).")
        return True
    sys.stderr.write("ERROR: FleetProfileActivity failed\n")
    return False


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: enable_shizuku_installer.py <p7a|s24|hd8|serial>\n")
        return 2
    host = argv[0]
    serial = dev.resolve_adb(host)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)

    if not grant_json(serial):
        return 1
    if not apply_fleet_profile(serial):
        return 1
    print("Done. Obtainium will use Shizuku for installs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
