#!/usr/bin/env python3
"""Back up and restore Termux's adb key (the vault holds one TERMUX_ADBKEY_<HOST> per phone).

  capture HOST   store the key in the vault once adbd's key store holds it (idempotent)
  restore HOST   write the stored key back when the phone has none (a reinstalled Termux)
  state HOST     authorized | unauthorized | no-key | unknown, read over the control node's adb

Needs run-as com.termux (the fleet's debuggable Termux). Prints one status line and
never a key. Exit 0 for a done or skipped step, 1 for a hard failure, 3 when the
vault is unavailable (a broken broker is a repair job: sudo-secretspec doctor).

``just deploy-termux`` runs ``capture`` after Termux's adb is authorised, and
``just bootstrap-ssh`` / bootstrap.yml run ``restore`` before Termux's first adb call.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "control" / "lib"))
import adb_cli as ac
import secretspec_exec as se
import termux_adbkey as vault
import termux_run_as as tr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up and restore Termux's adb key.")
    parser.add_argument("action", choices=["capture", "restore", "state"])
    parser.add_argument("host", help="Fleet host name (t2e, s24, ...)")
    parser.add_argument("--device", default="", help="adb serial (default: resolved from the host name)")
    args = parser.parse_args(argv)

    serial = args.device or ac.resolve_target(args.host)
    try:
        if args.action == "state":
            print(tr.adbkey_state(vault.adb_run, serial))
        elif args.action == "capture":
            print(vault.capture(args.host, serial))
        else:
            print(vault.restore(args.host, serial))
    except (se.BoundaryUnavailable, vault.VaultError, ValueError, subprocess.TimeoutExpired) as exc:
        print("%s: the adb key vault is unavailable for %s: %s" % (args.action, args.host, exc), file=sys.stderr)
        return 3
    except (RuntimeError, OSError) as exc:
        print("%s: FAIL %s: %s" % (args.action, args.host, exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
