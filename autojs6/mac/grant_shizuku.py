#!/usr/bin/env python3
"""Grant Shizuku API access to AutoJs6 (stayturgid watchdog).

Python replacement for grant-shizuku.sh — the shizuku.json patch is now a
unit-tested function (shared/mac/stayturgid_device.py) instead of an embedded
bash heredoc. Does not revoke anything; other apps keep their Shizuku access.

Usage: ./grant_shizuku.py <p7a|s24|serial>
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "shared", "mac"))
import stayturgid_device as dev  # noqa: E402

AUTOJS_PKG = "org.autojs.autojs6"
SHIZUKU_PERM = "moe.shizuku.manager.permission.API_V23"
SHIZUKU_JSON = "/data/local/tmp/shizuku/shizuku.json"
STAGING = "/sdcard/Download/shizuku.json"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.stderr.write("usage: grant_shizuku.py <p7a|s24|serial>\n")
        return 2
    shell = dev.PrivShell(argv[0])

    uid = shell.app_uid(AUTOJS_PKG)
    if not uid:
        sys.stderr.write("ERROR: could not resolve AutoJs6 uid\n")
        return 1

    shell.sh("pm grant %s %s" % (AUTOJS_PKG, SHIZUKU_PERM))

    current, ok = shell.read_shizuku_json(SHIZUKU_JSON)
    if not ok:
        sys.stderr.write(
            "ERROR: no privileged shell or unreadable %s — aborting before "
            "touching it (would clobber other apps' grants)\n" % SHIZUKU_JSON)
        return 1

    patched = dev.patch_shizuku_json(current, uid, AUTOJS_PKG)
    if not shell.install_shizuku_json(patched, STAGING, SHIZUKU_JSON):
        sys.stderr.write("ERROR: failed to install patched shizuku.json\n")
        return 1

    print("Shizuku: allowed AutoJs6 (uid=%s) on %s" % (uid, shell.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
