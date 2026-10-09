#!/usr/bin/env python3
"""Run fleet-wide Termux pkg update/upgrade via Ansible (nightly launchd entry).

Standard Termux package maintenance is ``pkg update`` + ``pkg upgrade -y``
(apt under the hood). This wrapper invokes the same
``stayturgid.termux.termux_pkg`` path used at deploy time (mirror pin +
``apt-get full-upgrade`` / ``pkg upgrade``), over SSH to every inventory host.

Usage:
  python3 control/bin/termux_pkg_nightly.py
  python3 control/bin/termux_pkg_nightly.py --limit oneui-device
  CHECK=1 python3 control/bin/termux_pkg_nightly.py   # ansible --check

Logs: ~/.config/stayturgid/logs/termux-pkg-nightly.log
Telemetry (#310): one ``termux_pkg_error`` record per failed or unreachable
host in ~/.config/stayturgid/stats/termux_pkg.jsonl (Vector -> OpenObserve
stream ``termux_pkg``), and a Hermes notice when the set of failing hosts
changes. The playbook runs with ``ignore_unreachable``, so an offline phone
leaves ansible at rc=0; it is found in the output instead.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control.lib import hermes_notify
from control.lib.ansible_context import AnsibleConfigError, require_inventory, resolve_ansible_context, resolved_env
from control.lib.fleet_deploy_lock import FleetLockHeld, fleet_lock
from control.lib.secretspec_exec import secretspec_run
from control.lib.stats import record_termux_pkg_error

PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "fleet" / "termux-pkg-upgrade.yml"
CHECK_UPDATES = REPO_ROOT / "control" / "bin" / "check_termux_pkg_updates.py"
LOG_DIR = Path.home() / ".config" / "stayturgid" / "logs"
LOG = LOG_DIR / "termux-pkg-nightly.log"
MAX_LOG_LINES = 4000
# Last notified per-host failure set, so Hermes hears about a change (a new
# failure, a different one, or recovery), not the same offline phone nightly.
STATE_PATH = Path.home() / ".local" / "state" / "stayturgid" / "termux-pkg-nightly.json"

# `fatal: [s24]: UNREACHABLE! => {...}` / `fatal: [s24]: FAILED! => {...}`
_FATAL_RE = re.compile(r"^fatal: \[([^\]]+)\]: (UNREACHABLE|FAILED)! => (.*)$")
# `s24                        : ok=5    changed=1    unreachable=0    failed=1 ...`
_RECAP_RE = re.compile(r"^(\S+)\s+:\s+ok=\d+\s+changed=\d+\s+unreachable=(\d+)\s+failed=(\d+)")
_MAX_ERROR_CHARS = 500


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


def _fatal_message(payload: str) -> str:
    """Best-effort `msg` from a fatal result; the raw payload if it is not JSON."""
    try:
        data = json.loads(payload)
    except ValueError:
        return payload.strip()[:_MAX_ERROR_CHARS]
    if isinstance(data, dict):
        msg = data.get("msg") or data.get("stderr") or data.get("module_stderr") or ""
        if isinstance(msg, str) and msg.strip():
            return msg.strip()[:_MAX_ERROR_CHARS]
    return payload.strip()[:_MAX_ERROR_CHARS]


def parse_host_failures(output: str) -> dict[str, dict[str, str]]:
    """Map each host that failed or was unreachable to its status and error.

    A FAILED result outranks UNREACHABLE for the same host (it reached the host
    and the upgrade itself broke). The PLAY RECAP catches a host whose fatal
    line was not printed; with ``ignore_unreachable`` the recap counts an
    unreachable host as ok+ignored, so the fatal lines are the primary source.
    """
    failures: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        line = line.strip()
        m = _FATAL_RE.match(line)
        if m:
            host, kind, payload = m.groups()
            status = "failed" if kind == "FAILED" else "unreachable"
            current = failures.get(host)
            if current is None or (current["status"] == "unreachable" and status == "failed"):
                failures[host] = {"status": status, "error": _fatal_message(payload)}
            continue
        m = _RECAP_RE.match(line)
        if m:
            host, unreachable, failed = m.group(1), int(m.group(2)), int(m.group(3))
            if failed and failures.get(host, {}).get("status") != "failed":
                failures[host] = {
                    "status": "failed",
                    "error": failures.get(host, {}).get("error") or "failed=%d in PLAY RECAP" % failed,
                }
            elif unreachable and host not in failures:
                failures[host] = {"status": "unreachable", "error": "unreachable=%d in PLAY RECAP" % unreachable}
    return failures


def _failure_keys(failures: dict[str, dict[str, str]]) -> list[str]:
    return sorted("%s:%s" % (host, info["status"]) for host, info in failures.items())


def _previous_failure_keys() -> list[str] | None:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    keys = data.get("failing") if isinstance(data, dict) else None
    return [str(k) for k in keys] if isinstance(keys, list) else None


def _write_failure_state(keys: list[str]) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"checked_at": ts(), "failing": keys}, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, STATE_PATH)
    except OSError as exc:
        log("WARN: could not write %s: %s" % (STATE_PATH, exc))


def notify_failure_change(failures: dict[str, dict[str, str]]) -> bool:
    """Hermes-notify when the failing-host set differs from the last one sent.

    Returns True when a notice went out. Never raises: like the telemetry
    writer, the notice must not be able to break the upgrade job.
    """
    keys = _failure_keys(failures)
    previous = _previous_failure_keys()
    if keys == (previous or []):
        return False
    if keys:
        lines = [
            "%s %s: %s" % (host, info["status"], info["error"].splitlines()[0][:200])
            for host, info in sorted(failures.items())
        ]
        message = "nightly pkg upgrade problems on %d host(s):\n%s" % (len(failures), "\n".join(lines))
    else:
        message = "nightly pkg upgrade OK again on every reachable host (was: %s)" % ", ".join(previous or [])
    try:
        hermes_notify.notify("stayturgid termux-pkg", message)
    except Exception as exc:  # noqa: BLE001 - a dead transport must not fail the job
        log("WARN: hermes notify failed: %s" % exc)
        return False
    _write_failure_state(keys)
    return True


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
        record_termux_pkg_error("preflight", "missing playbook %s" % PLAYBOOK, rc=2)
        return 2
    try:
        context = resolve_ansible_context(REPO_ROOT)
        require_inventory(context)
    except AnsibleConfigError as exc:
        log("ERROR: %s" % exc)
        record_termux_pkg_error("preflight", str(exc), rc=2)
        return 2

    cmd = secretspec_run(
        "ansible-playbook",
        str(PLAYBOOK),
        "-e",
        "stayturgid_repo_root=%s" % REPO_ROOT,
    )
    if args.limit:
        cmd.extend(["--limit", args.limit])
    if check:
        cmd.extend(["--check", "--diff"])

    # resolved_env() also supplies ANSIBLE_ROLES_PATH/ANSIBLE_COLLECTIONS_PATH —
    # without them ansible-playbook can't resolve stayturgid.termux.termux_pkg.
    env = resolved_env(REPO_ROOT)
    # launchd has a minimal PATH; prefer Homebrew ansible.
    homebrew = "/opt/homebrew/bin:/usr/local/bin"
    env["PATH"] = homebrew + ":" + env.get("PATH", "/usr/bin:/bin")

    log("start: config=%s (%s) inventory=%s" % (context.config, context.source, context.inventory))
    log("start: %s" % " ".join(cmd))
    label = "termux_pkg_nightly.py %s" % (args.limit or "(whole fleet)")

    # Pre-upgrade visibility (#152): hermes-notify which packages are about to
    # be upgraded. Skip in ansible --check mode so dry-runs stay silent.
    # Failures here must not block the upgrade itself.
    if not check and CHECK_UPDATES.is_file():
        pre_cmd = [sys.executable, str(CHECK_UPDATES)]
        if args.limit:
            pre_cmd.extend(["--limit", args.limit])
        log("pre-check: %s" % " ".join(pre_cmd))
        try:
            pre = subprocess.run(
                pre_cmd,
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("STAYTURGID_TERMUX_PKG_CHECK_TIMEOUT", "600")),
            )
            pre_out = ((pre.stdout or "") + (pre.stderr or "")).strip()
            if pre_out:
                for line in pre_out.splitlines()[-40:]:
                    log("  | %s" % line)
            log("pre-check rc=%s" % pre.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log("WARN: pre-check failed (continuing upgrade): %s" % exc)

    try:
        with fleet_lock(label):
            r = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("STAYTURGID_TERMUX_PKG_TIMEOUT", "3600")),
            )
    except FleetLockHeld as exc:
        log("ERROR: %s" % exc)
        record_termux_pkg_error("lock", str(exc), rc=3)
        return 3
    except FileNotFoundError:
        log("ERROR: secretspec or ansible-playbook not found on PATH=%s" % env.get("PATH"))
        record_termux_pkg_error("preflight", "secretspec or ansible-playbook not found on PATH", rc=2)
        return 2
    except subprocess.TimeoutExpired:
        log("ERROR: ansible-playbook timed out")
        record_termux_pkg_error("upgrade", "ansible-playbook timed out", rc=2)
        return 2

    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if out:
        for line in out.splitlines()[-80:]:
            log("  | %s" % line)
    log("done rc=%s" % r.returncode)
    failures = parse_host_failures(r.stdout or "")
    for host, info in sorted(failures.items()):
        log("host %s %s: %s" % (host, info["status"], info["error"].splitlines()[0] if info["error"] else ""))
        phase = "unreachable" if info["status"] == "unreachable" else "upgrade"
        record_termux_pkg_error(phase, info["error"], host=host, rc=r.returncode)
    if r.returncode != 0 and not failures:
        # Nothing per-host to attribute it to. Last 20 lines carry the ansible
        # failure summary; the full run stays in the human log. Keep the record
        # small enough for one JSON line.
        tail = "\n".join(out.splitlines()[-20:]) if out else "ansible-playbook rc=%s" % r.returncode
        record_termux_pkg_error("upgrade", tail, rc=r.returncode)
    if not check:
        if notify_failure_change(failures):
            log("hermes: notified failing-host set change")
    trim_log()
    # Unreachable-only runs stay rc=0: an offline phone is expected and is now
    # recorded per host, while a real upgrade failure keeps ansible's rc.
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
