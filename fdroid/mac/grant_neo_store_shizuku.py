#!/usr/bin/env python3
"""Grant Shizuku to Neo Store (com.machiav3lli.fdroid) and basic setup notes.

Usage: ./grant_neo_store_shizuku.py <p7a|s24|serial-or-ip:5555>

This reuses the shared stayturgid_device patch logic (same as for AutoJs6/Obtainium).
After this, on device open Neo Store settings and confirm:
- Installer = Shizuku (or Dhizuku/Sui)
- Enable automatic / background updates

The first app you install *through* Neo Store will then get auto-update behavior.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared", "mac"))
import stayturgid_device as dev

SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
STAGING = "/sdcard/Download/neo_shizuku.json"
NEO_PKG = "com.machiav3lli.fdroid"
AURORA_PKG = "com.aurora.store"

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    alias = sys.argv[1]
    pkg = sys.argv[2] if len(sys.argv) > 2 else NEO_PKG
    adb_target = dev.resolve_adb(alias)

    print(f"Using ADB target: {adb_target} (from alias {alias}) for pkg {pkg}")

    # Get uid
    status, out = subprocess.getstatusoutput(
        f'adb -s {adb_target} shell pm list packages -U {pkg}'
    )
    uid = dev.parse_uid(out)
    if not uid:
        print(f"ERROR: Could not get uid for {pkg}. Is it installed?")
        print("Install via Obtainium first (we added relevant to the catalog).")
        sys.exit(1)

    print(f"{pkg} uid: {uid}")

    # Read current shizuku.json
    status, current = subprocess.getstatusoutput(
        f'adb -s {adb_target} shell cat {SHIZUKU_JSON} 2>/dev/null || echo ""'
    )

    patched = dev.patch_shizuku_json(current, uid, pkg)

    # Write via staging (standard pattern)
    with open("/tmp/shizuku_patch.json", "w") as f:
        f.write(patched)

    subprocess.check_call(["adb", "-s", adb_target, "push", "/tmp/shizuku_patch.json", STAGING])
    subprocess.check_call(["adb", "-s", adb_target, "shell", "mv", STAGING, SHIZUKU_JSON])
    subprocess.check_call(["adb", "-s", adb_target, "shell", "chmod", "644", SHIZUKU_JSON])

    print(f"shizuku.json updated for {pkg}.")
    print("On device: open Shizuku → check authorized apps, then the client settings → enable Shizuku installer + auto updates.")

if __name__ == "__main__":
    main()
