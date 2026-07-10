#!/usr/bin/env python3
"""Repair hd8 sideloaded Google Play stack (Doze whitelist + optional pin).

Default (2026-07-10): whitelist GMS/GSF and ensure GSF 10-x. Does **not**
force-downgrade GMS/Play (operator prefers newer stacks).

Emergency pin (Fire-Tools GMS 24.35.30 + Play 42.6.23)::

  STAYTURGID_HD8_PIN_GMS=1 ./control/bin/fix_hd8_google_stack.py hd8
  ./control/bin/fix_hd8_google_stack.py hd8 --force

Usage:
  ./control/bin/fix_hd8_google_stack.py [hd8]
  ./control/bin/fix_hd8_google_stack.py hd8 --force
  ./control/bin/fix_hd8_google_stack.py hd8 --verify-autoupdate
  ./control/bin/fix_hd8_google_stack.py hd8 --no-verify

When llama-server is running, auto-runs full VLM close-out (crash dialog +
auto-update) unless --no-verify. See docs/vlm.md and control/bin/verify_hd8_google.py.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import hd8_google_stack as hgs  # noqa: E402
import stayturgid_device as dev  # noqa: E402
import vlm_helpers as vh  # noqa: E402


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
        help="Run play auto-update VLM only (legacy; prefer full verify)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip VLM close-out even when llama-server is up",
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

    verify_rc = 0
    if not args.no_verify and (vh.auto_verify_enabled() or args.verify_autoupdate):
        env = os.environ.copy()
        env.setdefault("STAYTURGID_VLM", "1")
        if args.verify_autoupdate and not vh.auto_verify_enabled():
            script = REPO / "control" / "bin" / "verify_play_autoupdate.py"
        else:
            script = REPO / "control" / "bin" / "verify_hd8_google.py"
        print("\n--- VLM close-out (%s) ---" % script.name)
        verify_rc = subprocess.run(
            [sys.executable, str(script), args.host],
            env=env,
        ).returncode
    elif not args.no_verify:
        print(
            "\nOperator: Play Store → Settings → Network preferences → "
            "Auto-update apps → Don't auto-update apps"
        )
        print("  (or: make vlm-server && make verify-hd8-google HOSTS=hd8)")

    return verify_rc if verify_rc else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
