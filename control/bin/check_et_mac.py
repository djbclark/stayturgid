#!/usr/bin/env python3
"""Soft-health probe for phone→Mac Eternal Terminal prerequisites.

  python3 control/bin/check_et_mac.py
  python3 control/bin/check_et_mac.py --probe-host s24

Exit 0 = ok; 1 = problem; 2 = misconfig.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import et_mac as em  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--probe-host",
        default="",
        help="Optional inventory host: ssh there and run BatchMode ssh to mac",
    )
    ap.add_argument("--et-port", type=int, default=em.DEFAULT_ET_PORT)
    args = ap.parse_args(argv)

    issues: list[str] = []
    facts = em.load_control_facts()
    port = int(facts.get("et_port") or args.et_port)

    if not em.etserver_listening(port):
        issues.append("etserver_down")
        print(f"FAIL etserver not listening on {port}")
    else:
        print(f"OK etserver listening on {port}")

    launchd = em.etserver_launchd_running()
    if launchd is False:
        issues.append("et_launchd_not_running")
        print("FAIL homebrew.mxcl.et not running")
    elif launchd is True:
        print("OK homebrew.mxcl.et running")

    keys = em.list_cached_pubkeys()
    if not keys:
        issues.append("no_fleet_keys_cached")
        print("FAIL no fleet pubkeys in state/et-mac (run ensure_et_mac.py)")
    else:
        print(f"OK {len(keys)} fleet pubkey(s) cached")

    ak = em.default_authorized_keys()
    if ak.is_file():
        text = ak.read_text(encoding="utf-8", errors="replace")
        if em.AK_BEGIN not in text or em.AK_END not in text:
            issues.append("ak_block_missing")
            print("FAIL authorized_keys missing STAYTURGID-ET-MAC block")
        else:
            print("OK authorized_keys has STAYTURGID-ET-MAC block")
            # peer-help must still exist if it was there — soft note only
            if "peerhelp" in text.lower() or "fire_peer_help" in text:
                print("OK peer-help restricted key(s) still present outside block")
    else:
        issues.append("ak_missing")
        print("FAIL ~/.ssh/authorized_keys missing")

    if args.probe_host:
        import subprocess

        host = args.probe_host
        # From device: BatchMode ssh mac true using device's config
        remote = (
            "ssh -o BatchMode=yes -o ConnectTimeout=8 -o IdentitiesOnly=yes "
            "mac true 2>&1"
        )
        try:
            proc = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=12",
                    host,
                    remote,
                ],
                capture_output=True,
                text=True,
                timeout=25,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            issues.append("probe_error")
            print(f"FAIL probe via {host}: {e}")
        else:
            if proc.returncode == 0:
                print(f"OK control_ssh via {host} → mac")
            else:
                issues.append("control_ssh_fail")
                err = (proc.stderr or proc.stdout or "").strip()[:200]
                print(f"FAIL control_ssh via {host}: {err or 'rc=%s' % proc.returncode}")

    if issues:
        print("issues=%s" % ",".join(issues))
        return 1
    print("issues=none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
