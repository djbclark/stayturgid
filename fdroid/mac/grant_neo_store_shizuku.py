#!/usr/bin/env python3
"""Grant Shizuku to Neo Store (or Aurora Store) via the privileged adb shell.

Usage: ./grant_neo_store_shizuku.py <p7a|s24|serial-or-ip:5555> [package]

Reuses stayturgid_device.PrivShell + patch_shizuku_json (same path as Obtainium).
Prints a sentinel line "RESULT: CHANGED" or "RESULT: UNCHANGED" so callers
(the fdroid_repos role) can report idempotence accurately.

After this, on device open the client settings and confirm:
- Installer = Shizuku (or Dhizuku/Sui)
- Enable automatic / background updates
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "shared", "mac"))
import stayturgid_device as dev  # noqa: E402

SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
STAGING = "/sdcard/Download/shizuku-neo.json"
NEO_PKG = "com.machiav3lli.fdroid"
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"


def grant_json(shell, pkg):
    uid = shell.app_uid(pkg)
    if not uid:
        sys.stderr.write("ERROR: %s not installed on %s\n" % (pkg, shell.target))
        sys.stderr.write("Install via Obtainium first (stayturgid-apps.json).\n")
        return False

    print("Granting Shizuku API to %s (uid=%s)..." % (pkg, uid))
    shell.sh("pm grant %s %s" % (pkg, SHIZUKU_PERM))

    current, ok = shell.read_shizuku_json(SHIZUKU_JSON)
    if not ok:
        sys.stderr.write(
            "ERROR: no privileged shell or unreadable %s — "
            "aborting to avoid clobbering grants\n" % SHIZUKU_JSON
        )
        return None

    patched = dev.patch_shizuku_json(current, uid, pkg)
    if patched.strip() == (current or "").strip():
        print("shizuku.json already grants %s (no change)." % pkg)
        return False  # unchanged

    if not shell.install_shizuku_json(patched, STAGING, SHIZUKU_JSON):
        sys.stderr.write("ERROR: failed to install patched shizuku.json\n")
        return None

    print("shizuku.json updated for %s." % pkg)
    return True  # changed


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    alias = sys.argv[1]
    pkg = sys.argv[2] if len(sys.argv) > 2 else NEO_PKG
    shell = dev.PrivShell(alias)

    if shell.sh("true")[0] != 0:
        sys.stderr.write(
            "ERROR: no adb shell on %s — connect device and ensure Shizuku adbd is up\n"
            % shell.target
        )
        return 1

    result = grant_json(shell, pkg)
    if result is None:
        print("RESULT: FAILED")
        return 1

    print("RESULT: %s" % ("CHANGED" if result else "UNCHANGED"))
    print("On device: open client settings → Shizuku installer + auto updates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
