#!/usr/bin/env python3
"""Verify Play Store 'Don't auto-update apps' via Handsets nav + optional VLM gate.

Navigates Play Store without ScreenControlSession (account drawer is unreliable
under display inversion). When STAYTURGID_VLM=1 and the llama-server is up,
confirms the radio selection from a screenshot.

Usage:
  STAYTURGID_VLM=1 python3 control/bin/verify_play_autoupdate.py hd8
  python3 control/bin/verify_play_autoupdate.py hd8 --shot-only /tmp/play-auto.png
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import play_store_autoupdate as psa  # noqa: E402
import stayturgid_device as dev  # noqa: E402
import ui_driver as uid  # noqa: E402
import vlm_gate as vlm  # noqa: E402

ART = Path.home() / ".config" / "stayturgid" / "artifacts" / "vlm-verify"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host", nargs="?", default="hd8", help="Fleet alias (default hd8)")
    ap.add_argument(
        "--shot-only",
        metavar="PNG",
        help="Skip navigation; run VLM gate on an existing screenshot",
    )
    ap.add_argument(
        "--no-vlm",
        action="store_true",
        help="Navigate and capture only; skip vision gate",
    )
    args = ap.parse_args(argv)

    if args.shot_only:
        shot = Path(args.shot_only)
        if not shot.is_file():
            sys.stderr.write("missing screenshot: %s\n" % shot)
            return 2
    else:
        serial = dev.resolve_adb(args.host)
        subprocess.run(["adb", "connect", serial], capture_output=True, text=True)
        day = datetime.now().strftime("%Y-%m-%d")
        shot = ART / day / args.host / "play-autoupdate.png"
        with uid.try_handsets(serial, args.host) as hs:
            if not hs:
                sys.stderr.write("Handsets unavailable — install ~/.handsets/hs\n")
                return 1
            captured = psa.capture_autoupdate_screenshot(serial, shot, hs)
            if not captured:
                sys.stderr.write("failed to open Play Store auto-update screen\n")
                return 1
            shot = captured
            print("screenshot: %s" % shot)

    if args.no_vlm:
        return 0

    prev = os.environ.get("STAYTURGID_VLM")
    os.environ.setdefault("STAYTURGID_VLM", "1")
    # allow_server_only so cloud keys work even when local UI-TARS is off
    gate = vlm.VlmGate(autostart=True, allow_server_only=True)
    if prev is None:
        os.environ.pop("STAYTURGID_VLM", None)
    else:
        os.environ["STAYTURGID_VLM"] = prev

    if not gate.usable:
        print("VLM skipped (no local server and no cloud keys) — capture ok")
        return 0

    ok, detail = gate.verify(shot, "play_autoupdate_dont")
    print(json.dumps(detail, indent=2, default=str)[:2000])
    if detail.get("skipped"):
        print("VLM skipped (%s) — navigation/capture ok" % detail.get("reason"))
        return 0
    if ok:
        print(
            "PASS: Don't auto-update apps (VLM backend=%s)"
            % detail.get("backend", "?")
        )
        return 0
    print("FAIL: Play auto-update not confirmed off", file=sys.stderr)
    return 1 if vlm.vlm_strict() else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
