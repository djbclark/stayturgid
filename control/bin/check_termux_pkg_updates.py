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

The same SSH session also lists Python packages that pip, not apt, put on the
device: ``*.dist-info`` directories under site-packages that no dpkg package
owns. Device-side pip is unmanaged by policy (#309): device code is stdlib
only, and ``device/termux/requirements.txt`` declares the pip packages a
device may carry (none today). Any other pip-only package is reported once,
with the apt updates, so a hand-run ``pip install`` (t2e, 2026-09-19) is seen
instead of drifting silently.

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

from control.lib import hermes_notify as _hermes  # noqa: E402

STATE_PATH = os.path.expanduser("~/.local/state/stayturgid/termux-pkg-updates.json")

TERMUX_PREFIX = "/data/data/com.termux/files/usr"
# The device pip set this repo allows (#309); the checker reads only names.
DEVICE_REQUIREMENTS = _REPO / "device" / "termux" / "requirements.txt"
_PIP_MARKER = "@@stayturgid-pip-only@@"
# Device-supplied names reach a Telegram message: accept only sane metadata
# directory names and cap what one host can add (adversary review L3).
_META_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._]*)-([A-Za-z0-9.+!_]+?)(?:-py[0-9.]+)?\.(?:dist|egg)-info$")
_MAX_PIP_LINES_PER_HOST = 20
_MAX_MESSAGE_CHARS = 3500
SSH_TIMEOUT_SEC = int(os.environ.get("STAYTURGID_TERMUX_PKG_CHECK_TIMEOUT", "180"))

# apt list --upgradable line, e.g.:
#   curl/stable 8.12.1 aarch64 [upgradable from: 8.11.0]
#   libandroid-support/stable 29-1 aarch64 [upgradable from: 28-3]
_UPGRADABLE_RE = re.compile(r"^([^/\s]+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]\s*$")


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


def normalize_pip_name(name: str) -> str:
    """PEP 503 form, so `charset_normalizer` and `Charset-Normalizer` match."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pip_only(text: str) -> list[dict[str, str]]:
    """Parse the remote list of unowned ``<name>-<version>.dist-info`` (or
    ``.egg-info``) basenames. Entries whose name does not look like package
    metadata are counted, not dropped, so a check never fails open on them."""
    found: list[dict[str, str]] = []
    odd = 0
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = _META_RE.match(line)
        if m:
            found.append({"name": m.group(1), "version": m.group(2)})
        elif line.endswith((".dist-info", ".egg-info")):
            odd += 1
    if odd:
        found.append({"name": "unrecognised-metadata-entries", "version": str(odd)})
    return found


def declared_pip_packages(path: Path = DEVICE_REQUIREMENTS) -> set[str]:
    """Normalized names in device/termux/requirements.txt (missing file: none)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    names: set[str] = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", line)
        if m:
            names.add(normalize_pip_name(m.group(0)))
    return names


def build_pip_lines(pip_by_host: dict[str, list[dict[str, str]]], declared: set[str]) -> list[str]:
    """One line per pip-only package that the requirements file does not
    declare. The full list: it is the dedup key and the state, so a change
    past the message cap still counts as a change (re-review N2)."""
    lines: list[str] = []
    for host in sorted(pip_by_host):
        for pkg in sorted(pip_by_host[host], key=lambda p: normalize_pip_name(p["name"])):
            if normalize_pip_name(pkg["name"]) not in declared:
                lines.append(f"{host}: pip-only {pkg['name']} {pkg['version']}")
    return lines


def cap_lines_per_host(lines: list[str], limit: int = _MAX_PIP_LINES_PER_HOST) -> list[str]:
    """The message view of ``host: ...`` lines: at most *limit* per host."""
    shown: list[str] = []
    counts: dict[str, int] = {}
    for line in lines:
        host = line.split(":", 1)[0]
        counts[host] = counts.get(host, 0) + 1
        if counts[host] <= limit:
            shown.append(line)
    for host, n in counts.items():
        if n > limit:
            shown.append(f"{host}: pip-only and {n - limit} more")
    return shown


def _printable(text: str) -> str:
    """Device-supplied text bound for a chat message: no control characters."""
    return re.sub(r"[^\x20-\x7e]", "?", text)


