#!/usr/bin/env python3
"""Full hd8 sideloaded Google Play health check (versions + optional VLM gates).

Closes the operator loop that previously required manually confirming:
  - GMS / Play / GSF pinned versions
  - No GSF/GMS crash dialog on screen
  - Play Store auto-update set to Don't auto-update apps

Usage:
  STAYTURGID_VLM=1 python3 control/bin/verify_hd8_google.py [hd8]
  just verify-hd8-google HOSTS=hd8

VLM gates run when llama-server is healthy (see docs/vlm.md). Stack version checks
always run (no VLM required).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))
import hd8_google_stack as hgs  # noqa: E402
import play_store_autoupdate as psa  # noqa: E402
import stayturgid_device as dev  # noqa: E402
import ui_driver as uid  # noqa: E402
import vlm_gate as vlm  # noqa: E402

ART = Path.home() / ".config" / "stayturgid" / "artifacts" / "vlm-verify"


def run_command(cmd, *args, **kwargs):
    if isinstance(cmd, str):
        cmd = cmd.split()
    r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return r.returncode, r.stdout or "", r.stderr or ""


def check_stack(serial: str) -> tuple[bool, dict]:
    """Stack health: packages present + GSF 10-x. GMS pin is opt-in policy only."""
    gms = hgs.package_version_code(run_command, serial, hgs.GMS_PKG)
    play = hgs.package_version_code(run_command, serial, hgs.PLAY_PKG)
    gsf = hgs.package_version_name(run_command, serial, hgs.GSF_PKG)
    ok = gms is not None and play is not None and not hgs.needs_gsf_reinstall(gsf)
    # Optional pin-policy signal (does not fail the check by default).
    pin_drift = hgs.needs_gms_downgrade(gms) or hgs.needs_play_downgrade(play)
    return ok, {
        "gms_version": gms,
        "play_version": play,
        "gsf_version": gsf,
        "ok": ok,
        "pin_policy": hgs.pin_gms_enabled(),
        "pin_drift": pin_drift,
    }


def check_crash_dialog(serial: str, gate: vlm.VlmGate) -> tuple[bool, dict]:
    if not gate.usable:
        return True, {"skipped": True, "reason": "vlm_unavailable"}
    with tempfile.TemporaryDirectory() as td:
        shot = Path(td) / "foreground.png"
        vlm.adb_screencap(serial, shot)
        return gate.verify(shot, "no_gms_crash_dialog")


def check_autoupdate(host: str, serial: str, gate: vlm.VlmGate) -> tuple[bool, dict]:
    if not gate.usable:
        return True, {"skipped": True, "reason": "vlm_unavailable"}

    import ui_guard

    def detect_play_autoupdate():
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            chk_shot = Path(td) / "check-autoupdate.png"
            vlm.adb_screencap(serial, chk_shot)
            ok, _ = gate.verify(chk_shot, "play_autoupdate_dont")
            return ok

    ui_guard.check_ui_guard(
        host=host,
        action_type="PLAY-AUTOUPDATE-OFF",
        message=(
            "Disable Google Play Store auto-updates:\n"
            "1. Open Google Play Store.\n"
            "2. Tap your profile icon (top right) -> Settings.\n"
            "3. Tap 'Network preferences' -> 'Auto-update apps'.\n"
            "4. Select 'Don't auto-update apps' and tap DONE."
        ),
        detect_fn=detect_play_autoupdate,
    )

    day = datetime.now().strftime("%Y-%m-%d")
    shot = ART / day / host / "play-autoupdate.png"
    with uid.try_handsets(serial, host) as hs:
        if not hs:
            return False, {"ok": False, "reason": "handsets_unavailable"}
        captured = psa.capture_autoupdate_screenshot(serial, shot, hs)
        if not captured:
            return False, {"ok": False, "reason": "navigation_failed"}
        return gate.verify(captured, "play_autoupdate_dont")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host", nargs="?", default="hd8")
    ap.add_argument("--json", action="store_true", help="Emit JSON summary on stdout")
    args = ap.parse_args(argv)

    os.environ.setdefault("STAYTURGID_VLM", "1")
    serial = dev.resolve_adb(args.host)
    subprocess.run(["adb", "connect", serial], capture_output=True, text=True)

    report: dict = {"host": args.host, "serial": serial, "checks": {}}
    failures: list[str] = []

    stack_ok, stack_detail = check_stack(serial)
    report["checks"]["stack"] = stack_detail
    if not stack_ok:
        failures.append("stack_drift")
        print(
            "FAIL stack: gms=%s play=%s gsf=%s"
            % (
                stack_detail.get("gms_version"),
                stack_detail.get("play_version"),
                stack_detail.get("gsf_version"),
            )
        )
    else:
        print(
            "OK stack pinned (gms=%s play=%s gsf=%s)"
            % (
                stack_detail.get("gms_version"),
                stack_detail.get("play_version"),
                stack_detail.get("gsf_version"),
            )
        )

    gate = vlm.VlmGate(autostart=True, allow_server_only=True)
    if gate.usable:
        crash_ok, crash_detail = check_crash_dialog(serial, gate)
        report["checks"]["no_crash_dialog"] = crash_detail
        if crash_detail.get("skipped"):
            print("SKIP crash dialog VLM (%s)" % crash_detail.get("reason"))
        elif crash_ok:
            print(
                "OK no GSF/GMS crash dialog (VLM %s %.1fs)"
                % (
                    crash_detail.get("backend", "?"),
                    crash_detail.get("elapsed_s", 0),
                )
            )
        else:
            failures.append("gms_crash_dialog")
            print("FAIL crash dialog visible (VLM)")

        auto_ok, auto_detail = check_autoupdate(args.host, serial, gate)
        report["checks"]["play_autoupdate"] = auto_detail
        if auto_detail.get("skipped"):
            print("SKIP play autoupdate VLM (%s)" % auto_detail.get("reason"))
        elif auto_ok:
            print(
                "OK Play Store Don't auto-update (VLM %s %.1fs)"
                % (
                    auto_detail.get("backend", "?"),
                    auto_detail.get("elapsed_s", 0),
                )
            )
        else:
            failures.append("play_autoupdate_on")
            print("FAIL Play auto-update not off (VLM)")
    else:
        report["checks"]["vlm"] = {"skipped": True, "reason": "server_unavailable"}
        print("SKIP VLM gates — start: just vlm-server (or configure cloud keys)")
        if not vlm.vlm_strict():
            print("  (stack-only pass; enable VLM for full close-out)")

    report["ok"] = not failures
    report["failures"] = failures
    if args.json:
        print(json.dumps(report, indent=2))

    if failures:
        return 1 if vlm.vlm_strict() or gate.usable else (1 if "stack_drift" in failures else 0)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
