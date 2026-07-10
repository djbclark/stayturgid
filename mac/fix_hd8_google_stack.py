#!/usr/bin/env python3
"""Repair hd8 sideloaded Google Play stack (pin GMS + Play Store, Doze whitelist).

Play Services auto-updated to 26.x on Fire OS and crashed with
``CHANGE_DEVICE_IDLE_TEMP_WHITELIST`` SecurityException. This script
reinstalls Fire-Tools-pinned APKs (GMS 24.35.30, Play Store 42.6.23) and
whitelists GMS/GSF on Doze.

Usage:
  ./mac/fix_hd8_google_stack.py [hd8]
  ./mac/fix_hd8_google_stack.py hd8 --force
  ./mac/fix_hd8_google_stack.py hd8 --verify-autoupdate

After repair: open Play Store → Settings → Network preferences →
Auto-update apps → **Don't auto-update apps** (prevents re-break).
Or: STAYTURGID_VLM=1 make verify-play-autoupdate HOSTS=hd8
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared" / "mac"))
import hd8_google_stack as hgs  # noqa: E402
import stayturgid_device as dev  # noqa: E402


def run_command(cmd, *args, **kwargs):
    if isinstance(cmd, str):
        cmd = cmd.split()
    r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return r.returncode, r.stdout or "", r.stderr or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pin hd8 Google Play Services stack")
    parser.add_argument("host", nargs="?", default="hd8", help="Device alias (default hd8)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reinstall pinned APKs even when version looks OK",
    )
    parser.add_argument(
        "--verify-autoupdate",
        action="store_true",
        help="After stack check, VLM-verify Play Store auto-update is off (needs vlm-server)",
    )
    args = parser.parse_args(argv)

    if args.host != "hd8":
        sys.stderr.write("warning: this repair targets Fire OS; continuing for %s\n" % args.host)

    serial = dev.resolve_adb(args.host)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)

    print("hd8 Google stack repair on %s (%s)..." % (args.host, serial))
    result = hgs.repair_if_needed(run_command, serial, force=args.force)

    gms = result.get("gms_version")
    play = result.get("play_version")
    gsf = result.get("gsf_version")
    print("  gms versionCode=%s play versionCode=%s gsf=%s" % (gms, play, gsf))
    print("  doze whitelist: %s" % ", ".join(result.get("whitelist") or []))

    if result.get("downgraded"):
        install = result.get("install") or {}
        gms_i = install.get("gms") or {}
        play_i = install.get("play") or {}
        print("  reinstalled GMS (%s splits) rc=%s" % (gms_i.get("splits"), gms_i.get("rc")))
        print("  reinstalled Play (%s splits) rc=%s" % (play_i.get("splits"), play_i.get("rc")))
        if gms_i.get("rc") != 0 or play_i.get("rc") != 0:
            sys.stderr.write(
                "install error — see messages above; Play Store may need manual setup\n"
            )
            return 1
    elif hgs.needs_gms_downgrade(gms) or hgs.needs_play_downgrade(play):
        print("  still out of range after repair attempt")
        return 1
    else:
        print("  OK — pinned stack (no reinstall needed)")

    print(
        "\nOperator: Play Store → Settings → Network preferences → "
        "Auto-update apps → Don't auto-update apps"
    )
    if args.verify_autoupdate:
        verify = REPO / "mac" / "verify_play_autoupdate.py"
        env = os.environ.copy()
        env.setdefault("STAYTURGID_VLM", "1")
        r = subprocess.run(
            [sys.executable, str(verify), args.host],
            env=env,
        )
        return r.returncode
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