def format_package_line(pkg: dict[str, str]) -> str:
    return _printable(f"{pkg['name']}: {pkg['current']} -> {pkg['latest']}")


def list_hosts(limit: str | None = None) -> list[str]:
    """Fleet aliases from devices.conf, optionally restricted by --limit/HOSTS."""
    all_hosts = [name for name, *_rest in dev.iter_devices_conf()]
    if not limit:
        return all_hosts
    wanted = {h.strip() for h in limit.replace(" ", ",").split(",") if h.strip()}
    return [h for h in all_hosts if h in wanted]


def ssh_probe(host: str, *, refresh: bool = True) -> tuple[list[dict[str, str]], list[dict[str, str]], str | None]:
    """SSH to *host* once: (upgradable apt packages, pip-only packages, error).

    When *refresh* is True (default), runs ``pkg update`` first so the check
    sees current indexes — same first step as the nightly upgrade path. The
    exit status stays apt's, so a broken apt is still an error; the pip pass
    is best effort and read-only (``dpkg -S`` over site-packages).
    """
    ssh_host = dev.resolve_ssh_host(host) or host
    refresh_cmd = "pkg update -y >/dev/null 2>&1 || true\n" if refresh else ""
    remote = (
        f"export PATH={TERMUX_PREFIX}/bin:$PATH\n"
        f"export TMPDIR={TERMUX_PREFIX}/tmp\n"  # nosec B108  # remote Termux app-private tmp, not a host /tmp
        "export DEBIAN_FRONTEND=noninteractive\n"
        f"{refresh_cmd}"
        "apt list --upgradable 2>/dev/null\n"
        "apt_rc=$?\n"
        f"echo '{_PIP_MARKER}'\n"
        # Both the prefix and `pip install --user`, wheels and legacy eggs.
        "set --\n"
        f"for d in {TERMUX_PREFIX}/lib/python3*/site-packages/*.dist-info"
        f" {TERMUX_PREFIX}/lib/python3*/site-packages/*.egg-info"
        ' "$HOME"/.local/lib/python3*/site-packages/*.dist-info'
        ' "$HOME"/.local/lib/python3*/site-packages/*.egg-info; do\n'
        '  [ -e "$d" ] && set -- "$@" "$d"\n'
        "done\n"
        'if [ "$#" -gt 0 ]; then\n'
        "  owned=$(dpkg -S \"$@\" 2>/dev/null | sed 's/^[^:]*: //')\n"
        '  for d in "$@"; do printf \'%s\\n\' "$owned" | grep -qxF "$d" || basename "$d"; done\n'
        "fi\n"
        'exit "$apt_rc"\n'
    )
    try:
        result = subprocess.run(
            ["ssh", *dev.SSH_OPTS, "-o", "ConnectTimeout=10", ssh_host, remote],
            capture_output=True,
            text=True,
            timeout=SSH_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return [], [], f"{host}: ssh timed out after {SSH_TIMEOUT_SEC}s"
    except OSError as exc:
        return [], [], f"{host}: ssh failed: {exc}"

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip().splitlines()
        detail = err[-1] if err else f"rc={result.returncode}"
        return [], [], f"{host}: ssh/apt failed ({detail})"

    apt_lines: list[str] = []
    pip_lines: list[str] = []
    target = apt_lines
    for line in (result.stdout or "").splitlines():
        if line.strip() == _PIP_MARKER:
            target = pip_lines
            continue
        target.append(line)
    return parse_apt_upgradable("\n".join(apt_lines)), parse_pip_only("\n".join(pip_lines)), None


def ssh_upgradable(host: str, *, refresh: bool = True) -> tuple[list[dict[str, str]], str | None]:
    """SSH to *host* and return (upgradable packages, error_or_None)."""
    packages, _pip_only, err = ssh_probe(host, refresh=refresh)
    return packages, err


def collect_updates(
    hosts: list[str],
    *,
    refresh: bool = True,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]], list[str]]:
    """Probe each host. Returns (host -> apt updates, host -> pip-only packages, errors)."""
    by_host: dict[str, list[dict[str, str]]] = {}
    pip_by_host: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []
    for host in hosts:
        packages, pip_only, err = ssh_probe(host, refresh=refresh)
        if err:
            errors.append(err)
            print(err, file=sys.stderr)
            continue
        if packages:
            by_host[host] = packages
        if pip_only:
            pip_by_host[host] = pip_only
    return by_host, pip_by_host, errors


