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
leaves ansible at rc=0; it is found in the output instead. A run that fails
before any host reports (rc != 0, no host lines) sends a run-level notice
instead, once per distinct failure. Only whole-fleet, non-check runs notify
or touch the notice state: a ``--limit``/``HOSTS=`` run says nothing about
the hosts it skipped. The state records a notice only after Hermes accepted
it, so a gateway outage retries on the next run instead of losing the alert.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control.lib import hermes_notify
from control.lib.ansible_context import AnsibleConfigError, require_inventory, resolve_ansible_context, resolved_env
from control.lib.fleet_deploy_lock import FleetLockHeld, fleet_lock
from control.lib.secretspec_exec import BoundaryUnavailable, secretspec_run
from control.lib.stats import record_termux_pkg_error, record_termux_pkg_result, record_termux_pkg_run

PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "fleet" / "termux-pkg-upgrade.yml"
CHECK_UPDATES = REPO_ROOT / "control" / "bin" / "check_termux_pkg_updates.py"
LOG_DIR = Path.home() / ".config" / "stayturgid" / "logs"
LOG = LOG_DIR / "termux-pkg-nightly.log"
MAX_LOG_LINES = 4000
# Last notified per-host failure set (and run-level failure, if any), so Hermes
# hears about a change (a new failure, a different one, or recovery), not the
# same offline phone nightly.
STATE_PATH = Path.home() / ".local" / "state" / "stayturgid" / "termux-pkg-nightly.json"

# `fatal: [s24]: UNREACHABLE! => {...}` / `fatal: [s24]: FAILED! => {...}`, and
# `fatal: [s24 -> localhost]: FAILED!` for a delegated task: the host is s24.
_FATAL_RE = re.compile(r"^fatal: \[([^\]\s]+)(?: -> [^\]]+)?\]: (UNREACHABLE|FAILED)! => (.*)$")
# `s24                        : ok=5    changed=1    unreachable=0    failed=1 ...`
_RECAP_RE = re.compile(r"^(\S+)\s+:\s+ok=\d+\s+changed=\d+\s+unreachable=(\d+)\s+failed=(\d+)")
_MAX_ERROR_CHARS = 500
STALE_INDEX_ERROR = "pkg update failed; upgraded against cached indexes (mirror unreachable or dead?)"


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


def parse_recap_hosts(output: str) -> list[str]:
    """Every host named in the PLAY RECAP, in order: the hosts the play covered."""
    hosts: list[str] = []
    for line in output.splitlines():
        m = _RECAP_RE.match(line.strip())
        if m and m.group(1) not in hosts:
            hosts.append(m.group(1))
    return hosts


def read_host_results(result_dir: Path | None) -> dict[str, dict]:
    """The per-host result files the playbook wrote (#310); bad files are skipped."""
    results: dict[str, dict] = {}
    if result_dir is None:
        return results
    try:
        paths = sorted(result_dir.glob("*.json"))
    except OSError:
        return results
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log("WARN: unreadable result file %s" % path.name)
            continue
        if isinstance(data, dict):
            results[str(data.get("host") or path.stem)] = data
    return results


