#!/usr/bin/env python3
"""Run fleet-wide Termux pkg update/upgrade via Ansible (nightly launchd entry).

Standard Termux package maintenance is ``pkg update`` + ``pkg upgrade -y``
(apt under the hood). This wrapper invokes the same
``stayturgid.termux.termux_pkg`` path used at deploy time (mirror pin +
``apt-get full-upgrade`` / ``pkg upgrade``), over SSH to every inventory host.

Usage:
  python3 control/bin/termux_pkg_nightly.py
  python3 control/bin/termux_pkg_nightly.py --limit s24
  CHECK=1 python3 control/bin/termux_pkg_nightly.py   # ansible --check

Logs: ~/.config/stayturgid/logs/termux-pkg-nightly.log
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control.lib.ansible_context import AnsibleConfigError, require_inventory, resolve_ansible_context

PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "fleet" / "termux-pkg-upgrade.yml"
LOG_DIR = Path.home() / ".config" / "stayturgid" / "logs"
LOG = LOG_DIR / "termux-pkg-nightly.log"
MAX_LOG_LINES = 4000


def ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = "%s  %s\n" % (ts(), msg)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    print(line, end="")


def trim_log() -> None:
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines(True)
        if len(lines) > MAX_LOG_LINES:
            LOG.write_text("".join(lines[-MAX_LOG_LINES:]), encoding="utf-8")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        default=os.environ.get("HOSTS", "").replace(" ", ",") or None,
        help="Ansible --limit (comma-separated hosts); or HOSTS env",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="ansible-playbook --check --diff (or CHECK=1)",
    )
    args = ap.parse_args(argv)
    check = args.check or os.environ.get("CHECK", "0") == "1"

    if not PLAYBOOK.is_file():
        log("ERROR: missing playbook %s" % PLAYBOOK)
        return 2
    try:
        context = resolve_ansible_context(REPO_ROOT)
        require_inventory(context)
    except AnsibleConfigError as exc:
        log("ERROR: %s" % exc)
        return 2

    cmd = [
        "ansible-playbook",
        str(PLAYBOOK),
        "-e",
        "stayturgid_repo_root=%s" % REPO_ROOT,
    ]
    if args.limit:
        cmd.extend(["--limit", args.limit])
    if check:
        cmd.extend(["--check", "--diff"])

    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(context.config)
    env["STAYTURGID_ROOT"] = str(REPO_ROOT)
    # launchd has a minimal PATH; prefer Homebrew ansible.
    homebrew = "/opt/homebrew/bin:/usr/local/bin"
    env["PATH"] = homebrew + ":" + env.get("PATH", "/usr/bin:/bin")

    log("start: config=%s (%s) inventory=%s" % (context.config, context.source, context.inventory))
    log("start: %s" % " ".join(cmd))
    try:
        r = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("STAYTURGID_TERMUX_PKG_TIMEOUT", "3600")),
        )
    except FileNotFoundError:
        log("ERROR: ansible-playbook not found on PATH=%s" % env.get("PATH"))
        return 2
    except subprocess.TimeoutExpired:
        log("ERROR: ansible-playbook timed out")
        return 2

    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if out:
        for line in out.splitlines()[-80:]:
            log("  | %s" % line)
    log("done rc=%s" % r.returncode)
    trim_log()
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