def build_update_lines(by_host: dict[str, list[dict[str, str]]]) -> list[str]:
    """Flatten host→packages into notification lines."""
    lines: list[str] = []
    for host in sorted(by_host):
        for pkg in by_host[host]:
            lines.append(f"{host}: {format_package_line(pkg)}")
    return lines


def previous_notified_updates(path: str) -> list[str] | None:
    """Return last notified update lines, or None if no usable state exists."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("last_notified")
    if raw is None:
        raw = data.get("updates")
    if not isinstance(raw, list):
        return None
    return [str(x) for x in raw]


def should_notify(path: str, updates: list[str]) -> bool:
    """Telegram only when the pending-update set changes."""
    prev = previous_notified_updates(path)
    if prev is None:
        return bool(updates)
    return sorted(updates) != sorted(prev)


def write_state(
    path: str,
    *,
    updates: list[str],
    by_host: dict[str, list[dict[str, str]]],
    errors: list[str],
    hosts_checked: list[str],
    last_notified: list[str] | None = None,
    pip_only: list[str] | None = None,
) -> None:
    """Write state atomically; failures are non-fatal so notify can still run."""
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "hosts_checked": hosts_checked,
        "updates": updates,
        "last_notified": last_notified if last_notified is not None else updates,
        "by_host": {h: [dict(p) for p in pkgs] for h, pkgs in by_host.items()},
        "pip_only": pip_only or [],
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


def hermes_notify(message: str) -> bool:
    """One notice; True only when Hermes accepted it. Never raises.

    Goes through control/lib/hermes_notify, which finds ~/.local/bin/hermes:
    the nightly runs this checker under launchd's PATH, where a bare `hermes`
    raised FileNotFoundError (3 of 6 nights to 2026-10-09; adversary review H1).
    """
    try:
        if len(message) > _MAX_MESSAGE_CHARS:
            message = message[: _MAX_MESSAGE_CHARS - 12] + "\n(truncated)"
        return bool(_hermes.notify("stayturgid termux-pkg", message))
    except Exception as exc:  # noqa: BLE001 - a dead transport must not crash the check
        print(f"WARN: hermes notify failed: {exc}", file=sys.stderr)
        return False


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

    by_host, pip_by_host, errors = collect_updates(hosts, refresh=not args.no_refresh)
    updates = build_update_lines(by_host)
    pip_only = build_pip_lines(pip_by_host, declared_pip_packages())
    # One notice covers both, sent when either set changes.
    keys = updates + pip_only
    notify = should_notify(STATE_PATH, keys)
    previous = previous_notified_updates(STATE_PATH) or []

    sections: list[str] = []
    if updates:
        sections.append("Stayturgid Termux package updates available:\n" + "\n".join(updates))
    if pip_only:
        sections.append(
            "Termux pip packages outside policy (not from apt, not in device/termux/requirements.txt; #309):\n"
            + "\n".join(cap_lines_per_host(pip_only))
        )
    # A set counts as notified only once Hermes accepted it; a dry run or a
    # failed send leaves the previous one, so the next real run retries.
    notified = False
    if sections:
        message = "\n\n".join(sections)
        print(message)
        if notify and not args.dry_run:
            notified = hermes_notify(message)
            if not notified:
                print("WARN: hermes send failed; the notice will be retried on the next run", file=sys.stderr)
        elif not notify:
            print("(unchanged since last notify; Telegram skipped)")
    else:
        # The set emptied: nothing to send, and nothing left to retry.
        notified = notify and not args.dry_run
        print("No Termux package updates available on %s" % (", ".join(hosts) if hosts else "(none)"))
    write_state(
        STATE_PATH,
        updates=updates,
        by_host=by_host,
        errors=errors,
        hosts_checked=hosts,
        last_notified=keys if notified else previous,
        pip_only=pip_only,
    )

    # Errors contacting hosts are non-fatal for the "updates available" path
    # (same spirit as check_apk_updates treating one bad GitHub repo as skip),
    # but exit 1 if *every* host failed so Jobber/notifyOnError can fire.
    if errors and not by_host and len(errors) >= len(hosts):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