def _duration_s(result: dict) -> float | None:
    try:
        started = dt.datetime.strptime(str(result["started"]), "%Y-%m-%dT%H:%M:%SZ")
        finished = dt.datetime.strptime(str(result["finished"]), "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, ValueError):
        return None
    return max(0.0, (finished - started).total_seconds())


@dataclass
class HostOutcome:
    status: str
    changed: bool = False
    upgraded_packages: list[str] = field(default_factory=list)
    index_update_failed: bool = False
    duration_s: float | None = None
    error: str = ""


def host_outcomes(
    hosts: list[str], results: dict[str, dict], failures: dict[str, dict[str, str]]
) -> dict[str, HostOutcome]:
    """One outcome per host the run covered.

    A parsed failure wins over a result file (the play stops for a failed
    host, and an unreachable one writes none). A host in the recap with
    neither is ``skipped``: it finished the play without reaching the result
    task. A host with ``stayturgid_termux_pkg_upgrade_enabled: false`` ends
    before anything is counted, so ansible leaves it out of the recap and it
    gets no row at all.
    """
    outcomes: dict[str, HostOutcome] = {}
    for host in sorted(set(hosts) | set(results) | set(failures)):
        result = results.get(host, {})
        packages = result.get("upgraded_packages")
        o = HostOutcome(
            status="skipped",
            changed=bool(result.get("changed")),
            upgraded_packages=[str(p) for p in packages] if isinstance(packages, list) else [],
            index_update_failed=bool(result.get("index_update_failed")),
            duration_s=_duration_s(result) if result else None,
        )
        if host in failures:
            o.status = failures[host]["status"]
            o.error = failures[host]["error"]
        elif result:
            o.status = "changed" if o.changed else "ok"
            if o.index_update_failed:
                o.error = STALE_INDEX_ERROR
        outcomes[host] = o
    return outcomes


def stale_index_hosts(outcomes: dict[str, HostOutcome]) -> dict[str, dict[str, str]]:
    """Hosts that upgraded but could not refresh their indexes, as notice entries.

    termux_pkg tolerates a failed ``pkg update`` (a mirror sync is routine),
    so such a host reports ok while it may be upgrading against a dead mirror
    for weeks: the case #310 names. It joins the Hermes failing set, which
    already alerts once per change, not nightly.
    """
    return {
        host: {"status": "stale_index", "error": STALE_INDEX_ERROR}
        for host, o in outcomes.items()
        if o.status in ("ok", "changed") and o.index_update_failed
    }


def _failure_keys(failures: dict[str, dict[str, str]]) -> list[str]:
    return sorted("%s:%s" % (host, info["status"]) for host, info in failures.items())


def _read_state() -> dict | None:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _previous_failure_keys(state: dict | None) -> list[str] | None:
    keys = state.get("failing") if state else None
    return [str(k) for k in keys] if isinstance(keys, list) else None


def _previous_run_failure(state: dict | None) -> str | None:
    value = state.get("run_failed") if state else None
    return value if isinstance(value, str) and value else None


def _write_state(keys: list[str], run_failed: str | None = None) -> None:
    payload: dict[str, object] = {"checked_at": ts(), "failing": keys}
    if run_failed:
        payload["run_failed"] = run_failed
    tmp = STATE_PATH.with_suffix(".json.tmp")
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, STATE_PATH)
    except OSError as exc:
        log("WARN: could not write %s: %s" % (STATE_PATH, exc))


def _send(message: str) -> bool:
    """One Hermes notice; True only when it was accepted. Never raises."""
    try:
        sent = hermes_notify.notify("stayturgid termux-pkg", message)
    except Exception as exc:  # noqa: BLE001 - a dead transport must not fail the job
        log("WARN: hermes notify failed: %s" % exc)
        return False
    if not sent:
        log("WARN: hermes notify failed; the notice will be retried on the next run")
        return False
    return True


def notify_failure_change(failures: dict[str, dict[str, str]]) -> bool:
    """Hermes-notify when the failing-host set differs from the last one sent.

    Call only for a whole-fleet run that completed (the per-host set is
    meaningful). Also announces that the job runs again after a notified
    run-level failure. Returns True when a notice went out; the state is
    written only then. Never raises: like the telemetry writer, the notice
    must not be able to break the upgrade job.
    """
    state = _read_state()
    keys = _failure_keys(failures)
    previous = _previous_failure_keys(state)
    run_failed = _previous_run_failure(state)
    if keys == (previous or []) and not run_failed:
        return False
    if keys:
        lines = [
            "%s %s: %s" % (host, info["status"], info["error"].splitlines()[0][:200])
            for host, info in sorted(failures.items())
        ]
        message = "nightly pkg upgrade problems on %d host(s):\n%s" % (len(failures), "\n".join(lines))
    elif previous:
        message = "nightly pkg upgrade OK again on every reachable host (was: %s)" % ", ".join(previous)
    else:
        message = "nightly pkg upgrade OK on every reachable host"
    if run_failed:
        message = "nightly pkg upgrade runs again (was: %s)\n%s" % (run_failed, message)
    if not _send(message):
        return False
    _write_state(keys)
    return True


def _run_failure_summary(phase: str, error: str) -> str:
    lines = [line.strip() for line in error.splitlines() if line.strip()]
    pick = next((line for line in lines if "ERROR" in line), lines[-1] if lines else "no output")
    return "%s: %s" % (phase, pick[:200])


def notify_run_failure(phase: str, error: str) -> bool:
    """Hermes-notify a whole-fleet run that failed before any host reported.

    Not an "OK again": the per-host set from the last completed run is kept.
    Sent once per distinct failure (phase plus its ERROR line); the state is
    written only when Hermes accepted the notice. Never raises.
    """
    state = _read_state()
    summary = _run_failure_summary(phase, error)
    if _previous_run_failure(state) == summary:
        return False
    if not _send("nightly pkg upgrade did not complete (%s)" % summary):
        return False
    _write_state(_previous_failure_keys(state) or [], run_failed=summary)
    return True


