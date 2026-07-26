#!/usr/bin/env python3
"""Provision native-agent peer-start assignment (issue #61).

Writes a ``peer.json`` telling the agent which Fire-OS device(s) it should keep
Shizuku running on over external ADB. The agent reads it from its app-private
files dir (preferred) or its external files dir (fallback); this tool writes the
private copy via ``run-as`` on the debug build, and the external copy otherwise.

The targets are plain ``host:port`` (Tailscale IP + adbd port 5555) — not a
secret. The ADB *key* is generated on-device by the agent (best practice, see
issue #61); nothing sensitive is pushed here.

Usage:
  ./provision_peer.py <peer-host-or-serial> <target-ip:5555> [more targets...]
  ./provision_peer.py --start <peer> <target:5555>     # provision then trigger
  ./provision_peer.py --show  <peer>                   # print current peer.json

Default package is the debug build (org.stayturgid.agent.debug); pass
STAYTURGID_AGENT_PKG=org.stayturgid.agent for release.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "control" / "lib"))
import adb_cli as adb  # noqa: E402

PKG = os.environ.get("STAYTURGID_AGENT_PKG", "org.stayturgid.agent.debug")
PEER_START_RECEIVER = "org.stayturgid.agent.PeerStartReceiver"
PEER_START_ACTION = "org.stayturgid.agent.action.PEER_START_NOW"
SHIZUKU_PKG = os.environ.get("STAYTURGID_SHIZUKU_PKG", "moe.shizuku.privileged.api")
STAGING = "/data/local/tmp/stayturgid_peer.json"
FILE_NAME = "peer.json"


def _resolve_pkg(serial: str) -> str | None:
    for pkg in (PKG, "org.stayturgid.agent.debug", "org.stayturgid.agent"):
        if adb.package_installed(serial, pkg):
            return pkg
    return None


def _external_files_path(pkg: str) -> str:
    return f"/sdcard/Android/data/{pkg}/files/{FILE_NAME}"


def provision(serial: str, targets: list[str], remind: bool = True) -> int:
    pkg = _resolve_pkg(serial)
    if not pkg:
        sys.stderr.write(f"ERROR: native-agent not installed on {serial} ({PKG})\n")
        return 1

    payload = json.dumps({"targets": targets, "shizuku_pkg": SHIZUKU_PKG}, indent=2)

    # Stage in a world-accessible tmp dir first (adb push can't always write
    # app-scoped dirs directly on Android 11+).
    push = adb.adb(serial, "shell", f"cat > {STAGING}", input_text=payload)
    if push.returncode != 0:
        sys.stderr.write(f"ERROR: staging write failed: {(push.stderr or '').strip()}\n")
        return 1

    # Preferred: app-private files dir via run-as (works on the debuggable build).
    ok_private = False
    runas = adb.adb(
        serial,
        "shell",
        f"run-as {pkg} sh -c 'cat {STAGING} > files/{FILE_NAME}' && echo OK",
    )
    if "OK" in (runas.stdout or ""):
        ok_private = True

    # Always also write the external files-dir copy as a fallback the app can
    # read even on a non-debuggable build.
    ext = _external_files_path(pkg)
    adb.adb(serial, "shell", f"mkdir -p /sdcard/Android/data/{pkg}/files")
    ext_res = adb.adb(serial, "shell", f"cp {STAGING} {ext} && echo OK")
    ok_external = "OK" in (ext_res.stdout or "")

    adb.adb(serial, "shell", f"rm -f {STAGING}")

    if not ok_private and not ok_external:
        sys.stderr.write(
            f"ERROR: could not write peer.json to either app-private (run-as) or external ({ext}) files dir\n"
        )
        return 1

    where = []
    if ok_private:
        where.append("filesDir (run-as)")
    if ok_external:
        where.append(ext)
    print(f"peer.json provisioned on {serial} pkg={pkg} -> {', '.join(where)}")
    print(f"  targets={targets} shizuku_pkg={SHIZUKU_PKG}")
    if remind:
        for t in targets:
            set_target_reminder(t)
    return 0


# Agent ids whose external files dir the target reminder marker may live in.
AGENT_PKGS = ("org.stayturgid.agent", "org.stayturgid.agent.debug")
REMINDER_FILE = "authorize_reminder"


def set_target_reminder(target: str) -> None:
    """Best-effort: drop the 'approve the Allow dialog' marker on a target device
    so its own agent nags the operator standing at it. The peer clears the marker
    automatically over the authorized connection once peer-start succeeds.

    Needs the Mac to be able to adb-reach the target (same host:port the peer
    uses); silently skips if not reachable.
    """
    try:
        adb.run([adb.adb_bin(), "connect", target], timeout=15)
    except Exception:  # noqa: BLE001
        pass
    ok = False
    for pkg in AGENT_PKGS:
        d = f"/sdcard/Android/data/{pkg}/files"
        r = adb.adb(target, "shell", f"mkdir -p {d} && : > {d}/{REMINDER_FILE} && echo OK")
        if "OK" in (r.stdout or ""):
            ok = True
    if ok:
        print(f"  target reminder set on {target} (agent there will prompt to approve)")
    else:
        print(f"  note: could not set target reminder on {target} (adb-unreachable?) — skipping")


def trigger_start(serial: str) -> int:
    pkg = _resolve_pkg(serial)
    if not pkg:
        sys.stderr.write(f"ERROR: native-agent not installed on {serial}\n")
        return 1
    # Broadcast (not an activity) so the trigger never foregrounds the app UI;
    # PeerStartReceiver forwards to the already-running HostService FGS.
    r = adb.adb(
        serial,
        "shell",
        f"am broadcast -a {PEER_START_ACTION} -n {pkg}/{PEER_START_RECEIVER}",
    )
    if r.returncode != 0 or "Broadcast completed" not in (r.stdout or ""):
        sys.stderr.write((r.stderr or r.stdout or "am broadcast failed").strip() + "\n")
        return 1
    print(f"peer-start triggered on {serial} — watch the TARGET for a one-time")
    print("  'Always allow' ADB dialog (first connect with the agent's key),")
    print(f"  then check peerstart.log under /sdcard/Android/data/{pkg}/files/")
    return 0


def show(serial: str) -> int:
    pkg = _resolve_pkg(serial)
    if not pkg:
        sys.stderr.write(f"ERROR: native-agent not installed on {serial}\n")
        return 1
    private = adb.adb(serial, "shell", f"run-as {pkg} cat files/{FILE_NAME} 2>/dev/null")
    ext = adb.adb(serial, "shell", f"cat {_external_files_path(pkg)} 2>/dev/null")
    print(f"[filesDir]  {(private.stdout or '').strip() or '(none)'}")
    print(f"[external]  {(ext.stdout or '').strip() or '(none)'}")
    log = adb.adb(
        serial,
        "shell",
        f"tail -5 /sdcard/Android/data/{pkg}/files/peerstart.log 2>/dev/null",
    )
    if (log.stdout or "").strip():
        print("[peerstart.log tail]")
        print(log.stdout.rstrip())
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("peer", help="peer device host/alias/serial (the device that runs the starter)")
    p.add_argument("targets", nargs="*", help="Fire-OS target(s) as host:port (adbd, e.g. 100.x.x.x:5555)")
    p.add_argument("--start", action="store_true", help="trigger a peer-start immediately after provisioning")
    p.add_argument("--show", action="store_true", help="print current peer.json + peerstart.log, do nothing else")
    p.add_argument(
        "--no-remind",
        action="store_true",
        help="do not set the 'approve on target' reminder marker on the target device(s)",
    )
    args = p.parse_args(argv)

    serial = adb.resolve_target(args.peer)

    if args.show:
        return show(serial)

    if not args.targets:
        # --start with no targets = trigger only (re-uses the already-provisioned
        # peer.json). Otherwise there is nothing to do.
        if args.start:
            return trigger_start(serial)
        sys.stderr.write("ERROR: need at least one target (host:port), or use --start / --show\n")
        return 2

    rc = provision(serial, args.targets, remind=not args.no_remind)
    if rc != 0:
        return rc
    if args.start:
        return trigger_start(serial)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
