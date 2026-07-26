#!/usr/bin/env python3
# @heals: HD8-DOZE-WHITELIST HD8-GSF-PINNED HD8-GMS-PINNED
"""Repair fireos-device sideloaded Google Play stack (Doze whitelist + optional pin).

Default (2026-07-10): whitelist GMS/GSF and ensure GSF 10-x. Does **not**
force-downgrade GMS/Play (operator prefers newer stacks).

Emergency pin (Fire-Tools GMS 24.35.30 + Play 42.6.23)::

  STAYTURGID_HD8_PIN_GMS=1 ./control/bin/fix_hd8_google_stack.py fireos-device
  ./control/bin/fix_hd8_google_stack.py fireos-device --force

Usage:
  ./control/bin/fix_hd8_google_stack.py [fireos-device]
  ./control/bin/fix_hd8_google_stack.py fireos-device --force
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import hd8_google_stack as hgs
import stayturgid_device as dev


def run_command(cmd, *args, **kwargs):
    if isinstance(cmd, str):
        cmd = cmd.split()
    if cmd and cmd[0] == "adb":
        cmd[0] = dev.adb_bin()
    r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return r.returncode, r.stdout or "", r.stderr or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pin fireos-device Google Play Services stack")
    parser.add_argument("host", nargs="?", default="fireos-device", help="Device alias (default fireos-device)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reinstall pinned APKs even when version looks OK",
    )
    args = parser.parse_args(argv)

    if args.host != "fireos-device":
        sys.stderr.write("warning: this repair targets Fire OS; continuing for %s\n" % args.host)

    serial = dev.resolve_adb(args.host)
    subprocess.run([dev.adb_bin(), "connect", serial], capture_output=True, text=True)

    print("fireos-device Google stack repair on %s (%s)..." % (args.host, serial))
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
            sys.stderr.write("install error — see messages above; Play Store may need manual setup\n")
            return 1
    elif hgs.needs_gms_downgrade(gms) or hgs.needs_play_downgrade(play):
        print("  still out of range after repair attempt")
        return 1
    else:
        print("  OK — pinned stack (no reinstall needed)")

    print("\nOperator: Play Store → Settings → Network preferences → Auto-update apps → Don't auto-update apps")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