def _run_failed(phase: str, error: str, rc: int, *, notify: bool, notice: str | None = None) -> int:
    """Record a run that ended before any host reported, and tell Hermes once.

    Every early return goes through here (review-2 4.1d): preflight, lock,
    missing binary and timeout used to record telemetry only, so a nightly
    that never ran stayed silent. ``notice`` is a stable text for the Hermes
    dedup when ``error`` varies run to run (the lock holder's pid).
    """
    record_termux_pkg_error(phase, error, rc=rc)
    if notify and notify_run_failure(phase, notice or error):
        log("hermes: notified run-level failure")
    return rc


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
    # Only a whole-fleet, real run speaks for the fleet (review-2 4.1b).
    notify = not check and not args.limit

    if not PLAYBOOK.is_file():
        log("ERROR: missing playbook %s" % PLAYBOOK)
        return _run_failed("preflight", "missing playbook %s" % PLAYBOOK, 2, notify=notify)
    try:
        context = resolve_ansible_context(REPO_ROOT)
        require_inventory(context)
    except AnsibleConfigError as exc:
        log("ERROR: %s" % exc)
        return _run_failed("preflight", str(exc), 2, notify=notify)

    try:
        cmd = secretspec_run(
            "ansible-playbook",
            str(PLAYBOOK),
            "-e",
            "stayturgid_repo_root=%s" % REPO_ROOT,
        )
    except BoundaryUnavailable as exc:
        # A provisioned node whose sudo-secretspec broke (#287 fails closed).
        # Under launchd an uncaught traceback would only reach the .err.log,
        # failing silently every night: record it and tell Hermes once.
        log("ERROR: %s" % exc)
        return _run_failed("preflight", str(exc), 2, notify=notify)
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

    # Each host that finishes writes <dir>/<host>.json (#310). A dry run
    # upgrades nothing, so it records no results.
    result_dir = None if check else Path(tempfile.mkdtemp(prefix="termux-pkg-nightly-"))
    if result_dir is not None:
        cmd.extend(["-e", json.dumps({"stayturgid_termux_pkg_result_dir": str(result_dir)})])
    try:
        return _run_and_report(cmd, env, label, limit=args.limit or "", notify=notify, result_dir=result_dir)
    finally:
        if result_dir is not None:
            shutil.rmtree(result_dir, ignore_errors=True)


def _run_and_report(
    cmd: list[str], env: dict[str, str], label: str, *, limit: str, notify: bool, result_dir: Path | None
) -> int:
    started = time.monotonic()
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
        return _run_failed(
            "lock",
            str(exc),
            3,
            notify=notify,
            notice="the fleet lock was held by another run; tonight's upgrade was skipped",
        )
    except FileNotFoundError:
        log("ERROR: secretspec or ansible-playbook not found on PATH=%s" % env.get("PATH"))
        return _run_failed("preflight", "secretspec or ansible-playbook not found on PATH", 2, notify=notify)
    except subprocess.TimeoutExpired:
        log("ERROR: ansible-playbook timed out")
        return _run_failed("upgrade", "ansible-playbook timed out", 2, notify=notify)
    duration = time.monotonic() - started

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

    stale: dict[str, dict[str, str]] = {}
    if result_dir is not None:
        outcomes = host_outcomes(parse_recap_hosts(r.stdout or ""), read_host_results(result_dir), failures)
        stale = stale_index_hosts(outcomes)
        for host in sorted(stale):
            log("host %s stale_index: %s" % (host, STALE_INDEX_ERROR))
            record_termux_pkg_error("update", STALE_INDEX_ERROR, host=host, rc=r.returncode)
        run_id = uuid.uuid4().hex[:12]
        statuses: dict[str, int] = {}
        for host, o in outcomes.items():
            statuses[o.status] = statuses.get(o.status, 0) + 1
            record_termux_pkg_result(
                host,
                o.status,
                run_id=run_id,
                changed=o.changed,
                upgraded_packages=o.upgraded_packages,
                index_update_failed=o.index_update_failed,
                duration_s=o.duration_s,
                error=o.error,
                rc=r.returncode,
            )
        record_termux_pkg_run(run_id, rc=r.returncode, duration_s=duration, limit=limit, statuses=statuses)
        log("results: run %s %s" % (run_id, " ".join("%s=%d" % kv for kv in sorted(statuses.items())) or "no hosts"))

    if r.returncode != 0 and not failures:
        # Nothing per-host to attribute it to. Last 20 lines carry the ansible
        # failure summary; the full run stays in the human log. Keep the record
        # small enough for one JSON line.
        tail = "\n".join(out.splitlines()[-20:]) if out else "ansible-playbook rc=%s" % r.returncode
        _run_failed("upgrade", tail, r.returncode, notify=notify)
    elif notify:
        if notify_failure_change({**stale, **failures}):
            log("hermes: notified failing-host set change")
    trim_log()
    # Unreachable-only runs stay rc=0: an offline phone is expected and is now
    # recorded per host, while a real upgrade failure keeps ansible's rc. A
    # stale index stays rc=0 too: the upgrade itself ran.
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
