#!/usr/bin/env python3
"""Notify when Termux apt packages on fleet devices have upgrades available.

Parallel to ``check_apk_updates.py`` (pinned Android APKs vs GitHub tags), but
for the Termux apt/pkg layer: SSH to each device, refresh package indexes,
parse ``apt list --upgradable``, and ``hermes send`` when anything is pending.

Why a separate checker (not only the nightly upgrade log):
  - Nightly ``termux_pkg_nightly.py`` upgrades everything with only an Ansible
    changed=true/false line — no package names, no hermes path (#152).
  - This script reports *available* upgrades (names + old → new versions) so
    the operator sees what is pending even if the nightly job is disabled,
    fails, or has not run yet.

Usage:
  python3 control/bin/check_termux_pkg_updates.py
  python3 control/bin/check_termux_pkg_updates.py --limit s24,p7a
  HOSTS=s24 python3 control/bin/check_termux_pkg_updates.py

Scheduled via Jobber (site overlay, same jobber as check-apk-updates) and
optionally invoked by ``termux_pkg_nightly.py`` before the upgrade playbook.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_LIB = _REPO / "control" / "lib"
for _p in (str(_LIB), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import stayturgid_device as dev  # noqa: E402

HERMES_TARGET = "telegram:838808636:22082"
STATE_PATH = os.path.expanduser("~/.local/state/stayturgid/termux-pkg-updates.json")

TERMUX_PREFIX = "/data/data/com.termux/files/usr"
SSH_TIMEOUT_SEC = int(os.environ.get("STAYTURGID_TERMUX_PKG_CHECK_TIMEOUT", "180"))

# apt list --upgradable line, e.g.:
#   curl/stable 8.12.1 aarch64 [upgradable from: 8.11.0]
#   libandroid-support/stable 29-1 aarch64 [upgradable from: 28-3]
_UPGRADABLE_RE = re.compile(
    r"^([^/\s]+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]\s*$"
)


def parse_apt_upgradable(text: str) -> list[dict[str, str]]:
    """Parse ``apt list --upgradable`` stdout into [{name, current, latest}, ...]."""
    found: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("Listing"):
            continue
        m = _UPGRADABLE_RE.match(line)
        if not m:
            continue
        found.append(
            {
                "name": m.group(1),
                "latest": m.group(2),
                "current": m.group(3).strip(),
            }
        )
    return found


def format_package_line(pkg: dict[str, str]) -> str:
    return f"{pkg['name']}: {pkg['current']} -> {pkg['latest']}"


def list_hosts(limit: str | None = None) -> list[str]:
    """Fleet aliases from devices.conf, optionally restricted by --limit/HOSTS."""
    all_hosts = [name for name, *_rest in dev.iter_devices_conf()]
    if not limit:
        return all_hosts
    wanted = {h.strip() for h in limit.replace(" ", ",").split(",") if h.strip()}
    return [h for h in all_hosts if h in wanted]


def ssh_upgradable(host: str, *, refresh: bool = True) -> tuple[list[dict[str, str]], str | None]:
    """SSH to *host* and return (upgradable packages, error_or_None).

    When *refresh* is True (default), runs ``pkg update`` first so the check
    sees current indexes — same first step as the nightly upgrade path.
    """
    ssh_host = dev.resolve_ssh_host(host) or host
    refresh_cmd = "pkg update -y >/dev/null 2>&1 || true\n" if refresh else ""
    remote = (
        f"export PATH={TERMUX_PREFIX}/bin:$PATH\n"
        f"export TMPDIR={TERMUX_PREFIX}/tmp\n"
        "export DEBIAN_FRONTEND=noninteractive\n"
        f"{refresh_cmd}"
        "apt list --upgradable 2>/dev/null\n"
    )
    try:
        result = subprocess.run(
            ["ssh", *dev.SSH_OPTS, "-o", "ConnectTimeout=10", ssh_host, remote],
            capture_output=True,
            text=True,
            timeout=SSH_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return [], f"{host}: ssh timed out after {SSH_TIMEOUT_SEC}s"
    except OSError as exc:
        return [], f"{host}: ssh failed: {exc}"

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip().splitlines()
        detail = err[-1] if err else f"rc={result.returncode}"
        return [], f"{host}: ssh/apt failed ({detail})"

    return parse_apt_upgradable(result.stdout or ""), None


def collect_updates(
    hosts: list[str],
    *,
    refresh: bool = True,
) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    """Probe each host. Returns (host -> packages, error messages)."""
    by_host: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []
    for host in hosts:
        packages, err = ssh_upgradable(host, refresh=refresh)
        if err:
            errors.append(err)
            print(err, file=sys.stderr)
            continue
        if packages:
            by_host[host] = packages
    return by_host, errors


def build_update_lines(by_host: dict[str, list[dict[str, str]]]) -> list[str]:
    """Flatten host→packages into notification lines."""
    lines: list[str] = []
    for host in sorted(by_host):
        for pkg in by_host[host]:
            lines.append(f"{host}: {format_package_line(pkg)}")
    return lines


def write_state(
    path: str,
    *,
    updates: list[str],
    by_host: dict[str, list[dict[str, str]]],
    errors: list[str],
    hosts_checked: list[str],
) -> None:
    """Write state atomically; failures are non-fatal so notify can still run."""
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "hosts_checked": hosts_checked,
        "updates": updates,
        "by_host": {h: [dict(p) for p in pkgs] for h, pkgs in by_host.items()},
        "errors": errors,
    }
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"WARN: could not write state {path}: {exc}", file=sys.stderr)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def hermes_notify(message: str) -> None:
    subprocess.run(["hermes", "send", "-t", HERMES_TARGET, message], check=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        default=os.environ.get("HOSTS", "").replace(" ", ",") or None,
        help="Comma-separated device aliases (devices.conf); or HOSTS env",
    )
    ap.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip pkg update (use cached indexes only; faster, may be stale)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not hermes-notify; still write state and print",
    )
    args = ap.parse_args(argv)

    hosts = list_hosts(args.limit)
    if not hosts:
        print("No hosts to check (empty devices.conf or --limit matched nothing)", file=sys.stderr)
        return 2

    by_host, errors = collect_updates(hosts, refresh=not args.no_refresh)
    updates = build_update_lines(by_host)
    write_state(
        STATE_PATH,
        updates=updates,
        by_host=by_host,
        errors=errors,
        hosts_checked=hosts,
    )

    if updates:
        message = "Stayturgid Termux package updates available:\n" + "\n".join(updates)
        print(message)
        if not args.dry_run:
            hermes_notify(message)
    else:
        print(
            "No Termux package updates available on %s"
            % (", ".join(hosts) if hosts else "(none)")
        )

    # Errors contacting hosts are non-fatal for the "updates available" path
    # (same spirit as check_apk_updates treating one bad GitHub repo as skip),
    # but exit 1 if *every* host failed so Jobber/notifyOnError can fire.
    if errors and not by_host and len(errors) >= len(hosts):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
